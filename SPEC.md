# Meal Planner — Specification

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
- A recipe has: **name** (unique across all recipes), **type** (required, see below), optional **notes** (free-text), and a **set of ingredients**.
- **Type** is required and must be one of the fixed enum values: `antipasto`, `primo`, `secondo`, `contorno`, `frutta`, `dolce`, `altro`. The recipe form does not submit without a type.
- Type is a portable label — used to sort/badge recipes and (when combined with the planner) makes multi-dish slots readable. Not used as a slot-level constraint (see §3.3).
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
- Each `(year, week, day, slot)` cell can hold **zero or more recipes** (e.g. a *primo* + a *contorno* + a *frutta*). There is **no cap** and no per-type restriction — you can even plan two *primi* if that's how you actually eat.
- The same recipe cannot be added twice to the same cell (enforced by `UNIQUE(year, week, day, slot, recipe_id)`); attempting to add a duplicate is a silent no-op.
- Actions: add a recipe to a slot; remove a specific recipe from a slot.
- Dishes within a cell render sorted by recipe type in the canonical order (antipasto → primo → secondo → contorno → frutta → dolce → altro), then by recipe name.
- Navigation: previous week, next week, jump to the current week.
- The current week (`/planner`) redirects to the ISO week containing today.

### 3.4 Weekly plan templates

- Named, reusable weekly plans (e.g. "settimana standard", "settimana estiva").
- CRUD: create, list, edit, delete templates.
- A template has: **name** (unique across templates) and a set of `(day, slot, recipe)` entries under the same rules as §3.3 (fixed slots {lunch, dinner}, multiple recipes per cell allowed, same recipe cannot appear twice in one cell).
- **Apply to week:** on the planner, the user selects a template and a target week. For each `(day, slot)` in the template, the template's recipes are inserted into that cell **only if the target cell is fully empty** (zero existing dishes). If the target cell has even one dish, the entire cell is skipped — no partial merging. Deliberately non-destructive.
- Template editing UI mirrors the planner grid but is week-agnostic.
- Deleting a recipe cascades to `TemplateSlot` rows the same way it cascades to `PlannedMeal` rows.

### 3.5 Shopping list (supermarket view)

- URL: `/shopping/{year}/{week}` (root `/shopping` redirects to the current week).
- **Purpose:** a single unified list of everything to buy for the week, meant to be used at the supermarket. Read-only apart from the checkboxes.
- **Content:** the union of
  a) distinct ingredient names appearing in any recipe planned for that week (§3.3), and
  b) every entry from the pantry (§3.6).
  Deduplicated by name (case-insensitive) — an item present in both sources shows up **once**.
- **Grouped by supermarket department** in the fixed store-flow order below. Only departments with at least one item are shown. Department per name comes from the keyword table in `app/ingredient_emoji.py`; unknowns fall into **Altro**. Fixed order:
  1. Frutta e verdura
  2. Panetteria
  3. Pasta e riso
  4. Latticini e uova
  5. Salumi
  6. Carne
  7. Pesce
  8. Surgelati
  9. Scatolame e conserve
  10. Condimenti
  11. Dolci
  12. Bevande
  13. Casa e pulizia
  14. Altro
- **Checkbox behavior:**
  - Each item has one checkbox. Check state is scoped by `(year, week, name)` — a new ISO week naturally shows every item unchecked (auto-reset by design; no cron).
  - Checked items sort to the bottom of their department block and render grayed out / struck through.
- **Nothing else:** the page does **not** allow adding items, removing items, or editing anything. Adding recurring pantry items happens in §3.6; ingredient-name typos are fixed by editing the recipe (§3.1).

### 3.6 Pantry (voci manuali)

- URL: `/pantry`.
- Flat, week-independent list of recurring names the user always wants on the shopping list — e.g. `caffè`, `detersivo piatti`, `carta igienica`.
- Actions: **add** (name only), **rename**, **delete**. **No check state, no department grouping** — this page is just for management, not for shopping.
- Names are case-insensitive-unique across the pantry (`caffè` and `Caffè` are the same entry).
- Every pantry name automatically appears in the shopping list (§3.5), grouped into the department its keywords match.

### 3.7 Import and export

