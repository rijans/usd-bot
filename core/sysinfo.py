"""
core/sysinfo.py  ─  Server/process statistics for the admin panel.

Uses stdlib only (no psutil required). Works on Linux (Railway containers).
"""
import os
import sys
import shutil
import platform
import resource
import datetime
from typing import Optional

# Set at bot startup to track bot uptime
_BOT_START_TIME: Optional[datetime.datetime] = None


def set_start_time() -> None:
    global _BOT_START_TIME
    _BOT_START_TIME = datetime.datetime.now(datetime.timezone.utc)


def _fmt_uptime(seconds: float) -> str:
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


def _read_file(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except Exception:
        return ""


def get_system_info() -> dict:
    info: dict = {}

    # ── Bot uptime ─────────────────────────────────────────────────────────────
    if _BOT_START_TIME:
        delta = datetime.datetime.now(datetime.timezone.utc) - _BOT_START_TIME
        info["bot_uptime"] = _fmt_uptime(delta.total_seconds())
    else:
        info["bot_uptime"] = "Unknown"

    # ── System uptime (Linux only) ────────────────────────────────────────────
    uptime_raw = _read_file("/proc/uptime")
    if uptime_raw:
        info["sys_uptime"] = _fmt_uptime(float(uptime_raw.split()[0]))
    else:
        info["sys_uptime"] = "N/A"

    # ── CPU load averages ─────────────────────────────────────────────────────
    try:
        l1, l5, l15 = os.getloadavg()
        info["load_avg"] = f"{l1:.2f} / {l5:.2f} / {l15:.2f} (1m/5m/15m)"
    except Exception:
        info["load_avg"] = "N/A"

    # ── CPU model & count ─────────────────────────────────────────────────────
    info["cpu_count"] = str(os.cpu_count() or "?")
    cpu_model = "Unknown"
    for line in _read_file("/proc/cpuinfo").splitlines():
        if line.lower().startswith("model name"):
            cpu_model = line.split(":", 1)[1].strip()
            break
    if cpu_model == "Unknown":
        cpu_model = platform.processor() or "Unknown"
    info["cpu_model"] = cpu_model

    # ── System RAM from /proc/meminfo ─────────────────────────────────────────
    mem: dict[str, int] = {}
    for line in _read_file("/proc/meminfo").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            try:
                mem[parts[0].rstrip(":")] = int(parts[1]) * 1024  # kB → bytes
            except ValueError:
                pass
    if mem:
        total     = mem.get("MemTotal", 0)
        available = mem.get("MemAvailable", 0)
        used      = total - available
        info["mem_total"]     = f"{total     // 1024 // 1024} MB"
        info["mem_used"]      = f"{used      // 1024 // 1024} MB"
        info["mem_available"] = f"{available // 1024 // 1024} MB"
        info["mem_pct"]       = f"{used * 100 // total}%" if total else "?"
    else:
        info["mem_total"] = info["mem_used"] = info["mem_available"] = info["mem_pct"] = "N/A"

    # ── Bot process RSS (current memory usage of this Python process) ─────────
    try:
        # ru_maxrss is in kilobytes on Linux
        rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        info["proc_rss"] = f"{rss_kb // 1024} MB"
    except Exception:
        info["proc_rss"] = "N/A"

    # ── Disk usage ────────────────────────────────────────────────────────────
    try:
        total_d, used_d, free_d = shutil.disk_usage("/")
        info["disk_total"] = f"{total_d // 1024 // 1024 // 1024} GB"
        info["disk_used"]  = f"{used_d  // 1024 // 1024 // 1024} GB"
        info["disk_free"]  = f"{free_d  // 1024 // 1024 // 1024} GB"
        info["disk_pct"]   = f"{used_d * 100 // total_d}%" if total_d else "?"
    except Exception:
        info["disk_total"] = info["disk_used"] = info["disk_free"] = info["disk_pct"] = "N/A"

    # ── Platform ──────────────────────────────────────────────────────────────
    info["python_version"] = sys.version.split()[0]
    info["arch"]           = platform.machine() or "Unknown"
    info["os_name"]        = f"{platform.system()} {platform.release()}".strip()

    return info


def format_server_status() -> str:
    s = get_system_info()
    return (
        "🖥 *Server Status*\n\n"
        f"🤖 *Bot Uptime:* `{s['bot_uptime']}`\n"
        f"🕒 *System Uptime:* `{s['sys_uptime']}`\n\n"
        f"🧠 *CPU*\n"
        f"  Model: `{s['cpu_model']}`\n"
        f"  Cores: `{s['cpu_count']}`\n"
        f"  Load: `{s['load_avg']}`\n\n"
        f"💾 *Memory (System)*\n"
        f"  Total: `{s['mem_total']}` | Used: `{s['mem_used']}` ({s['mem_pct']})\n"
        f"  Available: `{s['mem_available']}`\n\n"
        f"🤖 *Bot Process RAM:* `{s['proc_rss']}`\n\n"
        f"💿 *Disk*\n"
        f"  Total: `{s['disk_total']}` | Used: `{s['disk_used']}` ({s['disk_pct']})\n"
        f"  Free: `{s['disk_free']}`\n\n"
        f"🐍 *Python:* `{s['python_version']}`\n"
        f"⚙️ *Platform:* `{s['os_name']} ({s['arch']})`"
    )
