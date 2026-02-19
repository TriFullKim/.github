"""Notion Database sync module for server metrics."""

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class NotionSync:
    def __init__(self, api_key: str, database_id: str):
        try:
            from notion_client import Client
        except ImportError:
            logger.error("notion-client package not installed. Run: pip install notion-client")
            raise
        self.notion = Client(auth=api_key)
        self.database_id = database_id
        self._page_cache: dict[str, str] = {}  # server_name -> page_id
        self.title_prop = "Name"  # Default, will be updated by _ensure_schema
        self._ensure_schema()

    def _ensure_schema(self):
        """Ensure database has necessary properties."""
        try:
            db = self.notion.databases.retrieve(database_id=self.database_id)
            current_props = db.get("properties", {})
            
            # Find the title property
            for name, prop in current_props.items():
                if prop["type"] == "title":
                    self.title_prop = name
                    break
            
            # Define required properties
            required_props = {
                "CPU (%)": {"number": {"format": "percent"}},
                "RAM Used (MB)": {"number": {"format": "number"}},
                "RAM Total (MB)": {"number": {"format": "number"}},
                "Disk (%)": {"number": {"format": "percent"}},
                "Active Users": {"number": {"format": "number"}},
                "Last Updated": {"rich_text": {}},
                "GPU (%)": {"number": {"format": "percent"}},
                "GPU Mem (MB)": {"number": {"format": "number"}},
                "Top Process": {"rich_text": {}},
                "User List": {"rich_text": {}},
            }
            
            props_to_create = {}
            for name, config in required_props.items():
                if name not in current_props:
                    props_to_create[name] = config
            
            if props_to_create:
                logger.info(f"Adding missing properties to Notion DB: {list(props_to_create.keys())}")
                self.notion.databases.update(
                    database_id=self.database_id,
                    properties=props_to_create
                )
                
        except Exception as e:
            logger.error(f"Failed to ensure schema: {e}")

    def _find_page(self, server_name: str) -> Optional[str]:
        """Find existing page for a server by name."""
        if server_name in self._page_cache:
            return self._page_cache[server_name]

        try:
            result = self.notion.databases.query(
                database_id=self.database_id,
                filter={
                    "property": self.title_prop,
                    "title": {"equals": server_name},
                },
            )
            if result["results"]:
                page_id = result["results"][0]["id"]
                self._page_cache[server_name] = page_id
                return page_id
        except Exception as e:
            logger.error(f"Notion query failed for {server_name}: {e}")
        return None

    def _build_properties(self, data: dict) -> dict:
        """Build Notion page properties from metric data."""
        now = datetime.now(timezone.utc).isoformat()

        props = {
            self.title_prop: {"title": [{"text": {"content": data["server_name"]}}]},
            "CPU (%)": {"number": data.get("cpu", 0)},
            "RAM Used (MB)": {"number": data.get("ram_used", 0)},
            "RAM Total (MB)": {"number": data.get("ram_total", 0)},
            "Disk (%)": {"number": data.get("disk", 0)},
            "Active Users": {"number": len(data.get("users", []))},
            "Last Updated": {"rich_text": [{"text": {"content": now}}]},
        }

        # GPU (optional)
        if data.get("gpu_util") is not None:
            props["GPU (%)"] = {"number": data["gpu_util"]}
            props["GPU Mem (MB)"] = {"number": data.get("gpu_mem_used", 0)}
        else:
            props["GPU (%)"] = {"number": None}
            props["GPU Mem (MB)"] = {"number": None}

        # Top process
        processes = data.get("processes", [])
        if processes:
            top = processes[0]
            props["Top Process"] = {
                "rich_text": [{"text": {"content": f"PID {top['pid']}: {top['command'][:90]}"}}]
            }

        # User list
        users = data.get("users", [])
        if users:
            user_str = ", ".join(u["username"] for u in users)[:100]
            props["User List"] = {
                "rich_text": [{"text": {"content": user_str}}]
            }

        return props

    def sync_server(self, data: dict):
        """Upsert a server's latest metrics to Notion."""
        server_name = data["server_name"]
        props = self._build_properties(data)

        page_id = self._find_page(server_name)

        try:
            if page_id:
                # Update existing page
                self.notion.pages.update(page_id=page_id, properties=props)
                logger.info(f"Notion updated: {server_name}")
            else:
                # Create new page
                result = self.notion.pages.create(
                    parent={"database_id": self.database_id},
                    properties=props,
                )
                self._page_cache[server_name] = result["id"]
                logger.info(f"Notion created: {server_name}")
        except Exception as e:
            logger.error(f"Notion sync failed for {server_name}: {e}")

    def sync_all(self, metrics_list: list[dict]):
        """Sync all servers' metrics to Notion."""
        for data in metrics_list:
            if data:
                self.sync_server(data)
