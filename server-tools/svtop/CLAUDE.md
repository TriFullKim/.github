# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

svtop is a server monitoring dashboard that collects CPU, RAM, GPU, and disk metrics from remote Linux servers via SSH (Paramiko), stores them in SQLite, and displays them through a FastAPI web dashboard with Chart.js time-series graphs. It optionally syncs metrics to a Notion database.

## Running the App

```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run (starts on port 8000)
python app.py
# or
uvicorn app:app --host 0.0.0.0 --port 8000
```

On first launch, if a server in `config.yaml` has no SSH key or encrypted password, the app prompts interactively for the SSH password and writes `password_encrypted` back to config.yaml.

## Architecture

**Backend (Python):**
- `app.py` — FastAPI app, APScheduler setup, API endpoints, lifespan management. Config is loaded from `config.yaml` at module level. The scheduler calls `run_collection()` at the configured interval.
- `collector.py` — SSH into each server, runs shell commands (`top`, `free`, `df`, `ps aux`, `nvidia-smi`, `who`), parses output with regex. All parsing functions (`parse_cpu`, `parse_ram`, `parse_gpu`, `parse_disk`, `parse_processes`, `parse_users`) are standalone and testable.
- `database.py` — Thread-safe SQLite wrapper using `threading.local()` for per-thread connections. WAL mode enabled. Three tables: `metrics`, `processes`, `logged_users` (with foreign keys and cascade deletes).
- `crypto_util.py` — Fernet symmetric encryption for SSH passwords. Key stored in `.secret_key` (gitignored, mode 0600).
- `notion_sync.py` — Optional Notion integration that upserts server metrics as Notion database pages. Only active when `notion.enabled: true` in config. Requires `notion-client` pip package.

**Frontend:**
- `templates/index.html` — Single-page Jinja2 template with Korean UI text
- `static/dashboard.js` — Client-side logic: fetches `/api/*` endpoints, renders Chart.js time-series, auto-refreshes every 30 seconds
- `static/style.css` — Dark theme with CSS variables

**API Endpoints:**
- `GET /api/servers` — List all known servers
- `GET /api/metrics/{server_name}?hours=N` — Time-series data (1-720 hours)
- `GET /api/latest/{server_name}` — Latest snapshot with processes and users
- `POST /api/collect` — Trigger manual collection (runs in background thread)
- `GET /api/config` — Expose non-sensitive config info

## Key Config

`config.yaml` defines servers (name, host, user, port, ssh_key, password_encrypted), collection interval, retention days, and Notion integration settings.

## Data Flow

1. APScheduler triggers `run_collection()` every N seconds
2. For each server in config: SSH connect → run commands → parse output → insert into SQLite
3. If Notion enabled: upsert metrics to Notion database
4. Old data cleaned up based on `log_retention_days`
5. Frontend polls API endpoints on 30s interval

## Important Files (gitignored)

- `.secret_key` — Fernet encryption key (auto-generated)
- `monitor.db` / `monitor.db-shm` / `monitor.db-wal` — SQLite database
- `config.yaml` — May contain `password_encrypted` values