- **Dedicated import page** at `/import` with a file upload form. Shows a per-import result summary (created / skipped / errored counts by entity type).
- **Export** `GET /export`: downloads a JSON file. Format:
  ```json
  {
    "ingredients": ["sale", "olio d'oliva", "..."],
    "recipes": [
      {"name": "Lasagna", "type": "primo", "notes": "...", "ingredients": ["pasta", "manzo"]}
    ],
    "templates": [
      {
        "name": "settimana standard",
        "slots": [
          {"day": 0, "slot": "lunch", "recipe": "Lasagna"},
          {"day": 0, "slot": "lunch", "recipe": "Insalata"},
          {"day": 0, "slot": "dinner", "recipe": "Zuppa"}
        ]
      }
    ]
  }
  ```
  Note: template slots for the same `(day, slot)` may repeat — that is how a template records multiple dishes for one cell.
- **Excludes** the weekly plan, manual shopping items, and derived-ingredient checkboxes — those are ephemeral state, not portable content.
- **Import** `POST /import` (multipart file upload): upserts by name, never silently overwrites.
  - **Ingredients:** create if missing.
  - **Recipes:** skip if a recipe with that name already exists. Recipes without a valid `type` field are counted as `invalid_rows` and their dependent template slots become orphaned.
  - **Templates:** skip if a template with that name already exists.
  - **Template slots referencing an unknown recipe:** skip that slot and count it in an `orphaned_slots` figure on the summary page. Do not fail the whole import.

## 4. Non-functional requirements

### 4.1 Deployment

- Buildable and runnable from the root `Dockerfile`.
- Single container image, single SQLite file mounted at `/data` via a host volume.
- Database path from `MENUAPP_DB_PATH` (default `/data/menuapp.db` in-container; a local relative path for dev outside Docker).
- Runs as a single `uvicorn` process. No workers, no external services.
- **Turn-key deployment** via:
  - `docker-compose.yml` at the repo root, reading `./​.env` (`.env.example` is committed as a template). Compose refuses to start if `MENUAPP_PASSWORD` or `MENUAPP_SESSION_SECRET` are empty.
  - `scripts/install-apache-config.sh` + `scripts/meal-planner.conf.template` — installs an Apache reverse-proxy config that mounts the app at `/meal-planner` on the machine's IP (no domain assumed). Renders port and root path from env into `/etc/apache2/conf-available/meal-planner.conf`, enables the required modules, reloads Apache.
- **Sub-path proxying** is supported natively via the `MENUAPP_ROOT_PATH` env var. When set, templates prefix all internal URLs with it and outgoing `Location` headers get the prefix (via `app/middleware.py`). Unset (dev) → transparent no-op.

### 4.2 Authentication

- Single-user app → **single master password**, no usernames.
- **Form-based login page** at `/login` with a single password field. Not HTTP Basic Auth.
- The master password comes from the `MENUAPP_PASSWORD` environment variable.
- **Session:** signed cookie via Starlette `SessionMiddleware`, 30-day expiry, `HttpOnly`, `SameSite=Lax`, `Secure` when served over HTTPS. Cookie survives browser restarts within its TTL.
- **Session signing key:** `MENUAPP_SESSION_SECRET` env var. If unset, a random key is generated at startup and a warning is logged; sessions do not survive process restarts in that case.
- **Logout** at `/logout` clears the session and redirects to `/login`.
- Auth gates every route except `/login`, `/logout`, `/healthz`, and `/static/*`.
- Unauthenticated requests to protected routes redirect to `/login?next=<original path>` and are returned to `next` after login.
- **Development bypass:** if `MENUAPP_PASSWORD` is unset, auth is bypassed entirely (login page still exists but accepts any input, and all routes are open) and a warning is logged at startup.
- Password comparison is constant-time on the sha256 digest so it works with any Unicode input.

### 4.3 Persistence

- SQLite. Schema created by SQLAlchemy `Base.metadata.create_all()` on startup.
- Migration tooling (Alembic) is deferred until the first breaking schema change post-v1.

### 4.4 Frontend

- Server-rendered Jinja2 templates.
- **HTMX** for partial updates. No JS framework, no bundler, no build step.
- **Italian throughout:** all labels, buttons, page titles, headings, tooltips, and error messages user-visible in the browser are in Italian.
- **Mobile-usable:** the planner grid and shopping list must be readable and interactive at 375px width.
- **Emoji hints:**
  - Every recipe type carries a fixed emoji (rendered next to the label in badges and pickers).
  - Ingredient names are auto-decorated with an emoji picked from a hand-maintained Italian keyword table (whole-word, accent-insensitive match). The lookup is presentation-only — nothing is stored in the DB. Names without a keyword match render without an emoji.

### 4.5 Reliability

- The app must never lose the user's data on a graceful container restart. All persistent state lives in the mounted SQLite file.
- Invalid input (missing fields, duplicate names, deleting a used ingredient) returns a clear Italian error message in the UI, not a 500.

