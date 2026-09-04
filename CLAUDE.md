# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Source of truth

**Read [`SPEC.md`](./SPEC.md) first.** It is the authoritative specification for what this app must do. Every implementation decision must be traceable to a requirement there. If a task appears to require something the spec doesn't cover — or contradicts — **stop and update `SPEC.md` first, with the user's approval**, before writing code. Do not silently expand scope.

CLAUDE.md (this file) is guidance for *how* to work in the repo; SPEC.md is the contract for *what* to build.

## Status

v1 feature-complete against `SPEC.md`. All six phases (recipes+ingredients CRUD, planner, shopping, templates, login+import/export, merge+tests+docker) landed. Test suite: `pytest -q` runs 25 tests, all green. Docker acceptance cycle (build → run with mounted volume + auth env → login → create recipe → restart → verify persistence) verified against `docker run` on port 18000. The sections below describe the actual architecture as built.

## Working conventions for this repo

- **Python environment:** always use the project venv at `.venv/`. Run Python and pip via `.venv/bin/python` and `.venv/bin/pip` (or activate with `source .venv/bin/activate`). Do not install packages into the system Python.
- **Containerization:** the app must remain buildable and runnable via the root `Dockerfile`. Any new runtime dependency or filesystem expectation (env vars, mount points, exposed ports) must be reflected there.
- **Git cadence:** commit after each substantial modification — a new feature, a non-trivial refactor, a dependency change, initial scaffolding of a subsystem. Small in-progress edits can be batched into the next substantial commit. Never touch `git config` in this repo (the user's global config is authoritative).

## Purpose (see SPEC.md for the authoritative version)

Self-hosted webapp for personal meal planning. Core capabilities:

1. **Recipe library** — name + **required type** (fixed enum: antipasto/primo/secondo/contorno/frutta/dolce/altro) + optional notes + a **set of ingredient names**. No quantities, no units.
2. **Weekly planner** — recipes assigned to fixed slots **{lunch, dinner}** on an ISO year+week grid (no breakfast). Each cell can hold **multiple recipes** — natural for the Italian multi-course meal. The same recipe cannot appear twice in one cell.
3. **Reusable weekly templates** — named plans that can be applied to a specific week; applying **only fills fully empty cells** (no partial merge), never overwrites.
4. **Shopping list** — two independent sections shown together:
   - **Derived** from the plan, each item with a checkbox scoped to `(year, week)`. New week ⇒ fresh empty check state (auto-reset by design).
   - **Manual** pantry list, persistent, independent of any week.
5. **Import page + export** for recipes, ingredients, and templates as JSON.

All user-facing text is **Italian**. Code, comments, and log messages stay in English.

## Tech stack

- **Backend:** Python + FastAPI
- **Database:** SQLite (single file, no external DB server)
- **Templating:** Jinja2 (server-rendered HTML)
- **Frontend interactivity:** HTMX for partial updates; minimal-to-zero custom JS
- **Deployment target:** self-hosted on a small web server (single-user, no auth planned initially)

The stack was chosen to stay lightweight — one Python process, one SQLite file, no build step, no JS framework.

## Development commands

Local (venv):
- Install / update deps: `.venv/bin/pip install -r requirements.txt`
- Run dev server: `.venv/bin/uvicorn app.main:app --reload`
- Run tests: `.venv/bin/pytest` _(pytest not yet in requirements — add when tests are introduced)_
- Run a single test: `.venv/bin/pytest path/to/test_file.py::test_name`
- DB migrations: TBD (Alembic if the schema outgrows hand-written SQL)

Docker:
- Build: `docker build -t meal-planner .`
- Run: `docker run -p 8000:8000 -v $(pwd)/data:/data meal-planner`
  (SQLite database persists in the host `./data` directory via the `/data` volume; path is set by `MENUAPP_DB_PATH`.)

## Architecture — the big picture

### Domain model (see SPEC.md §5 for canonical definitions)

- `Ingredient` — canonical, deduplicated by name (case-insensitive).
- `Recipe` — name + **required type (fixed enum)** + optional notes. See `RECIPE_TYPES` / `RECIPE_TYPE_LABELS` in `app/i18n.py`.
- `RecipeIngredient` — join table (recipe_id, ingredient_id). No quantity, no unit. Unique per (recipe, ingredient).
- `PlannedMeal` — (year, week, day, slot, recipe). Unique per (year, week, day, slot, **recipe_id**) — one cell holds many recipes, only same-recipe duplication is blocked.
- `MealPlanTemplate` + `TemplateSlot` — same shape as `PlannedMeal` but without (year, week). Templates get "applied" to a week and fill only **fully empty** cells (skip cell if any dish is already there).
- `ManualShoppingItem` — persistent pantry item (name, checked flag). Not tied to any week.
- `ShoppingCheck` — (year, week, ingredient_id). Presence of a row = that derived ingredient is checked for that week. Per-week scoping is what gives the "auto-reset on new week" behavior for free.

**Never merge** the derived and manual shopping sections. See SPEC.md §3.5.

### Auth (see SPEC.md §4.2)

Form-based login with a signed session cookie (Starlette `SessionMiddleware`), credentials from `MENUAPP_USER` / `MENUAPP_PASSWORD`. If either env var is unset at startup, auth is fully bypassed and a warning is logged — this is the dev mode. `MENUAPP_SESSION_SECRET` signs the cookie; generated at startup with a warning if unset. `/healthz`, `/login`, `/logout`, and `/static/*` are always unauthenticated.

### Suggested layout

```
app/
  main.py            # FastAPI app, route registration
  db.py              # SQLite connection / session helpers
  models.py          # SQLAlchemy (or dataclass) models
  routes/            # One module per feature: recipes, planner, shopping
  templates/         # Jinja2 templates; HTMX partials live alongside full pages
  static/            # CSS, minimal JS
tests/
```

Routes should return full HTML pages for direct navigation and HTML **fragments** for HTMX-triggered requests. The convention: a request with header `HX-Request: true` gets the fragment; otherwise the full page. Keep partial templates small and composable so the same fragment can be rendered from multiple routes.

### Data flow for the shopping list (reference)

`GET /shopping/{year}/{week}` →
- **Derived section:** `SELECT DISTINCT ingredient.id, ingredient.name FROM planned_meals JOIN recipe_ingredients ON ... JOIN ingredients ON ... WHERE year=? AND week=? ORDER BY ingredient.name`. Then LEFT JOIN `ShoppingCheck` on `(year, week, ingredient_id)` to determine each item's checkbox state. Sort checked items to the bottom in the template.
- **Manual section:** load all `ManualShoppingItem` rows.

Both rendered in `shopping/index.html` as two distinct sections. Toggling a derived checkbox is `POST /shopping/{year}/{week}/check/{ingredient_id}` (creates a `ShoppingCheck` row) / `DELETE ...` (removes it). Manual items use `POST/DELETE /shopping/manual/...` and only ever touch `ManualShoppingItem`.

### Template application (reference)

`POST /planner/{year}/{week}/apply` with form field `template_id` → group the template's slots by `(day, slot)`; for each group, check whether the target week already has ANY `PlannedMeal` for that `(day, slot)`. If empty, insert all the template's recipes for that cell. If non-empty, skip the whole cell (no partial merge — see SPEC.md §3.4). Never `INSERT OR REPLACE`.
