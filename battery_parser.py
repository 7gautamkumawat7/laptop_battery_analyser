#!/usr/bin/env python3
"""
Battery Parser & Generator Module
==================================
Handles running `powercfg /batteryreport`, parsing all sections of the generated
HTML report, calculating health metrics, and querying live battery status.
"""

import csv
import io
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    import psutil
except ImportError:
    psutil = None


def generate_battery_report(output_path: Path) -> Path:
    """Run `powercfg /batteryreport` to generate a fresh HTML report on Windows."""
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if sys.platform != "win32":
        if output_path.exists():
            return output_path
        raise RuntimeError("powercfg is a Windows-only tool. Provide an existing battery-report.html.")

    cmd = ["powercfg", "/batteryreport", "/output", str(output_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err_msg = result.stderr or result.stdout or "Unknown powercfg error"
        raise RuntimeError(f"powercfg command failed (exit code {result.returncode}): {err_msg.strip()}")

    if not output_path.exists():
        raise FileNotFoundError(f"powercfg completed but output file not found at: {output_path}")

    return output_path


def load_html(path: Path) -> str:
    """Load HTML file with automatic BOM/encoding detection."""
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xff\xfe"):
        return raw.decode("utf-16-le")
    if raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16-be")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    for enc in ("utf-8", "utf-16", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def to_mwh(value: Any) -> Optional[int]:
    """Convert capacities like '54,891 mWh', '54.89 Wh', or '1.2 kWh' to integer mWh."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(round(value))

    text = str(value).strip()
    if not text or text == "-":
        return None

    match = re.search(r"([0-9][0-9,]*\.?[0-9]*)\s*(mWh|Wh|kWh)?", text, re.IGNORECASE)
    if not match:
        return None

    number = float(match.group(1).replace(",", ""))
    unit = (match.group(2) or "mWh").lower()
    if unit == "wh":
        number *= 1000
    elif unit == "kwh":
        number *= 1_000_000
    return int(round(number))


def parse_duration_to_seconds(value: str) -> Optional[int]:
    """Convert 'H:MM:SS' or 'M:SS' or duration string into total seconds."""
    if not value or value == "-":
        return None
    parts = str(value).strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 1 and parts[0].isdigit():
            return int(parts[0])
    except (ValueError, TypeError):
        pass
    return None


def format_seconds_to_hms(seconds: Optional[int]) -> str:
    """Format total seconds into human readable 'Xh Ym' or 'Xm Ys'."""
    if seconds is None:
        return "N/A"
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    hours = minutes // 60
    rem_min = minutes % 60
    if hours > 0:
        return f"{hours}h {rem_min}m"
    return f"{minutes}m"


def health_verdict(pct: Optional[float], cycles: Optional[int] = None) -> Dict[str, Any]:
    """Formulate a comprehensive battery health verdict and rating."""
    if pct is None:
        return {
            "status": "Unknown",
            "badge": "neutral",
            "color": "#94a3b8",
            "title": "Data Unavailable",
            "description": "Capacity information is missing from the generated report.",
            "recommendation": "Check if battery firmware drivers are installed properly."
        }

    if pct >= 95:
        return {
            "status": "Pristine",
            "badge": "emerald",
            "color": "#10b981",
            "title": "Excellent - Factory Condition",
            "description": f"Battery capacity is operating at {pct}% of its original design specification. Essentially brand new.",
            "recommendation": "Maintain optimal charge cycles between 20% and 80% to prolong lifespan."
        }
    elif pct >= 85:
        return {
            "status": "Healthy",
            "badge": "cyan",
            "color": "#06b6d4",
            "title": "Very Good - Normal Operation",
            "description": f"Battery capacity is at {pct}%. Minimal degradation consistent with routine usage.",
            "recommendation": "Battery condition is solid. No action required."
        }
    elif pct >= 75:
        return {
            "status": "Fair",
            "badge": "amber",
            "color": "#f59e0b",
            "title": "Good - Moderate Wear",
            "description": f"Battery holds {pct}% of design capacity. You may notice slightly shorter unplugged sessions.",
            "recommendation": "Avoid exposing laptop to extreme heat and prolonged 100% trickle-charging."
        }
    elif pct >= 60:
        return {
            "status": "Degraded",
            "badge": "orange",
            "color": "#f97316",
            "title": "Degraded - Noticeable Capacity Loss",
            "description": f"Battery capacity has dropped to {pct}%. Run time per charge is noticeably reduced.",
            "recommendation": "Consider battery replacement if portable uptime is critical. Many manufacturers consider <80% degraded."
        }
    else:
        return {
            "status": "Poor",
            "badge": "rose",
            "color": "#ef4444",
            "title": "Poor - Near End of Life",
            "description": f"Battery health is at {pct}%. High risk of sudden shutdowns or severe throttling on battery power.",
            "recommendation": "Replacement strongly recommended for reliable mobile usage."
        }


def get_live_battery_status() -> Dict[str, Any]:
    """Query real-time battery status using psutil and Windows APIs."""
    live = {
        "supported": False,
        "percent": None,
        "power_plugged": None,
        "secsleft": None,
        "time_left_formatted": "N/A",
        "charging_state": "Unknown",
        "power_source": "Unknown",
        "status_badge": "neutral"
    }

    if psutil and hasattr(psutil, "sensors_battery"):
        try:
            battery = psutil.sensors_battery()
            if battery:
                live["supported"] = True
                live["percent"] = round(battery.percent, 1)
                live["power_plugged"] = battery.power_plugged

                if battery.power_plugged:
                    live["power_source"] = "AC Power (Plugged In)"
                    if battery.percent >= 99:
                        live["charging_state"] = "Fully Charged"
                        live["status_badge"] = "emerald"
                    else:
                        live["charging_state"] = "Charging"
                        live["status_badge"] = "cyan"
                else:
                    live["power_source"] = "Battery Power (Discharging)"
                    live["charging_state"] = "Discharging"
                    live["status_badge"] = "amber" if battery.percent > 20 else "rose"

                if battery.secsleft != psutil.POWER_TIME_UNLIMITED and battery.secsleft != psutil.POWER_TIME_UNKNOWN and battery.secsleft > 0:
                    live["secsleft"] = battery.secsleft
                    live["time_left_formatted"] = format_seconds_to_hms(battery.secsleft)
                elif battery.power_plugged:
                    live["time_left_formatted"] = "On AC Power"
                else:
                    live["time_left_formatted"] = "Calculating..."
        except Exception:
            pass

    return live


def parse_battery_report(html_content: str) -> Dict[str, Any]:
    """Parse the complete Windows battery report HTML into structured data."""
    if not BeautifulSoup:
        raise ImportError("BeautifulSoup4 is required. Install with: pip install beautifulsoup4")

    soup = BeautifulSoup(html_content, "html.parser")

    # 1. Parse System Info Header
    system_info = {}
    first_table = soup.find("table")
    if first_table:
        for tr in first_table.find_all("tr"):
            tds = tr.find_all(["td", "th"])
            if len(tds) >= 2:
                label = tds[0].get_text(" ", strip=True).upper()
                val = tds[1].get_text(" ", strip=True)
                system_info[label] = val

    # 2. Parse Section Tables
    sections = {}
    for h2 in soup.find_all("h2"):
        title = h2.get_text(strip=True)
        table = h2.find_next("table")
        if table:
            sections[title] = table

    # 3. Installed Battery Details
    installed_battery_data = {}
    installed_table = sections.get("Installed batteries") or sections.get("Installed Batteries")
    if installed_table:
        for tr in installed_table.find_all("tr"):
            tds = tr.find_all(["td", "th"])
            if len(tds) >= 2:
                k = tds[0].get_text(strip=True).upper()
                v = tds[1].get_text(strip=True)
                if k:
                    installed_battery_data[k] = v

    name = installed_battery_data.get("NAME") or "Unknown"
    manufacturer = installed_battery_data.get("MANUFACTURER") or "Unknown"
    serial_number = installed_battery_data.get("SERIAL NUMBER") or "N/A"
    chemistry = installed_battery_data.get("CHEMISTRY") or "Li-Ion"

    raw_design = installed_battery_data.get("DESIGN CAPACITY")
    raw_full = installed_battery_data.get("FULL CHARGE CAPACITY")
    design_mwh = to_mwh(raw_design)
    full_mwh = to_mwh(raw_full)

    cycle_count_raw = installed_battery_data.get("CYCLE COUNT")
    cycle_count = None
    if cycle_count_raw and cycle_count_raw.isdigit():
        cycle_count = int(cycle_count_raw)

    health_pct = None
    if design_mwh and full_mwh and design_mwh > 0:
        health_pct = round((full_mwh / design_mwh) * 100, 1)

    wear_pct = round(100.0 - health_pct, 1) if health_pct is not None else None
    capacity_lost_mwh = (design_mwh - full_mwh) if (design_mwh and full_mwh) else 0

    verdict_info = health_verdict(health_pct, cycle_count)

    # 4. Parse Recent Usage (Power states over the last 3-7 days)
    recent_usage_rows = []
    recent_table = sections.get("Recent usage") or sections.get("Recent Usage")
    current_date = ""

    if recent_table:
        for tr in recent_table.find_all("tr"):
            tds = tr.find_all("td")
            if not tds or len(tds) < 4:
                continue

            date_cell = tds[0]
            date_span = date_cell.find("span", class_="date")
            time_span = date_cell.find("span", class_="time")

            if date_span and date_span.get_text(strip=True):
                current_date = date_span.get_text(strip=True)

            time_str = time_span.get_text(strip=True) if time_span else date_cell.get_text(strip=True)
            full_timestamp = f"{current_date} {time_str}".strip()

            state = tds[1].get_text(strip=True)
            source = tds[2].get_text(strip=True)
            pct_str = tds[3].get_text(strip=True) if len(tds) > 3 else ""
            mwh_str = tds[4].get_text(strip=True) if len(tds) > 4 else ""

            pct_val = None
            if pct_str and "%" in pct_str:
                m = re.search(r"(\d+)\s*%", pct_str)
                if m:
                    pct_val = int(m.group(1))

            mwh_val = to_mwh(mwh_str)

            recent_usage_rows.append({
                "date": current_date,
                "time": time_str,
                "timestamp": full_timestamp,
                "state": state,
                "source": source if source else ("AC" if "Active" in state else "Standby"),
                "percent": pct_val,
                "percent_str": pct_str,
                "mwh": mwh_val,
                "mwh_str": mwh_str,
                "css_class": " ".join(tr.get("class", []))
            })

    # 5. Parse Battery Usage (Drains over the last days)
    battery_drain_rows = []
    battery_usage_table = sections.get("Battery usage") or sections.get("Battery Usage")
    current_drain_date = ""

    if battery_usage_table:
        for tr in battery_usage_table.find_all("tr"):
            tds = tr.find_all("td")
            if not tds or len(tds) < 4:
                continue

            date_cell = tds[0]
            date_span = date_cell.find("span", class_="date")
            time_span = date_cell.find("span", class_="time")

            if date_span and date_span.get_text(strip=True):
                current_drain_date = date_span.get_text(strip=True)

            time_str = time_span.get_text(strip=True) if time_span else date_cell.get_text(strip=True)
            full_timestamp = f"{current_drain_date} {time_str}".strip()

            state = tds[1].get_text(strip=True)
            duration_str = tds[2].get_text(strip=True)
            energy_str = tds[3].get_text(strip=True)
            mwh_drain_str = tds[4].get_text(strip=True) if len(tds) > 4 else ""

            energy_pct = None
            if energy_str and "%" in energy_str:
                m = re.search(r"(\d+)\s*%", energy_str)
                if m:
                    energy_pct = int(m.group(1))

            duration_secs = parse_duration_to_seconds(duration_str)

            if duration_str != "-" or energy_str != "-":
                battery_drain_rows.append({
                    "date": current_drain_date,
                    "time": time_str,
                    "timestamp": full_timestamp,
                    "state": state,
                    "duration": duration_str,
                    "duration_seconds": duration_secs,
                    "duration_formatted": format_seconds_to_hms(duration_secs),
                    "energy_percent": energy_pct,
                    "energy_percent_str": energy_str,
                    "mwh_drained": to_mwh(mwh_drain_str),
                    "mwh_drain_str": mwh_drain_str
                })

    # 6. Parse Usage History (AC vs Battery duration over time)
    usage_history_rows = []
    usage_history_table = sections.get("Usage history") or sections.get("Usage History")
    if usage_history_table:
        for tr in usage_history_table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) >= 5:
                period = tds[0].get_text(" ", strip=True)
                if "PERIOD" in period.upper() or not period:
                    continue
                bat_active = tds[1].get_text(strip=True)
                bat_standby = tds[2].get_text(strip=True)
                ac_active = tds[4].get_text(strip=True) if len(tds) > 4 else tds[3].get_text(strip=True)
                ac_standby = tds[5].get_text(strip=True) if len(tds) > 5 else ""

                usage_history_rows.append({
                    "period": period.replace("\r", "").replace("\n", " ").strip(),
                    "battery_active": bat_active,
                    "battery_active_secs": parse_duration_to_seconds(bat_active),
                    "battery_standby": bat_standby,
                    "battery_standby_secs": parse_duration_to_seconds(bat_standby),
                    "ac_active": ac_active,
                    "ac_active_secs": parse_duration_to_seconds(ac_active),
                    "ac_standby": ac_standby,
                    "ac_standby_secs": parse_duration_to_seconds(ac_standby)
                })

    # 7. Parse Battery Capacity History
    capacity_history_rows = []
    capacity_table = sections.get("Battery capacity history") or sections.get("Battery Capacity History")
    if capacity_table:
        for tr in capacity_table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) >= 3:
                period = tds[0].get_text(" ", strip=True).replace("\r", "").replace("\n", " ").strip()
                if "PERIOD" in period.upper() or not period:
                    continue
                full_cap_str = tds[1].get_text(strip=True)
                design_cap_str = tds[2].get_text(strip=True)

                f_mwh = to_mwh(full_cap_str)
                d_mwh = to_mwh(design_cap_str)
                h_pct = round((f_mwh / d_mwh) * 100, 1) if (f_mwh and d_mwh and d_mwh > 0) else None

                capacity_history_rows.append({
                    "period": period,
                    "full_charge_mwh": f_mwh,
                    "full_charge_str": full_cap_str,
                    "design_capacity_mwh": d_mwh,
                    "design_capacity_str": design_cap_str,
                    "health_percent": h_pct
                })

    # 8. Parse Battery Life Estimates
    life_estimates_rows = []
    life_table = sections.get("Battery life estimates") or sections.get("Battery Life Estimates")
    current_estimate_summary = {}
    if life_table:
        for tr in life_table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) >= 4:
                period = tds[0].get_text(" ", strip=True).replace("\r", "").replace("\n", " ").strip()
                if "PERIOD" in period.upper() or "AT FULL CHARGE" in period.upper():
                    continue

                full_active = tds[1].get_text(strip=True)
                full_standby = tds[2].get_text(strip=True)
                design_active = tds[4].get_text(strip=True) if len(tds) > 4 else tds[3].get_text(strip=True)
                design_standby = tds[5].get_text(strip=True) if len(tds) > 5 else ""

                if "CURRENT ESTIMATE" in period.upper():
                    current_estimate_summary = {
                        "full_active": full_active,
                        "full_active_secs": parse_duration_to_seconds(full_active),
                        "full_standby": full_standby,
                        "design_active": design_active,
                        "design_active_secs": parse_duration_to_seconds(design_active),
                        "design_standby": design_standby
                    }
                else:
                    life_estimates_rows.append({
                        "period": period,
                        "full_active": full_active,
                        "full_active_secs": parse_duration_to_seconds(full_active),
                        "full_standby": full_standby,
                        "design_active": design_active,
                        "design_active_secs": parse_duration_to_seconds(design_active),
                        "design_standby": design_standby
                    })

    # 9. Extract embedded javascript drainGraphData points if available
    drain_graph_points = []
    match = re.search(r"drainGraphData\s*=\s*(\[[\s\S]*?\]);", html_content)
    if match:
        raw_json_array = match.group(1)
        try:
            raw_cleaned = re.sub(r'(\b[a-zA-Z_][a-zA-Z0-9_]*\b)(?=\s*:)', r'"\1"', raw_json_array)
            drain_graph_points = json.loads(raw_cleaned)
        except Exception:
            pass

    # 10. Compute Last Days Aggregates
    daily_stats = {}
    for entry in recent_usage_rows:
        d = entry["date"] or "Unknown"
        if d not in daily_stats:
            daily_stats[d] = {
                "date": d,
                "entries_count": 0,
                "active_count": 0,
                "standby_count": 0,
                "ac_count": 0,
                "battery_count": 0,
                "lowest_pct": 100,
                "highest_pct": 0
            }
        daily_stats[d]["entries_count"] += 1
        if "Active" in entry["state"]:
            daily_stats[d]["active_count"] += 1
        else:
            daily_stats[d]["standby_count"] += 1

        if "AC" in entry["source"]:
            daily_stats[d]["ac_count"] += 1
        else:
            daily_stats[d]["battery_count"] += 1

        if entry["percent"] is not None:
            daily_stats[d]["lowest_pct"] = min(daily_stats[d]["lowest_pct"], entry["percent"])
            daily_stats[d]["highest_pct"] = max(daily_stats[d]["highest_pct"], entry["percent"])

    daily_summary_list = list(daily_stats.values())

    return {
        "system_info": {
            "computer_name": system_info.get("COMPUTER NAME", "Unknown"),
            "product_name": system_info.get("SYSTEM PRODUCT NAME", "Standard PC"),
            "bios": system_info.get("BIOS", "Unknown"),
            "os_build": system_info.get("OS BUILD", "Windows"),
            "platform_role": system_info.get("PLATFORM ROLE", "Mobile"),
            "connected_standby": system_info.get("CONNECTED STANDBY", "Supported"),
            "report_time": system_info.get("REPORT TIME", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        },
        "battery": {
            "name": name,
            "manufacturer": manufacturer,
            "serial_number": serial_number,
            "chemistry": chemistry,
            "design_capacity_mwh": design_mwh,
            "design_capacity_wh": round(design_mwh / 1000.0, 2) if design_mwh else None,
            "full_charge_capacity_mwh": full_mwh,
            "full_charge_capacity_wh": round(full_mwh / 1000.0, 2) if full_mwh else None,
            "health_percent": health_pct,
            "wear_percent": wear_pct,
            "capacity_lost_mwh": capacity_lost_mwh,
            "cycle_count": cycle_count if cycle_count is not None else "N/A",
            "verdict": verdict_info
        },
        "recent_usage": recent_usage_rows,
        "daily_summary": daily_summary_list,
        "battery_drains": battery_drain_rows,
        "usage_history": usage_history_rows,
        "capacity_history": capacity_history_rows,
        "life_estimates": life_estimates_rows,
        "current_estimate": current_estimate_summary,
        "drain_graph_points": drain_graph_points,
        "total_records": {
            "recent_usage": len(recent_usage_rows),
            "drains": len(battery_drain_rows),
            "capacity_history": len(capacity_history_rows),
            "usage_history": len(usage_history_rows)
        }
    }


def generate_and_parse_report(report_path: Path = Path("battery-report.html")) -> Dict[str, Any]:
    """Execute powercfg command, parse HTML, and attach live status."""
    report_file = Path(report_path)

    error_msg = None
    if sys.platform == "win32":
        try:
            generate_battery_report(report_file)
        except Exception as e:
            error_msg = str(e)

    if not report_file.exists():
        raise FileNotFoundError(
            f"Battery report not found at {report_file}. "
            f"(Generation error: {error_msg})" if error_msg else f"Run powercfg /batteryreport first."
        )

    html = load_html(report_file)
    parsed = parse_battery_report(html)
    parsed["live_status"] = get_live_battery_status()
    parsed["generation_error"] = error_msg
    return parsed
