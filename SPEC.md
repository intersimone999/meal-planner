# menuapp — Specification

_This document is the source of truth for what the app must do. Every implementation decision should be traceable back to a requirement here. Any scope change must be reflected here **before** code is written._

---

## 1. Purpose

A personal, self-hosted webapp for weekly meal planning. It turns "cosa cucino questa settimana?" into "cosa devo comprare?" with the lowest possible friction to add recipes and assign meals.

## 2. Users and operating context

- **Single user** (the owner). No multi-user, no roles, no sharing.
- **Self-hosted** on a small web server, exposed on the public internet or LAN.
- Accessed from a **browser** on desktop and mobile.
- Runs as a **single container**, single process, single SQLite file.
- **All user-facing text is in Italian.** Code, variable names, comments, and log/error messages emitted to the server console remain in English.

## 3. Functional requirements

### 3.1 Recipes

- CRUD: create, list, view, edit, delete.
- A recipe has: **name** (unique across all recipes), optional **notes** (free-text), and a **set of ingredients**.
- **Ingredients on a recipe are just names — no quantities, no units.** Rationale: recipes must be trivial to add; friction here kills the whole app for the user.
- The same ingredient cannot appear twice on the same recipe.
- Deleting a recipe removes its ingredient links, cascades to any `PlannedMeal` and `TemplateSlot` rows that reference it, but never deletes `Ingredient` rows themselves.

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
- Fixed slots per day: **lunch (pranzo), dinner (cena)**. Breakfast is intentionally excluded — the user handles it separately.
- Each `(year, week, day, slot)` cell holds **at most one recipe**. Re-assigning overwrites.
- Actions: assign a recipe to a slot, remove a recipe from a slot.
- Navigation: previous week, next week, jump to the current week.
- The current week (`/planner`) redirects to the ISO week containing today.

### 3.4 Weekly plan templates

- Named, reusable weekly plans (e.g. "settimana standard", "settimana estiva").
- CRUD: create, list, edit, delete templates.
- A template has: **name** (unique across templates) and a set of `(day, slot, recipe)` entries under the same rules as §3.3 (fixed slots {lunch, dinner}, at most one recipe per cell).
- **Apply to week:** on the planner, the user selects a template and a target week. The template populates **only empty cells** in that week — existing planned meals are preserved. Deliberately non-destructive; overwriting requires the user to first clear the slot.
- Template editing UI mirrors the planner grid but is week-agnostic.
- Deleting a recipe cascades to `TemplateSlot` rows the same way it cascades to `PlannedMeal` rows.

### 3.5 Shopping list

- URL: `/shopping/{year}/{week}` (root `/shopping` redirects to the current week).
- Two clearly separated sections:
  a) **Derived dal piano** — the distinct, sorted set of ingredient names appearing in any recipe planned for that week. **Each item has a checkbox.**
  b) **Voci manuali** — user-managed persistent items (name only, checkable), independent of any week. They persist across weeks.
- **The two sections are never silently merged**, even if the same name appears in both. If "olio d'oliva" is a manual pantry item and also used by a planned recipe, it shows in both sections. The user reconciles intent, not the app.
- **Derived checkbox behavior:**
  - Check state is stored per `(year, week, ingredient)`, so each ISO week has its own set of checks.
  - "Auto de-select when a new week starts" is a natural consequence: viewing a new week shows a fresh, empty check state. There is no explicit reset job.
  - Checked derived items sort to the bottom of the derived section and render grayed out / struck through, matching manual-item visuals.
- **Manual items:** add (name only), toggle checked, delete. Checked manual items also sort to the bottom and gray out; they do **not** auto-reset (they persist as long as the user leaves them checked).

### 3.6 Import and export

- **Dedicated import page** at `/import` with a file upload form. Shows a per-import result summary (created / skipped / errored counts by entity type).
- **Export** `GET /export`: downloads a JSON file. Format:
  ```json
  {
    "ingredients": ["sale", "olio d'oliva", "..."],
    "recipes": [
      {"name": "Lasagna", "notes": "...", "ingredients": ["pasta", "manzo"]}
    ],
    "templates": [
      {
        "name": "settimana standard",
        "slots": [
          {"day": 0, "slot": "lunch", "recipe": "Lasagna"},
          {"day": 0, "slot": "dinner", "recipe": "Insalata"}
        ]
      }
    ]
  }
  ```
- **Excludes** the weekly plan, manual shopping items, and derived-ingredient checkboxes — those are ephemeral state, not portable content.
- **Import** `POST /import` (multipart file upload): upserts by name, never silently overwrites.
  - **Ingredients:** create if missing.
  - **Recipes:** skip if a recipe with that name already exists.
  - **Templates:** skip if a template with that name already exists.
  - **Template slots referencing an unknown recipe:** skip that slot and count it in an `orphaned_slots` figure on the summary page. Do not fail the whole import.

## 4. Non-functional requirements

### 4.1 Deployment

- Buildable and runnable from the root `Dockerfile`.
- Single container image, single SQLite file mounted at `/data` via a host volume.
- Database path from `MENUAPP_DB_PATH` (default `/data/menuapp.db` in-container; a local relative path for dev outside Docker).
- Runs as a single `uvicorn` process. No workers, no external services.

