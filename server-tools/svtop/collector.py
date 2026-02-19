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


def _exec(client: paramiko.SSHClient, cmd: str, sudo_password: Optional[str] = None) -> str:
    """Execute command and return stdout. Supports sudo via stdin."""
    if sudo_password and cmd.startswith("sudo"):
        cmd = f"sudo -S -p '' {cmd[5:]}"  # Remove 'sudo ' prefix and add -S
    
    stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
    
    if sudo_password and cmd.startswith("sudo"):
        stdin.write(f"{sudo_password}\n")
        stdin.flush()

    return stdout.read().decode("utf-8", errors="replace").strip()


def parse_cpu_threads(load_raw: str, nproc_raw: str) -> tuple[float, int]:
    """Parse load average (1m) and total CPU threads."""
    try:
        # loadavg: 0.00 0.00 0.00 1/123 12345
        load = float(load_raw.split()[0])
        total = int(nproc_raw.strip())
        return load, total
    except (ValueError, IndexError):
        return 0.0, 1


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


def parse_disks(raw: str) -> tuple[float, list[dict]]:
    """
    Parse df -P -B1 output.
    Returns: (overall_percent_used, list_of_disk_details)
    overall_percent_used = (Total All - Total Free All) / Total All * 100
    User requested: Percentage based on total space vs total free space logic.
    User said: "disk percentage should be total free / total space" -> wait, usually usage is used/total.
    User said: "disk percentage is total space of all disks / free space of all disks" -> No, "disk의 percentage는 전체 디스크의 빈공간 / 전체 디스크의 전체공간 으로 해주고" -> "make disk percentage as (total free / total space)".
    Usually dashboard shows USAGE %, so if user wants FREE %, I should clarify or implement as requested.
    Actually, usually "Disk %" means Usage. If user says "Disk % is Free/Total", then 100% means empty. 
    However, standard is Usage. Let's assume user meant "Calculate global usage based on Total Used / Total Space", OR they want a "Free Space %" metric.
    Let's stick to standard "Usage %" for the gauge (1 - Free/Total), but if user explicitly asked for "Free / Total", that would be "Health"?
    Re-reading Korean: "disk의 percentage는 전체 디스크의 빈공간 / 전체 디스크의 전체공간 으로 해주고" -> "Please make disk percentage as (Total Free / Total Space)".
    This imply the Gauge value should be Free %. Okay. I will follow instruction. Gauge will show "Free %".
    """
    disks = []
    total_bytes_all = 0
    free_bytes_all = 0
    
    # Filesystems to ignore
    ignored_fs = ("tmpfs", "devtmpfs", "squashfs", "overlay", "iso9660")
    
    lines = raw.splitlines()
    for line in lines[1:]: # skip header
        parts = line.split()
        if len(parts) < 6:
            continue
            
        fs, total, used, available, capacity, mount = parts[0], parts[1], parts[2], parts[3], parts[4], " ".join(parts[5:])
        
        # Filter logic
        if fs == "udev" or any(x in fs for x in ignored_fs) or mount.startswith("/loop") or mount.startswith("/snap"):
            continue
            
        try:
            t = int(total)
            u = int(used)
            f = int(available)
            
            disks.append({
                "fs": fs,
                "mount": mount,
                "total": t,
                "used": u,
                "free": f,
                "percent": f / t * 100.0 if t > 0 else 0.0
            })
            
            total_bytes_all += t
            free_bytes_all += f
        except ValueError:
            continue
            
    # Per user request: Global "Disk %" = Total Free / Total All
    # But usually dashboard shows "Usage". If I return "Free %", I should label it "Free".
    # But existing label is "Disk (%)". If I put Free% there, 90% means Good.
    # The prompt says: "disk의 percentage는 전체 디스크의 빈공간 / 전체 디스크의 전체공간 으로 해주고"
    # -> "Make disk percentage as (Total Free) / (Total Space)".
    # Okay, I will return this value.
    
    overall_free_percent = (free_bytes_all / total_bytes_all * 100.0) if total_bytes_all > 0 else 0.0
    return overall_free_percent, disks


def parse_processes_enhanced(raw: str) -> list[dict]:
    """
    Parse ps aux output.
    Filter: hide kernel threads (usually [kworker...]), system daemons if possible.
    Prioritize: python, bash, scp, ssh, node, java.
    User said: "top command의 경우 system 상에서 사용하는 것은 나타내지말고 python, bash, scp 와 같이 사용자에 의해 작동하는 것을 우선적으로 나타내줘"
    """
    procs = []
    lines = raw.splitlines()
    priority_keywords = ["python", "bash", "scp", "ssh", "node", "java", "uvicorn", "gunicorn"]
    
    for line in lines[1:]:
        parts = line.split(None, 10)
        if len(parts) >= 11:
            user = parts[0]
            pid = int(parts[1])
            cpu = float(parts[2])
            mem = float(parts[3])
            cmd = parts[10]
            
            # Simple Filter: Skip kernel threads (often in brackets like [kworker...])
            if cmd.startswith("[") and cmd.endswith("]"):
                continue
            # Skip root processes that are not interesting (broad heuristic)
            # User said "don't show system usage". Hard to define perfectly.
            # We'll allow root processes if they match priority keywords.
            
            score = cpu
            # Boost score for priority keywords
            if any(k in cmd.lower() for k in priority_keywords):
                score += 1000.0
                
            procs.append({
                "user": user,
                "pid": pid,
                "cpu": cpu, # Logic for sorting
                "mem": mem,
                "command": cmd,
                "_score": score
            })
            
    # Sort by score desc
    procs.sort(key=lambda x: x["_score"], reverse=True)
    
    # Return top 20, remove _score
    result = []
    for p in procs[:20]:
        del p["_score"]
        result.append(p)
        
    return result

