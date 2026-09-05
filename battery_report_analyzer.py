#!/usr/bin/env python3
"""
Battery Health Report Analyzer
================================
Parses the HTML report produced by Windows' built-in `powercfg /batteryreport`
command and prints/exports a clean battery health summary:

  - Battery info (name, manufacturer, chemistry, cycle count)
  - Design capacity vs full charge capacity, and computed health %
  - Capacity history trend (how much it has degraded over time)
  - Estimated battery life (at full charge vs. at original design capacity)
  - A plain-English verdict on battery condition

USAGE
-----
  # 1) Generate a fresh report and analyze it (Windows only)
  py -m battery_report_analyzer --generate

  # 2) Analyze a report you already generated
  py -m battery_report_analyzer --input battery-report.html

  # 3) Also export data
  py -m battery_report_analyzer --input battery-report.html \
      --json summary.json --csv history.csv --plot chart.png

REQUIREMENTS
------------
  pip install beautifulsoup4
  pip install matplotlib      # only needed if you use --plot

NOTE ON GENERATING THE REPORT
------------------------------
`powercfg` is a Windows-only tool. On Windows, open Command Prompt / PowerShell
and run:
    powercfg /batteryreport /output "%USERPROFILE%\\battery-report.html"
This script can run that command for you with --generate, or you can just
point --input at a report you already generated.
"""

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# pyright: reportMissingImports=false
try:
    from bs4 import BeautifulSoup
except ImportError:
    install_cmd = f'"{sys.executable}" -m pip install beautifulsoup4'
    if shutil.which("py"):
        install_cmd = "py -m pip install beautifulsoup4"
    sys.exit(
        "Missing dependency. Install it with:\n"
        f"    {install_cmd}\n"
        "Then run the analyzer with the same Python launcher, for example:\n"
        "    py -m battery_report_analyzer --input battery-report.html"
    )


# ---------------------------------------------------------------------------
# Step 1: Generate the report (Windows only)
# ---------------------------------------------------------------------------