### 4.2 Authentication

- **Form-based login page** at `/login` with fields for username and password. Not HTTP Basic Auth.
- Credentials come from environment variables: `MENUAPP_USER`, `MENUAPP_PASSWORD`. Single user.
- **Session:** signed cookie via Starlette `SessionMiddleware`, 30-day expiry, `HttpOnly`, `SameSite=Lax`, `Secure` when served over HTTPS. Cookie survives browser restarts within its TTL.
- **Session signing key:** `MENUAPP_SESSION_SECRET` env var. If unset, a random key is generated at startup and a warning is logged; sessions do not survive process restarts in that case.
- **Logout** at `/logout` clears the session and redirects to `/login`.
- Auth gates every route except `/login`, `/logout`, `/healthz`, and `/static/*`.
- Unauthenticated requests to protected routes redirect to `/login?next=<original path>` and are returned to `next` after login.
- **Development bypass:** if either `MENUAPP_USER` or `MENUAPP_PASSWORD` is unset, auth is bypassed entirely (login page is not shown, all routes are open) and a warning is logged at startup.
- Password comparison is constant-time (`secrets.compare_digest`).

### 4.3 Persistence

- SQLite. Schema created by SQLAlchemy `Base.metadata.create_all()` on startup.
- Migration tooling (Alembic) is deferred until the first breaking schema change post-v1.

### 4.4 Frontend

- Server-rendered Jinja2 templates.
- **HTMX** for partial updates. No JS framework, no bundler, no build step.
- **Italian throughout:** all labels, buttons, page titles, headings, tooltips, and error messages user-visible in the browser are in Italian.
- **Mobile-usable:** the planner grid and shopping list must be readable and interactive at 375px width.

### 4.5 Reliability

- The app must never lose the user's data on a graceful container restart. All persistent state lives in the mounted SQLite file.
- Invalid input (missing fields, duplicate names, deleting a used ingredient) returns a clear Italian error message in the UI, not a 500.

## 5. Domain model

- **Ingredient**(`id`, `name` UNIQUE CI)
- **Recipe**(`id`, `name` UNIQUE, `notes` NULLABLE)
- **RecipeIngredient**(`id`, `recipe_id` FK→Recipe, `ingredient_id` FK→Ingredient) — UNIQUE(`recipe_id`, `ingredient_id`)
- **PlannedMeal**(`id`, `year`, `week`, `day` 0–6, `slot` IN {lunch, dinner}, `recipe_id` FK→Recipe) — UNIQUE(`year`, `week`, `day`, `slot`)
- **MealPlanTemplate**(`id`, `name` UNIQUE CI)
- **TemplateSlot**(`id`, `template_id` FK→MealPlanTemplate, `day` 0–6, `slot` IN {lunch, dinner}, `recipe_id` FK→Recipe) — UNIQUE(`template_id`, `day`, `slot`)
- **ManualShoppingItem**(`id`, `name`, `checked` BOOL, `created_at`)
- **ShoppingCheck**(`id`, `year`, `week`, `ingredient_id` FK→Ingredient) — UNIQUE(`year`, `week`, `ingredient_id`). Presence of a row means the corresponding derived ingredient is checked for that week. Auto-scoped: viewing a different week shows a different set of checks.

Cascading deletes: deleting a `Recipe` removes its `RecipeIngredient`, `PlannedMeal`, and `TemplateSlot` rows. Deleting a `MealPlanTemplate` removes its `TemplateSlot` rows. Deleting an `Ingredient` removes matching `ShoppingCheck` rows (rare, since delete is blocked while in use by recipes).

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
- Language switcher / multilingual UI (Italian is hardcoded).
- Breakfast slot (user manages breakfast on their own).
- Overwriting existing planned meals when applying a template (fill-empty-only is the contract).

## 7. Acceptance criteria

1. **Recipe entry friction test:** creating a new recipe with 5 new-to-the-system ingredients takes ≤ 30 seconds and never blocks on a modal.
2. **End-to-end plan → shopping:** create 3 recipes with overlapping ingredients → plan them across Mon/Wed/Fri dinner of the current week → `/shopping` derived section shows the union of their ingredients, deduped and sorted, each with an unchecked checkbox. Add a manual item "detersivo piatti" → it appears only in the manual section. Check one derived item → it grays out and sinks to the bottom of its section; navigating to next week shows all derived items unchecked again.
3. **Container persistence:** `docker run` with a mounted `/data` volume; create a recipe; restart the container; recipe is still there.
4. **Login:** with `MENUAPP_USER`/`MENUAPP_PASSWORD` set, visiting any protected page redirects to `/login`; correct credentials log you in and return you to the original page; `/healthz` is reachable without login; session survives a browser restart within 30 days.
5. **Import/export round-trip:** export → wipe DB → import via the `/import` upload page → recipes, ingredients, and templates are identical (order-insensitive). Importing a template whose recipes are missing succeeds and reports the orphaned slots on the summary.
6. **Template apply:** create a template with recipes on Mon lunch and Wed dinner → on a week with an existing meal on Mon lunch, apply the template → Mon lunch is unchanged; Wed dinner is populated from the template.
