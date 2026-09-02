# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Greenfield repository — project scaffolding (venv, `requirements.txt`, `Dockerfile`, `.gitignore`) is in place, but no application code exists yet. The sections below describe the **intended** architecture agreed with the user before implementation began. Update this file as reality diverges from the plan.

## Working conventions for this repo

- **Python environment:** always use the project venv at `.venv/`. Run Python and pip via `.venv/bin/python` and `.venv/bin/pip` (or activate with `source .venv/bin/activate`). Do not install packages into the system Python.
- **Containerization:** the app must remain buildable and runnable via the root `Dockerfile`. Any new runtime dependency or filesystem expectation (env vars, mount points, exposed ports) must be reflected there.
- **Git cadence:** commit after each substantial modification — a new feature, a non-trivial refactor, a dependency change, initial scaffolding of a subsystem. Small in-progress edits can be batched into the next substantial commit. Never touch `git config` in this repo (the user's global config is authoritative).

## Purpose

Self-hosted webapp for personal meal planning with three core capabilities:

1. **Recipe library** — create/edit meals, each composed of ingredients with quantity + unit.
2. **Weekly menu planner** — assign recipes to slots on a weekly calendar (day × meal-slot).
3. **Shopping list** — two parts merged into one view:
   - **Derived part:** consolidated ingredient list computed from the meals planned for a given week, aggregating quantities across recipes and (when possible) across units.
   - **Manual part:** a persistent list of recurring/pantry items the user adds, removes, and manages by hand (e.g. milk, coffee, dish soap). Independent of any week's plan.

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
- Build: `docker build -t menuapp .`
- Run: `docker run -p 8000:8000 -v $(pwd)/data:/data menuapp`
  (SQLite database persists in the host `./data` directory via the `/data` volume; path is set by `MENUAPP_DB_PATH`.)

## Architecture — the big picture

### Domain model

The three features are unified by a small domain that a future Claude should internalize before editing:

- `Ingredient` — a canonical pantry item (name, default unit). Deduplicated so the shopping list can aggregate.
- `Recipe` — a named meal with a collection of `RecipeIngredient` rows (recipe_id, ingredient_id, quantity, unit).
- `MenuPlan` / `PlannedMeal` — a week (ISO year+week) containing entries that assign a `Recipe` to a (day, slot) tuple, e.g. `(Monday, dinner) → Lasagna`.
- `ManualShoppingItem` — a persisted, user-managed pantry/recurring item (name, quantity, unit, optional "checked" flag). CRUD lives with the user, not with any week.
- `ShoppingList` — the composite view. **Not stored as a single entity.** For a given week it is the union of:
  1. the **derived** aggregate over that week's `PlannedMeal` → `RecipeIngredient` rows, and
  2. the current set of `ManualShoppingItem` rows.

   The two parts should remain visually and logically separable in the UI so the user always knows which items came from the plan vs. which they added themselves. When an ingredient appears in both (e.g. "olive oil" is a recurring pantry item *and* used by this week's recipes), do **not** silently merge them — surface both and let the user reconcile. Silent merging hides intent and makes the manual list feel unreliable.

### Unit aggregation

Aggregating ingredients across recipes is the one non-trivial piece of logic. Two ingredients aggregate cleanly only when their units match (or are convertible: g↔kg, ml↔l). Design the aggregator so incompatible units for the same ingredient produce **two separate line items** rather than a silent error — the shopping list is user-facing and must degrade gracefully.

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

`GET /shopping/{year}/{week}` → (a) load `PlannedMeal` rows for the week, join `RecipeIngredient`, group by `(ingredient_id, unit)`, sum quantities — this is the **derived** section; (b) load all `ManualShoppingItem` rows — this is the **manual** section. Render both in `shopping_list.html` as two distinct sections. The derived section is read-only for that week; the manual section supports add/remove/check via HTMX endpoints (`POST/DELETE /shopping/manual/...`) that only ever touch `ManualShoppingItem`.
