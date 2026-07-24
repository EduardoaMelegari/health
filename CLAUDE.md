# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Single-user web app (Flask + SQLite, **no ORM**) for one person's fat-loss plan: daily
checklist, meal library + food diary, weekly weigh-ins, workout load tracking, and a
Claude-powered "coach". No auth — built for a LAN / reverse proxy.

**Everything user-facing is Brazilian Portuguese** — UI copy, code comments, commit
messages, and the coach. Keep new strings and comments in pt-BR to match.

## Commands

```bash
# Local dev (serves http://localhost:8080, debug=True, auto-reload)
pip install -r requirements.txt
python app.py

# Seed/migrate the DB without starting the server
python seed.py

# Reset all data: stop the app, delete data/health.db, restart — seed.run() re-creates
# and re-populates it on the next boot (called at import time in app.py).

# Production (host port 8457 → container 8080, gunicorn 2×gthread, timeout 300s —
# the coach's agentic loop can exceed gunicorn's 30s default)
docker compose up -d --build
```

There is **no test suite and no linter/formatter** configured — don't invent commands for
them. Verify changes by running `python app.py` and exercising the affected page/endpoint.

Coach needs `ANTHROPIC_API_KEY` in the environment (optional `ANTHROPIC_MODEL`, default
`claude-sonnet-5`). Without it the app runs fine and only the Coach tab is disabled.
`DB_PATH` overrides the SQLite location (Docker sets it to `/app/data/health.db`).

## Architecture

Six Python modules, no packages:

- **`app.py`** — Flask app: page routes render Jinja templates; `/api/*` are JSON POST
  endpoints called by `static/app.js`; `/export/*.csv` stream CSV. Also holds the
  weekday→workout schedule constants. `seed.run()` runs on import (bottom of the file).
- **`actions.py`** — the **shared data layer**. Every function takes an explicit sqlite
  `conn` and commits its own writes.
- **`coach.py`** — the Anthropic tool-use agent.
- **`db.py`** — schema, `connect()`, and an idempotent `migrate()`.
- **`seed.py`** — idempotent seed of the original plan (the source of truth for defaults).

### The rule that matters most: put data logic in `actions.py`

`actions.py` is consumed by **both** the HTTP routes in `app.py` **and** the coach's tools
in `coach.py`. Every meaningful read/mutation (log weight, save sets, edit a meal option,
compute macros, build progress/plan snapshots) lives there so the two front doors stay in
sync. When adding a capability, write the logic once in `actions.py`, then expose it as a
route and (if the coach should do it) as a tool — don't duplicate SQL in a route handler.

### Coach = tool-use over that same data layer

`coach.py` defines `TOOLS` (JSON schemas) whose `_dispatch()` cases call `actions.py`
functions. Two entry points:
- **`chat()`** — full agentic loop (`MAX_TOOL_ITERATIONS=8`, adaptive thinking). History
  is persisted in the `chat_message` table: `content_json` holds the raw API blocks for
  replay, `text` holds the human-readable line for the UI. `reset()` soft-deletes via
  `active=0`. `_api_history()` reloads the last `HISTORY_LIMIT` messages and trims any
  orphan `tool_result` at the window start. Thinking blocks are dropped before persisting.
  The system prompt is `SYSTEM_BASE` (cached, ephemeral) + a live progress snapshot.
- **`quick_log()`** — single-shot structured-output call (json_schema, thinking disabled)
  behind the "quick log" food box on the Hoje page; no history, cheaper.

### Domain model — two concepts that are easy to conflate

1. **Meal library vs. food diary.** The Dieta tab (`meal` → `meal_option` → `meal_item`)
   is a **library of recommendations** with *reference* macros — what to eat, not what was
   eaten. The **`food_log`** table is the real daily diary. All "consumed today" numbers
   come from `food_log` (`macros_for_date`), never from the library. Logging a
   recommendation copies its macros into `food_log` (`log_food_from_option`). The coach
   system prompt leans on this distinction heavily — preserve it.

2. **Cooked weight vs. raw weight.** `meal_item.grams` and all item macros are in *cooked*
   ("pronto") weight. `raw_factor` converts back to raw for the shopping list only
   (~0.75 for meats, 1.0 otherwise). Don't mix the two.

### Other cross-file rules

- **Schedule is weekday-driven.** `WORKOUT_BY_WEEKDAY = {0:"A", 2:"B", 4:"C"}` and
  `RUN_DAYS = {1,3}` (Mon=0). `task_template.weekdays` is a comma-separated string of
  weekday ints. `day_type` (treino vs. descanso, weekend≥5) selects which kcal/carb target
  applies via `targets_for`.
- **Weight trend uses a 4-point moving average**, not raw points, to smooth daily
  water/gut swings — rate, ETA to milestone, and the chart line all derive from it.
- **`config` table** is key→value strings (targets, milestones, height, `start_date`,
  `review_days`). Editable at runtime by the coach's `update_targets` or any SQLite client;
  `seed.py` inserts defaults with `INSERT OR IGNORE` so it never overwrites live edits.
- **Exercise `kind`** is `'weight'` (kg×reps) or `'time'` (isometric seconds, e.g. plank —
  `target_reps` means seconds). Progression suggestion is +2.5 kg vs. +5 s. New columns on
  existing tables must be added in `db.migrate()` (`CREATE TABLE IF NOT EXISTS` won't).
- **Soft vs. hard delete:** exercises and meal options soft-delete (`active=0`, reversible
  in the UI); meal items and food-log entries hard-delete.
- **`meal.shopping`** (0/1) marks which meals enter the weekly shopping list — "Extra" is 0.
  Don't rely on meal order/index for that.
- **SQLite runs in WAL mode** (`db.connect()`) with `busy_timeout` — required for the two
  gunicorn workers. `db.backup()` writes a daily `VACUUM INTO` copy to `data/backups/`
  (keeps 14), triggered by a `before_request` hook in `app.py`.
- **Coach history hardening:** `_api_history()` drops orphan `tool_result` at the window
  start AND neutralizes dangling `tool_use` (process killed mid-loop) — otherwise the API
  rejects every later request that day. Keep both when touching history code.

## Conventions

- Raw parametrized SQL with `conn.row_factory = sqlite3.Row` — no ORM, no query builder.
- CSV export (`app.py:csv_response`): `;` delimiter, `.`→`,` on floats, UTF-8 BOM, for
  Excel pt-BR.
- Frontend is a vanilla-JS `App` object (`static/app.js`), no build step; Chart.js is
  vendored (`static/chart.umd.js`). Templates extend `base.html`; theme is persisted in
  `localStorage`.