def generate_report(output_path: Path) -> Path:
    """Run `powercfg /batteryreport` to create the HTML report."""
    if sys.platform != "win32":
        sys.exit("--generate only works on Windows (powercfg is a Windows-only tool).")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["powercfg", "/batteryreport", "/output", str(output_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"powercfg failed:\n{result.stderr or result.stdout}")
    if not output_path.exists():
        sys.exit("powercfg ran but no report file was found at the expected path.")
    print(f"Report generated at {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Step 2: Load + decode the HTML
# (powercfg has been known to write this file as UTF-16 on some Windows
#  builds and UTF-8 on others, so we sniff the byte-order-mark instead of
#  assuming one encoding.)
# ---------------------------------------------------------------------------

def load_html(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe"):
        return raw.decode("utf-16-le")
    if raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16-be")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    for enc in ("utf-8", "utf-16", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Step 3: Generic table parser
# The report is a series of <h2>Section title</h2> followed by a <table>.
# Some tables are "label: value" pairs (Installed batteries), others are
# proper multi-column tables with a header row (capacity history, etc).
# We detect which kind each table is instead of hard-coding either shape.
# ---------------------------------------------------------------------------

def parse_table(table):
    rows = table.find_all("tr")
    if not rows:
        return None

    row_cells = []
    for r in rows:
        cells = r.find_all(["th", "td"])
        if cells:
            row_cells.append(cells)
    if not row_cells:
        return None

    first_cells = row_cells[0]
    first_row_is_header = all(c.name == "th" for c in first_cells)
    same_width_rows_after_header = (
        first_row_is_header
        and len(row_cells) > 1
        and any(len(cells) == len(first_cells) for cells in row_cells[1:])
        and len(first_cells) > 2
    )

    if same_width_rows_after_header:
        headers = [c.get_text(strip=True) for c in first_cells]
        data = []
        for cells in row_cells[1:]:
            values = [c.get_text(strip=True) for c in cells]
            if len(values) == len(headers):
                data.append(dict(zip(headers, values)))
        return {"type": "tabular", "headers": headers, "rows": data}

    kv = {}
    for cells in row_cells:
        if len(cells) >= 2:
            # Skip the header row in a 2-column "Battery / Information" layout
            # so the actual label/value pairs are parsed correctly.
            if len(cells) == 2 and all(c.name == "th" for c in cells):
                continue
            key = cells[0].get_text(strip=True)
            value = cells[1].get_text(strip=True)
            if key:
                kv[key] = value
    return {"type": "keyvalue", "data": kv}


def parse_report(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    sections = {}
    for h2 in soup.find_all("h2"):
        title = h2.get_text(strip=True)
        table = h2.find_next("table")
        if table:
            parsed = parse_table(table)
            if parsed:
                sections[title] = parsed
    return sections


# ---------------------------------------------------------------------------
# Step 4: Turn parsed sections into a clean health summary
# ---------------------------------------------------------------------------

def get_ci(d: dict, *names):
    """Case-insensitive dict lookup, trying each name in order."""
    lower_map = {k.lower(): v for k, v in d.items()}
    for name in names:
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    return None


def get_section(sections: dict, *names):
    """Case-insensitive section lookup, returning an empty dict when missing."""
    lower_map = {k.lower(): v for k, v in sections.items()}
    for name in names:
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    return {}


def to_mwh(value):
    """Convert capacities like '56,289 mWh', '3.1 Wh', or '1.2 kWh' to integer mWh."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(round(value))

    text = str(value).strip()
    if not text:
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


def health_verdict(pct: float) -> str:
    if pct >= 90:
        return "Excellent - essentially like new"
    if pct >= 80:
        return "Good - normal wear for a used battery"
    if pct >= 60:
        return "Fair - noticeably degraded; many manufacturers consider under 80% eligible for warranty replacement"
    return "Poor - near end of life, replacement is worth considering"


def build_summary(sections: dict) -> dict:
    installed = get_section(sections, "Installed batteries", "Installed Batteries").get("data", {})

    design = to_mwh(get_ci(installed, "Design Capacity"))
    full = to_mwh(get_ci(installed, "Full Charge Capacity"))
    health_pct = round(full / design * 100, 1) if design and full and design > 0 else None
    cycle_count = get_ci(installed, "Cycle Count")

    summary = {
        "name": get_ci(installed, "Name"),
        "manufacturer": get_ci(installed, "Manufacturer"),
        "chemistry": get_ci(installed, "Chemistry"),
        "cycle_count": cycle_count if cycle_count else "Not reported by firmware",
        "design_capacity_mwh": design,
        "full_charge_capacity_mwh": full,
        "health_percent": health_pct,
        "verdict": health_verdict(health_pct) if health_pct is not None else "Could not compute (capacity data missing from report)",
        "capacity_history": get_section(sections, "Battery capacity history", "Battery Capacity History").get("rows", []),
        "life_estimates": get_section(sections, "Battery life estimates", "Battery Life Estimates").get("rows", []),
    }
    return summary


# ---------------------------------------------------------------------------
# Step 5: Display / export
# ---------------------------------------------------------------------------

def print_summary(summary: dict):
    line = "=" * 52
    print("\n" + line)
    print(" BATTERY HEALTH SUMMARY")
    print(line)
    print(f" Name            : {summary['name']}")
    print(f" Manufacturer    : {summary['manufacturer']}")
    print(f" Chemistry       : {summary['chemistry']}")
    print(f" Cycle count     : {summary['cycle_count']}")
    print("-" * 52)
    d, f, h = summary["design_capacity_mwh"], summary["full_charge_capacity_mwh"], summary["health_percent"]
    print(f" Design capacity      : {d:,} mWh" if d else " Design capacity      : N/A")
    print(f" Full charge capacity : {f:,} mWh" if f else " Full charge capacity : N/A")
    print(f" Battery health       : {h}%" if h is not None else " Battery health       : N/A")
    print(f" Verdict              : {summary['verdict']}")
    print(line)

    if summary["capacity_history"]:
        print("\n Capacity history (most recent first):")
        for row in summary["capacity_history"][:12]:
            print("  ", row)

    if summary["life_estimates"]:
        print("\n Estimated battery life:")
        for row in summary["life_estimates"]:
            print("  ", row)
    print()


def save_json(summary: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved JSON summary to {path}")


def save_csv(summary: dict, path: Path):
    history = summary.get("capacity_history", [])
    if not history:
        print("No capacity history rows found in the report - skipping CSV export.")
        return
    fieldnames = list(history[0].keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(history)
    print(f"Saved capacity history CSV to {path}")


def plot_history(summary: dict, path: Path = None):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        sys.exit("Plotting needs matplotlib. Install it with:\n    pip install matplotlib")

    history = summary.get("capacity_history", [])
    if not history:
        print("No capacity history to plot.")
        return

    periods, full_vals, design_vals = [], [], []
    for row in reversed(history):  # oldest -> newest for a left-to-right timeline
        period_key = next((k for k in row if "PERIOD" in k.upper()), None)
        full_key = next((k for k in row if "FULL CHARGE" in k.upper()), None)
        design_key = next((k for k in row if "DESIGN" in k.upper()), None)
        if period_key and full_key:
            periods.append(row[period_key])
            full_vals.append(to_mwh(row[full_key]))
            design_vals.append(to_mwh(row[design_key]) if design_key else None)

    plt.figure(figsize=(10, 5))
    plt.plot(periods, full_vals, marker="o", label="Full charge capacity")
    if any(design_vals):
        plt.plot(periods, design_vals, linestyle="--", label="Design capacity")
    plt.xticks(rotation=45, ha="right")
    plt.ylabel("mWh")
    plt.title("Battery capacity over time")
    plt.legend()
    plt.tight_layout()

    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(path)
        print(f"Saved chart to {path}")
    else:
        plt.show()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Analyze a Windows powercfg battery report.")
    parser.add_argument("--generate", action="store_true",
                         help="Run powercfg to generate a fresh report first (Windows only).")
    parser.add_argument("--input", default="battery-report.html",
                         help="Path to the battery report HTML file (default: battery-report.html).")
    parser.add_argument("--json", help="Save the summary as JSON to this path.")
    parser.add_argument("--csv", help="Save the capacity history table as CSV to this path.")
    parser.add_argument("--plot", nargs="?", const="__show__",
                         help="Plot the capacity history trend. Give a file path to save it, "
                              "or leave blank to just display it.")
    args = parser.parse_args()

    report_path = Path(args.input)

    if args.generate:
        report_path = generate_report(report_path)
    elif not report_path.exists():
        sys.exit(f"Report not found at {report_path}.\n"
                  f"Run `powercfg /batteryreport` first, or pass --generate.")

    html = load_html(report_path)
    sections = parse_report(html)
    summary = build_summary(sections)

    print_summary(summary)

    if args.json:
        save_json(summary, Path(args.json))
    if args.csv:
        save_csv(summary, Path(args.csv))
    if args.plot:
        plot_path = None if args.plot == "__show__" else Path(args.plot)
        plot_history(summary, plot_path)


if __name__ == "__main__":
    main()
