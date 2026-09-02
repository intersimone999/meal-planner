# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Source of truth

**Read [`SPEC.md`](./SPEC.md) first.** It is the authoritative specification for what this app must do. Every implementation decision must be traceable to a requirement there. If a task appears to require something the spec doesn't cover — or contradicts — **stop and update `SPEC.md` first, with the user's approval**, before writing code. Do not silently expand scope.

CLAUDE.md (this file) is guidance for *how* to work in the repo; SPEC.md is the contract for *what* to build.

## Status

Greenfield repository — project scaffolding (venv, `requirements.txt`, `Dockerfile`, `.gitignore`) and a stub FastAPI skeleton with placeholder routes are in place. Feature implementation has not begun. The sections below describe the **intended** architecture aligned with `SPEC.md`. Update this file as reality diverges from the plan.

## Working conventions for this repo

- **Python environment:** always use the project venv at `.venv/`. Run Python and pip via `.venv/bin/python` and `.venv/bin/pip` (or activate with `source .venv/bin/activate`). Do not install packages into the system Python.
- **Containerization:** the app must remain buildable and runnable via the root `Dockerfile`. Any new runtime dependency or filesystem expectation (env vars, mount points, exposed ports) must be reflected there.
- **Git cadence:** commit after each substantial modification — a new feature, a non-trivial refactor, a dependency change, initial scaffolding of a subsystem. Small in-progress edits can be batched into the next substantial commit. Never touch `git config` in this repo (the user's global config is authoritative).

## Purpose (see SPEC.md §1–§3 for the authoritative version)

Self-hosted webapp for personal meal planning with three core capabilities:

1. **Recipe library** — create/edit meals, each with a name, optional notes, and a **set of ingredient names**. No quantities, no units — recipes must be trivial to add.
2. **Weekly menu planner** — assign recipes to fixed slots (breakfast/lunch/dinner) on a weekly calendar keyed by ISO year+week.
3. **Shopping list** — two independent sections shown side by side:
   - **Derived:** the distinct, sorted set of ingredient names appearing in any recipe planned for the selected week.
   - **Manual:** a persistent list of recurring/pantry items the user manages by hand. Independent of any week's plan.

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

### Domain model (see SPEC.md §5 for the canonical definitions)

- `Ingredient` — canonical, deduplicated by name (case-insensitive).
- `Recipe` — name + optional notes.
- `RecipeIngredient` — join table only (recipe_id, ingredient_id). No quantity, no unit. Unique per (recipe, ingredient).
- `PlannedMeal` — (year, week, day, slot, recipe). Unique per (year, week, day, slot); a slot holds at most one recipe.
- `ManualShoppingItem` — persistent, user-managed pantry item (name, checked flag). Not tied to any week.

The shopping list is **derived on the fly** for the "from the plan" section and **read directly** for the manual section. Never merge the two sections — see SPEC.md §3.4.

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

`GET /shopping/{year}/{week}` → (a) `SELECT DISTINCT ingredient.name FROM planned_meals JOIN recipe_ingredients ON ... JOIN ingredients ON ... WHERE year=? AND week=? ORDER BY ingredient.name` — this is the **derived** section; (b) load all `ManualShoppingItem` rows — this is the **manual** section. Render both in `shopping/index.html` as two distinct sections. The derived section is read-only for that week; the manual section supports add/toggle/delete via HTMX endpoints (`POST/DELETE /shopping/manual/...`) that only ever touch `ManualShoppingItem`.
