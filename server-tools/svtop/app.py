"""FastAPI application with APScheduler for periodic metric collection."""

import getpass
import logging
import os
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from apscheduler.schedulers.background import BackgroundScheduler

from database import Database
from collector import collect_server_metrics
from notion_sync import NotionSync
from crypto_util import encrypt_password

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Load Config ────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")

with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)


# ─── Password Setup ────────────────────────────────────────────────────────
def setup_passwords():
    """Check each server for missing auth and prompt for passwords if needed."""
    changed = False
    servers = config.get("servers", [])

    for server in servers:
        ssh_key = server.get("ssh_key")
        key_path = os.path.expanduser(ssh_key) if ssh_key else None
        has_key = key_path and os.path.exists(key_path)
        has_password = bool(server.get("password_encrypted"))

        if not has_key and not has_password:
            print(f"\n🔐 Server '{server['name']}' ({server['host']})")
            if ssh_key:
                print(f"   ⚠  SSH key not found: {key_path}")
            print("   No authentication method configured.")
            password = getpass.getpass(f"   Enter SSH password for {server['user']}@{server['host']}: ")
            if password:
                server["password_encrypted"] = encrypt_password(password)
                changed = True
                print("   ✅ Password encrypted and saved.")
            else:
                print("   ⏭  Skipped (no password entered).")

    if changed:
        with open(CONFIG_PATH, "w") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        logger.info("Config updated with encrypted passwords")


setup_passwords()

db = Database(os.path.join(BASE_DIR, "monitor.db"))
db.init_db()

# ─── Notion (optional) ─────────────────────────────────────────────────────
notion_sync = None
notion_cfg = config.get("notion", {})
if notion_cfg.get("enabled"):
    try:
        notion_sync = NotionSync(
            api_key=notion_cfg["api_key"],
            database_id=notion_cfg["database_id"],
        )
        logger.info("Notion sync enabled")
    except Exception as e:
        logger.warning(f"Notion sync init failed: {e}")


# ─── Collection Job ────────────────────────────────────────────────────────
def run_collection():
    """Collect metrics from all configured servers."""
    logger.info("Starting metric collection cycle")
    servers = config.get("servers", [])
    collected = []

    for server in servers:
        data = collect_server_metrics(server)
        if data:
            metric_id = db.insert_metric(
                server_name=data["server_name"],
                cpu=data["cpu"],
                ram_used=data["ram_used"],
                ram_total=data["ram_total"],
                gpu_util=data["gpu_util"],
                gpu_mem_used=data["gpu_mem_used"],
                gpu_mem_total=data["gpu_mem_total"],
                disk_percent=data["disk"],
            )
            db.insert_processes(metric_id, data["processes"])
            db.insert_users(metric_id, data["users"])
            collected.append(data)
            logger.info(f"  ✓ {data['server_name']}: CPU={data['cpu']}%, RAM={data['ram_used']}/{data['ram_total']}MB")
        else:
            logger.warning(f"  ✗ {server['name']}: collection failed")

    # Notion sync
    if notion_sync and collected:
        notion_sync.sync_all(collected)

    # Cleanup old data
    retention = config.get("log_retention_days", 30)
    db.cleanup_old_data(retention)

    logger.info(f"Collection complete: {len(collected)}/{len(servers)} servers")


# ─── Scheduler ──────────────────────────────────────────────────────────────
scheduler = BackgroundScheduler()
interval = config.get("collect_interval_seconds", 300)
scheduler.add_job(run_collection, "interval", seconds=interval, id="collect_job")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    logger.info(f"Scheduler started (interval={interval}s)")
    yield
    scheduler.shutdown()


# ─── FastAPI App ────────────────────────────────────────────────────────────
app = FastAPI(title="Server Monitor", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/servers")
async def api_servers():
    cfg_servers = [s["name"] for s in config.get("servers", [])]
    db_servers = db.get_servers()
    all_servers = sorted(set(cfg_servers + db_servers))
    return {"servers": all_servers}


@app.get("/api/metrics/{server_name}")
async def api_metrics(server_name: str, hours: int = Query(default=24, ge=1, le=720)):
    metrics = db.get_metrics(server_name, hours=hours)
    return {"server": server_name, "hours": hours, "data": metrics}


@app.get("/api/latest/{server_name}")
async def api_latest(server_name: str):
    metric = db.get_latest_metric(server_name)
    if not metric:
        return {"server": server_name, "metric": None, "processes": [], "users": []}

    processes = db.get_processes(metric["id"])
    users = db.get_users(metric["id"])
    return {
        "server": server_name,
        "metric": metric,
        "processes": processes,
        "users": users,
    }


@app.post("/api/collect")
async def api_collect():
    """Trigger manual collection."""
    import threading
    t = threading.Thread(target=run_collection, daemon=True)
    t.start()
    return {"status": "collection_started"}


@app.get("/api/config")
async def api_config():
    return {
        "interval_seconds": config.get("collect_interval_seconds", 300),
        "retention_days": config.get("log_retention_days", 30),
        "notion_enabled": notion_cfg.get("enabled", False),
        "server_count": len(config.get("servers", [])),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