## 5. Domain model

- **Ingredient**(`id`, `name` UNIQUE CI)
- **Recipe**(`id`, `name` UNIQUE, `type` NOT NULL IN {antipasto, primo, secondo, contorno, frutta, dolce, altro}, `notes` NULLABLE)
- **RecipeIngredient**(`id`, `recipe_id` FK→Recipe, `ingredient_id` FK→Ingredient) — UNIQUE(`recipe_id`, `ingredient_id`)
- **PlannedMeal**(`id`, `year`, `week`, `day` 0–6, `slot` IN {lunch, dinner}, `recipe_id` FK→Recipe) — UNIQUE(`year`, `week`, `day`, `slot`, `recipe_id`) — a cell can hold multiple recipes; only duplicates of the same recipe in the same cell are blocked.
- **MealPlanTemplate**(`id`, `name` UNIQUE CI)
- **TemplateSlot**(`id`, `template_id` FK→MealPlanTemplate, `day` 0–6, `slot` IN {lunch, dinner}, `recipe_id` FK→Recipe) — UNIQUE(`template_id`, `day`, `slot`, `recipe_id`) — same reasoning as `PlannedMeal`.
- **PantryItem**(`id`, `name` UNIQUE CI, `created_at`) — user-managed recurring shopping names (§3.6). No check state (checks live in `ShoppingCheck`, per week).
- **ShoppingCheck**(`id`, `year`, `week`, `name` NoCaseString) — UNIQUE(`year`, `week`, `name`). Presence = the item with that name is checked for that week. Keyed by **name**, not by any FK, so it works for both derived ingredients and pantry items uniformly. Auto-scoped: viewing a different week shows a different set of checks.

Cascading deletes: deleting a `Recipe` removes its `RecipeIngredient`, `PlannedMeal`, and `TemplateSlot` rows. Deleting a `MealPlanTemplate` removes its `TemplateSlot` rows. Deleting an `Ingredient` removes matching `ShoppingCheck` rows (rare, since delete is blocked while in use by recipes).

## 6. Out of scope (v1)

Explicit non-goals — do **not** add these without updating the spec first:

- Quantities and units on ingredients.
- Servings / portion scaling.
- Multi-user, accounts, roles.
- Nutritional information.
- Recipe search, tagging, cuisines beyond the fixed type enum, ratings, favorites.
- User-editable recipe type list (the type enum is hardcoded).
- Per-type slot caps in the planner (a cell can hold multiple dishes of the same type).
- Grocery-store integrations.
- Native or PWA mobile app.
- Migration tooling.
- Undo / soft-delete.
- Language switcher / multilingual UI (Italian is hardcoded).
- Breakfast slot (user manages breakfast on their own).
- Overwriting existing planned meals when applying a template (fill-empty-only, at the cell level, is the contract).

## 7. Acceptance criteria

1. **Recipe entry friction test:** creating a new recipe with 5 new-to-the-system ingredients takes ≤ 30 seconds and never blocks on a modal.
2. **End-to-end plan → shopping:** create 3 recipes with overlapping ingredients → plan them across Mon/Wed/Fri dinner of the current week → `/shopping` shows the union of their ingredients, deduped, grouped by department, each with an unchecked checkbox, no add form. Add a pantry item "detersivo piatti" from `/pantry` → it also appears on `/shopping` in the Casa e pulizia department. Check one item → it grays out and sinks to the bottom of its department; navigating to next week shows every item unchecked again.
3. **Container persistence:** `docker run` with a mounted `/data` volume; create a recipe; restart the container; recipe is still there.
4. **Login:** with `MENUAPP_USER`/`MENUAPP_PASSWORD` set, visiting any protected page redirects to `/login`; correct credentials log you in and return you to the original page; `/healthz` is reachable without login; session survives a browser restart within 30 days.
5. **Import/export round-trip:** export → wipe DB → import via the `/import` upload page → recipes, ingredients, and templates are identical (order-insensitive). Importing a template whose recipes are missing succeeds and reports the orphaned slots on the summary.
6. **Template apply:** create a template with `[primo + contorno]` on Mon lunch and one recipe on Wed dinner → on a week with an existing meal on Mon lunch, apply the template → Mon lunch is unchanged (both template dishes skipped, not just the primo); Wed dinner is populated from the template.
7. **Multi-dish slot:** in a single planner cell, add a primo, a contorno, and a frutta → all three render sorted by type. The same recipe cannot be added twice; attempting to do so is a silent no-op.