def parse_home_usage(raw: str) -> list[dict]:
    """Parse du -hd 1 /home output."""
    # 50G /home/cvsp
    data = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            size_str = parts[0]
            path = parts[1]
            user = os.path.basename(path)
            if path == "/home" or user == "home":
                continue
                
            # Convert size to bytes for sorting/storage?
            # du -h gives K, M, G. Let's try to normalize or just store rough bytes if possible.
            # Actually du -b or -k is better for parsing, but -h is requested "sudo du -hd 1"
            # Let's parse the -h output roughly.
            
            mult = 1
            if size_str.endswith('T'): mult = 1024**4; val = float(size_str[:-1])
            elif size_str.endswith('G'): mult = 1024**3; val = float(size_str[:-1])
            elif size_str.endswith('M'): mult = 1024**2; val = float(size_str[:-1])
            elif size_str.endswith('K'): mult = 1024; val = float(size_str[:-1])
            else: val = float(size_str)
            
            size_bytes = int(val * mult)
            
            data.append({
                "user": user,
                "size": size_bytes
            })
    return data


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
        # CPU (Threads/Load)
        load_raw = _exec(client, "cat /proc/loadavg")
        nproc_raw = _exec(client, "nproc")
        cpu_load, cpu_total_threads = parse_cpu_threads(load_raw, nproc_raw)
        # Keep old cpu percent for compatibility or calculate it? 
        # User said "CPU는 전체 Thread수에서 사용되는 Thread 수로 해줘" -> Display logic.
        # But DB expects cpu_percent. Let's use (load / total * 100) as a proxy for "Busy %" 
        # or just store 0 and rely on the new fields.
        # Let's keep `top` for a general CPU % if we still want a bar, or just use load/total.
        # Actually, "process list" needs `ps`. The overview card needs "Used Threads / Total".
        # Let's store load and total in new fields. `cpu_percent` can be `load / total * 100`.
        cpu_percent = (cpu_load / cpu_total_threads * 100.0) if cpu_total_threads > 0 else 0.0

        # RAM
        ram_raw = _exec(client, "free -m")
        ram_used, ram_total = parse_ram(ram_raw)

        # GPU (optional)
        gpu_raw = _exec(client, "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv 2>/dev/null")
        gpu = parse_gpu(gpu_raw)

        # Disk (Per-partition + Overall Free %)
        disk_raw = _exec(client, "df -P -B1")
        disk_free_percent, disks = parse_disks(disk_raw)

        # Top processes (Prioritized)
        # Fetch more to allow software filtering
        ps_raw = _exec(client, "ps aux --sort=-%cpu | head -50")
        processes = parse_processes_enhanced(ps_raw)

        # Logged-in users
        who_raw = _exec(client, "who")
        users = parse_users(who_raw)

        # Home directory usage (sudo)
        # We need the decrypted password here. server dict has 'password_encrypted', 
        # but _ssh_connect decrypts it internally or we need to decrypt it here.
        # _ssh_connect logic handles connection. To get password for sudo, we need to decrypt again or pass it.
        # Let's check if we can get it.
        from crypto_util import decrypt_password
        sudo_pass = None
        if server.get("password_encrypted"):
            try:
                sudo_pass = decrypt_password(server["password_encrypted"])
            except:
                pass
        
        home_usage = []
        if sudo_pass:
            home_raw = _exec(client, "sudo -S du -hd 1 /home", sudo_password=sudo_pass)
            home_usage = parse_home_usage(home_raw)

        return {
            "server_name": name,
            "cpu_percent": cpu_percent, # Proxy from load
            "cpu_load": cpu_load,
            "cpu_threads_total": cpu_total_threads,
            "ram_used": ram_used,
            "ram_total": ram_total,
            "gpu_util": gpu["util"] if gpu else None,
            "gpu_mem_used": gpu["mem_used"] if gpu else None,
            "gpu_mem_total": gpu["mem_total"] if gpu else None,
            "disk": disk_free_percent,  # This is actually FREE percent now
            "disks": disks,
            "processes": processes,
            "users": users,
            "home_usage": home_usage,
        }

    except Exception as e:
        import traceback
        logger.error(f"Metric collection failed for {name}: {e}\n{traceback.format_exc()}")
        return None
    finally:
        client.close()
