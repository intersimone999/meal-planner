# menuapp — Specification

_This document is the source of truth for what the app must do. Every implementation decision should be traceable back to a requirement here. Any scope change must be reflected here **before** code is written._

---

## 1. Purpose

A personal, self-hosted webapp for weekly meal planning. It turns "what am I cooking this week?" into "what do I need to buy?" with the lowest possible friction to add recipes and assign meals.

## 2. Users and operating context

- **Single user** (the owner). No multi-user, no roles, no sharing.
- **Self-hosted** on a small web server, exposed on the public internet or LAN.
- Accessed from a **browser** on desktop and mobile.
- Runs as a **single container**, single process, single SQLite file.

## 3. Functional requirements

### 3.1 Recipes

- CRUD: create, list, view, edit, delete.
- A recipe has: **name** (unique across all recipes), optional **notes** (free-text), and a **set of ingredients**.
- **Ingredients on a recipe are just names — no quantities, no units.** Rationale: recipes must be trivial to add; friction here kills the whole app for the user.
- The same ingredient cannot appear twice on the same recipe.
- Deleting a recipe removes its ingredient links but never deletes ingredients themselves.

### 3.2 Ingredients

- A canonical, deduplicated master list of ingredient names.
- **Inline creation** while editing a recipe: type a name, hit enter. If an ingredient with that name (case-insensitive match) exists, reuse it; otherwise create it.
- **Autocomplete** in the inline input, backed by the current ingredient list.
- **Dedicated ingredients page** with: full list, per-ingredient usage count, rename, merge-into-another, delete.
- **Delete is blocked** if the ingredient is still referenced by any recipe (return a clear error message).
- **Rename** updates the canonical name and is immediately reflected everywhere.
- **Merge** reassigns all `recipe_ingredients` rows from the source to the target and deletes the source.

### 3.3 Weekly plan

- The plan is keyed by **ISO year + ISO week** (1–53). URLs like `/planner/2026/36`.
- Fixed slots per day: **breakfast, lunch, dinner**. No snack.
- Each `(year, week, day, slot)` cell holds **at most one recipe**. Re-assigning overwrites.
- Actions: assign a recipe to a slot, remove a recipe from a slot.
- Navigation: previous week, next week, jump to the current week.
- The current week (`/planner`) redirects to the ISO week containing today.

### 3.4 Shopping list

- URL: `/shopping/{year}/{week}` (root `/shopping` redirects to the current week).
- The page shows **two clearly separated sections**:
  a) **Derived from the plan** — the distinct, sorted set of ingredient names appearing in any recipe planned for that week.
  b) **Manual items** — user-managed persistent items (name only, checkable), independent of any week. They persist across weeks.
- **The two sections are never silently merged**, even if the same name appears in both. If "olive oil" is a manual pantry item and also used by a planned recipe, it shows in both sections. The user reconciles intent, not the app.
- Manual items support: add (name only), toggle checked, delete. Checked items sort to the bottom and render grayed out / struck through.

### 3.5 Import and export

- **Export** `GET /export`: downloads a JSON file containing all recipes and ingredients. Format:
  ```json
  {
    "ingredients": ["salt", "olive oil", "..."],
    "recipes": [
      {"name": "Lasagna", "notes": "...", "ingredients": ["pasta", "beef", "..."]}
    ]
  }
  ```
- **Excludes** the weekly plan and manual shopping items — those are ephemeral state, not portable content.
- **Import** `POST /import` (multipart file upload): upserts by name.
  - Ingredients: create if missing.
  - Recipes: **skip if a recipe with that name already exists** (never overwrite silently). Report skipped-vs-created counts on success.

## 4. Non-functional requirements

### 4.1 Deployment

- Buildable and runnable from the root `Dockerfile`.
- Single container image, single SQLite file mounted at `/data` via a host volume.
- Database path from `MENUAPP_DB_PATH` (default `/data/menuapp.db` in-container; a local relative path for dev outside Docker).
- Runs as a single `uvicorn` process. No workers, no external services.

### 4.2 Authentication

- **HTTP Basic Auth**, single credential pair from environment: `MENUAPP_USER`, `MENUAPP_PASSWORD`.
- If either env var is unset, auth is **bypassed** (development mode) and a warning is logged at startup.
- Auth gates every route except `/healthz` (used for container health checks).

### 4.3 Persistence

- SQLite. Schema created by SQLAlchemy `Base.metadata.create_all()` on startup.
- Migration tooling (Alembic) is deferred until the first breaking schema change post-v1.

### 4.4 Frontend

- Server-rendered Jinja2 templates.
- **HTMX** for partial updates. No JS framework, no bundler, no build step.
- **Mobile-usable**: the planner grid and shopping list must be readable and interactive at 375px width.

### 4.5 Reliability

- The app must never lose the user's data on a graceful container restart. All persistent state lives in the mounted SQLite file.
- Invalid input (missing fields, duplicate names, deleting a used ingredient) returns a clear error in the UI, not a 500.

## 5. Domain model

- **Ingredient**(`id`, `name` UNIQUE CI)
- **Recipe**(`id`, `name` UNIQUE, `notes` NULLABLE)
- **RecipeIngredient**(`id`, `recipe_id` FK→Recipe, `ingredient_id` FK→Ingredient) — UNIQUE(`recipe_id`, `ingredient_id`)
- **PlannedMeal**(`id`, `year`, `week`, `day` 0–6, `slot` IN {breakfast, lunch, dinner}, `recipe_id` FK→Recipe) — UNIQUE(`year`, `week`, `day`, `slot`)
- **ManualShoppingItem**(`id`, `name`, `checked` BOOL, `created_at`)

## 6. Out of scope (v1)

Explicit non-goals — do **not** add these without updating the spec first:

- Quantities and units on ingredients.
- Servings / portion scaling.
- Multi-user, accounts, roles.
- Nutritional information.
- Recipe search, tagging, cuisines, ratings, favorites.
- Grocery-store integrations.
- Native or PWA mobile app.
- Migration tooling.
- Undo / soft-delete.

## 7. Acceptance criteria

1. **Recipe entry friction test:** creating a new recipe with 5 new-to-the-system ingredients takes ≤ 30 seconds and never blocks on a modal.
2. **End-to-end plan → shopping:** create 3 recipes with overlapping ingredients → plan them across Mon/Wed/Fri dinner of the current week → `/shopping` derived section shows the union of their ingredients, deduped and sorted. Add a manual item "dish soap" → it appears only in the manual section.
3. **Container persistence:** `docker run` with a mounted `/data` volume; create a recipe; restart the container; recipe is still there.
4. **Auth:** with `MENUAPP_USER`/`MENUAPP_PASSWORD` set, all pages prompt for basic auth; `/healthz` does not.
5. **Import/export round-trip:** export → wipe DB → import → recipe and ingredient sets are identical (order-insensitive).
