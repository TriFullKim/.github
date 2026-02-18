"""SSH-based server metric collector using Paramiko."""

import logging
import os
import re
from typing import Optional

import paramiko

logger = logging.getLogger(__name__)


def _ssh_connect(server: dict) -> paramiko.SSHClient:
    """Create SSH connection to a server.

    Auth priority:
      1. SSH key (if ssh_key is set and file exists)
      2. Encrypted password (if password_encrypted is set)
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    ssh_key = server.get("ssh_key")
    key_path = os.path.expanduser(ssh_key) if ssh_key else None

    if key_path and os.path.exists(key_path):
        # Key-based auth
        client.connect(
            hostname=server["host"],
            port=server.get("port", 22),
            username=server["user"],
            key_filename=key_path,
            timeout=10,
        )
    elif server.get("password_encrypted"):
        # Password-based auth (decrypt stored password)
        from crypto_util import decrypt_password
        password = decrypt_password(server["password_encrypted"])
        client.connect(
            hostname=server["host"],
            port=server.get("port", 22),
            username=server["user"],
            password=password,
            timeout=10,
        )
    else:
        raise ValueError(
            f"No auth method for {server['name']}: "
            f"set ssh_key or run the app to enter a password"
        )

    return client


def _exec(client: paramiko.SSHClient, cmd: str) -> str:
    """Execute command and return stdout."""
    _, stdout, stderr = client.exec_command(cmd, timeout=15)
    return stdout.read().decode("utf-8", errors="replace").strip()


def parse_cpu(raw: str) -> float:
    """Parse CPU usage from top output."""
    # top -bn1 | grep 'Cpu(s)' ->  %Cpu(s):  3.1 us,  1.0 sy, ...
    # Also handle: top -bn1 | head -5 output variations
    match = re.search(r"(\d+\.?\d*)\s*id", raw)
    if match:
        idle = float(match.group(1))
        return round(100.0 - idle, 1)
    # Fallback: try to get us + sy
    us = re.search(r"(\d+\.?\d*)\s*us", raw)
    sy = re.search(r"(\d+\.?\d*)\s*sy", raw)
    if us and sy:
        return round(float(us.group(1)) + float(sy.group(1)), 1)
    return 0.0


def parse_ram(raw: str) -> tuple[float, float]:
    """Parse RAM from free -m output. Returns (used_mb, total_mb)."""
    for line in raw.splitlines():
        if line.lower().startswith("mem:"):
            parts = line.split()
            total = float(parts[1])
            used = float(parts[2])
            return used, total
    return 0.0, 0.0


def parse_gpu(raw: str) -> Optional[dict]:
    """Parse nvidia-smi CSV output. Returns dict or None."""
    lines = raw.strip().splitlines()
    if len(lines) < 2:
        return None
    # Header: utilization.gpu [%], memory.used [MiB], memory.total [MiB]
    data_line = lines[-1]
    parts = [p.strip().replace(" %", "").replace(" MiB", "") for p in data_line.split(",")]
    try:
        return {
            "util": float(parts[0]),
            "mem_used": float(parts[1]),
            "mem_total": float(parts[2]),
        }
    except (ValueError, IndexError):
        return None


def parse_disk(raw: str) -> float:
    """Parse df output for root partition usage percent."""
    for line in raw.splitlines():
        if line.endswith("/") or "/ " in line:
            match = re.search(r"(\d+)%", line)
            if match:
                return float(match.group(1))
    return 0.0


def parse_processes(raw: str) -> list[dict]:
    """Parse ps aux output into list of process dicts."""
    procs = []
    lines = raw.splitlines()
    for line in lines[1:]:  # skip header
        parts = line.split(None, 10)
        if len(parts) >= 11:
            procs.append({
                "user": parts[0],
                "pid": int(parts[1]),
                "cpu": float(parts[2]),
                "mem": float(parts[3]),
                "command": parts[10],
            })
    return procs


def parse_users(raw: str) -> list[dict]:
    """Parse who output into list of user dicts."""
    users = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 3:
            users.append({
                "username": parts[0],
                "terminal": parts[1],
                "login_time": " ".join(parts[2:4]) if len(parts) >= 4 else parts[2],
            })
    return users


def collect_server_metrics(server: dict) -> Optional[dict]:
    """
    Connect to server via SSH and collect all metrics.
    Returns dict with all parsed metrics, or None on failure.
    """
    name = server["name"]
    logger.info(f"Collecting metrics from {name} ({server['host']})")

    try:
        client = _ssh_connect(server)
    except Exception as e:
        logger.error(f"SSH connection failed for {name}: {e}")
        return None

    try:
        # CPU
        cpu_raw = _exec(client, "top -bn1 | grep 'Cpu(s)'")
        cpu = parse_cpu(cpu_raw)

        # RAM
        ram_raw = _exec(client, "free -m")
        ram_used, ram_total = parse_ram(ram_raw)

        # GPU (optional)
        gpu_raw = _exec(client, "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv 2>/dev/null")
        gpu = parse_gpu(gpu_raw)

        # Disk
        disk_raw = _exec(client, "df -h /")
        disk = parse_disk(disk_raw)

        # Top processes (top 10 by CPU)
        ps_raw = _exec(client, "ps aux --sort=-%cpu | head -11")
        processes = parse_processes(ps_raw)

        # Logged-in users
        who_raw = _exec(client, "who")
        users = parse_users(who_raw)

        return {
            "server_name": name,
            "cpu": cpu,
            "ram_used": ram_used,
            "ram_total": ram_total,
            "gpu_util": gpu["util"] if gpu else None,
            "gpu_mem_used": gpu["mem_used"] if gpu else None,
            "gpu_mem_total": gpu["mem_total"] if gpu else None,
            "disk": disk,
            "processes": processes,
            "users": users,
        }

    except Exception as e:
        logger.error(f"Metric collection failed for {name}: {e}")
        return None
    finally:
        client.close()
