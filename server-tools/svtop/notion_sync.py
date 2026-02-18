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

    def _find_page(self, server_name: str) -> Optional[str]:
        """Find existing page for a server by name."""
        if server_name in self._page_cache:
            return self._page_cache[server_name]

        try:
            result = self.notion.databases.query(
                database_id=self.database_id,
                filter={
                    "property": "Server Name",
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
            "Server Name": {"title": [{"text": {"content": data["server_name"]}}]},
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
