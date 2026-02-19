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
def run_collection(sync_notion: bool = True, server_name: str = None):
    """
    Collect metrics from all configured servers (or a specific one).
    :param sync_notion: If True, sync results to Notion.
    :param server_name: If provided, only collect for this server.
    """
    logger.info(f"Starting metric collection (Notion={'ON' if sync_notion else 'OFF'}, Target={server_name or 'ALL'})")
    
    all_servers = config.get("servers", [])
    if server_name:
        servers = [s for s in all_servers if s["name"] == server_name]
        if not servers:
            logger.warning(f"Server '{server_name}' not found in config.")
            return
    else:
        servers = all_servers
        
    collected = []

    import concurrent.futures
    
    def process_server(server):
        try:
            data = collect_server_metrics(server)
            if data:
                return data
            else:
                logger.warning(f"  ✗ {server['name']}: collection failed")
                return None
        except Exception as e:
            logger.error(f"  ✗ {server['name']}: error {e}")
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_server = {executor.submit(process_server, s): s for s in servers}
        
        for future in concurrent.futures.as_completed(future_to_server):
            data = future.result()
            if data:
                # Calculate aggregated disk metrics (Used instead of Free)
                disk_total = 0
                disk_used = 0
                for d in data.get("disks", []):
                    disk_total += d.get("total", 0)
                    disk_used += d.get("used", 0)
                
                # Global Used %
                disk_used_percent = (disk_used / disk_total * 100.0) if disk_total > 0 else 0.0

                metric_id = db.insert_metric(
                    server_name=data["server_name"],
                    cpu=data["cpu_percent"],
                    ram_used=data["ram_used"],
                    ram_total=data["ram_total"],
                    gpu_util=data["gpu_util"],
                    gpu_mem_used=data["gpu_mem_used"],
                    gpu_mem_total=data["gpu_mem_total"],
                    disk_percent=disk_used_percent, # Sving USED % now
                    cpu_load=data["cpu_load"],
                    cpu_threads_total=data["cpu_threads_total"],
                    disk_used_bytes=disk_used,
                    disk_total_bytes=disk_total
                )
                db.insert_processes(metric_id, data["processes"])
                db.insert_users(metric_id, data["users"])
                db.insert_disks(metric_id, data["disks"])
                if data["home_usage"]:
                    db.insert_home_usage(metric_id, data["home_usage"])
                    
                collected.append(data)
                logger.info(f"  ✓ {data['server_name']}: CPU={data['cpu_load']}/{data['cpu_threads_total']}, RAM={int(data['ram_used'])}MB")

    # Notion sync
    # Notion sync (Update logic if needed, or disable for now if schema mismatches again)
    # Since we changed data structure, NotionSync might break if it expects specific keys.
    # The 'data' dict now has 'cpu_percent' instead of 'cpu'.
    # We should probably update notion_sync.py to match, or map it here.
    # For now, let's just map it quickly to avoid breaking it completely.
    if sync_notion and notion_sync and collected:
        # Adapt data for notion sync (compat mode)
        notion_data = []
        for d in collected:
            d_copy = d.copy()
            d_copy["cpu"] = d["cpu_percent"]
            notion_data.append(d_copy)
        notion_sync.sync_all(notion_data)

    # Cleanup old data
    retention = config.get("log_retention_days", 30)
    db.cleanup_old_data(retention)

    logger.info(f"Collection complete: {len(collected)}/{len(servers)} servers")


# ─── Scheduler ──────────────────────────────────────────────────────────────
scheduler = BackgroundScheduler()
interval = config.get("collect_interval_seconds", 300)
# Scheduled job always syncs to Notion
scheduler.add_job(run_collection, "interval", seconds=interval, id="collect_job", kwargs={"sync_notion": True})


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


@app.get("/api/overview")
async def api_overview():
    """Get overview stats for all servers (Home Dashboard)."""
    cfg_servers = [s["name"] for s in config.get("servers", [])]
    db_servers = db.get_servers()
    all_servers = sorted(set(cfg_servers + db_servers))
    
    overview_data = []
    for server in all_servers:
        stats = db.get_overview_stats(server)
        if stats:
            overview_data.append(stats)
            
    return {"overview": overview_data}


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
    disks = db.get_disks(metric["id"])
    home_usage = db.get_home_usage(metric["id"])
    
    return {
        "server": server_name,
        "metric": metric,
        "processes": processes,
        "users": users,
        "disks": disks,
        "home_usage": home_usage,
    }


@app.post("/api/collect")
async def api_collect(server: str = Query(None)):
    """Trigger manual collection (Notion sync skipped). Optional: specific server."""
    import threading
    t = threading.Thread(target=run_collection, args=(False, server), daemon=True)
    t.start()
    return {"status": "collection_started", "target": server or "all"}


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
