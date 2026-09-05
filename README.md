# ⚡ VoltPulse - Battery Health & Diagnostics Dashboard

VoltPulse is a modern, real-time Windows Battery Health, Analytics & Diagnostics web application. It automates Windows `powercfg /batteryreport`, parses deep battery metrics and capacity degradation histories, and displays them on a sleek, interactive dashboard.

---

## 🛠️ Technologies & Tools Used

This project is built using the following technologies, libraries, and tools:

### 🖥️ Backend
- **[Python 3](https://www.python.org/)** — Core backend programming language.
- **[Flask](https://flask.palletsprojects.com/)** — Lightweight web server and RESTful API framework to serve the dashboard and API endpoints.
- **[BeautifulSoup4 (`bs4`)](https://www.crummy.com/software/BeautifulSoup/)** — HTML parsing engine used to scrape, extract, and structure data from the Windows-generated battery report.
- **[psutil](https://github.com/giampaolo/psutil)** — Cross-platform hardware monitoring library used for real-time live battery status (charge percentage, power plug state, discharge metrics, runtime).
- **Python Standard Library (`subprocess`, `csv`, `json`, `pathlib`, `re`)** — Used for executing system commands, data processing, and CSV export generation.

### 🎨 Frontend & UI
- **HTML5** — Clean, semantic markup for dashboard layout and data cards.
- **CSS3 (Custom Vanilla CSS)** — Modern dark-mode UI with:
  - Glassmorphism & backdrop-blur effects
  - Responsive CSS Grid & Flexbox layouts
  - Glowing neon gradients & dynamic battery health color coding
  - Smooth hover transitions and micro-animations
- **JavaScript (ES6+)** — Client-side application logic:
  - Asynchronous data fetching (`fetch` API)
  - Real-time periodic live telemetry polling
  - Dynamic SVG battery health gauge rendering
  - CSV report download generation
- **[Chart.js](https://www.chartjs.org/)** — Interactive canvas charting library for visualizing capacity degradation history over time.
- **[Lucide Icons](https://lucide.dev/)** — Modern, clean vector icon set.
- **[Google Fonts](https://fonts.google.com/)** — Typography using *Outfit*, *Inter*, and *JetBrains Mono*.

### ⚙️ System & OS Integration
- **Windows `powercfg /batteryreport`** — Native Windows ACPI power management diagnostic utility.
- **Windows Batch Script (`.bat`)** — One-click launcher script with automatic Python path detection (Anaconda, standard Python, PATH).

---

## 🚀 Quick Start / Launch Details

### 1. Prerequisites
Ensure you have **Python 3.8+** installed on your Windows system.

Install the required Python packages:
```bash
pip install flask beautifulsoup4 psutil
```

---

### 2. Running the Application

You can launch the server using either method:

#### Option A: Quick Launch via Batch Script (Recommended)
Double-click [`run.bat`](run.bat) in the project root directory or run it from PowerShell / Command Prompt:
```powershell
.\run.bat
```

#### Option B: Direct Python Execution
Run [`app.py`](app.py) directly:
```powershell
python app.py
```

---

### 3. Accessing the Dashboard

Once started, open your web browser and navigate to:

👉 **[http://localhost:5000](http://127.0.0.1:5000/)** (or `http://127.0.0.1:5000`)

---

## ✨ Features

- 🔋 **Battery Health Score & Verdict**: Calculates accurate wear percentage, full-charge vs. design capacity, cycle count, and gives an actionable health evaluation.
- ⚡ **Live Real-time Telemetry**: Auto-refreshing live battery percentage, power plug status, and discharge rate.
- 📈 **Capacity History Charts**: Visualizes historical degradation curves and full charge capacity trends over time with Chart.js.
- ⏱️ **Battery Life Estimates**: Side-by-side comparison of active and standby runtimes at full charge vs. design capacity.
- 🔄 **One-Click Fresh Report Generation**: Generate and re-analyze real-time Windows `powercfg` reports on demand.
- 💾 **Data Exports**: Export capacity degradation history as CSV or view/download the raw Windows HTML report.

---

## 📁 Project Structure

```
laptop_battery_analyser/
├── app.py                      # Flask application entrypoint & API routes
├── battery_parser.py           # Report generation, HTML parsing & live metrics logic
├── battery_report_analyzer.py  # Standalone CLI analysis script
├── run.bat                     # Quick launcher batch file for Windows
├── README.md                   # Project documentation, tech stack & launch instructions
├── templates/
│   └── index.html              # Main dashboard UI template
└── static/
    ├── css/
    │   └── style.css           # Modern dark-mode UI stylesheet
    └── js/
        └── app.js              # Interactive dashboard logic & charts
```

---

## 🔌 API Endpoints

- `GET /` - Main interactive dashboard UI
- `GET /api/battery-data` - JSON payload of parsed battery health, specs, usage history, and live stats
- `POST /api/refresh-report` - Triggers Windows `powercfg /batteryreport` and parses fresh data
- `GET /api/live-status` - Quick real-time polling endpoint for live charging state and battery percentage
- `GET /api/export-csv` - Downloads battery capacity history as a CSV file
- `GET /raw-report` - Serves the raw Windows-generated HTML battery report
