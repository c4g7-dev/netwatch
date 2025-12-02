# 🚀 NetWatch - Self-Hosted Network Monitor

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/Flask-3.0+-green.svg" alt="Flask">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg" alt="Platform">
</p>

A beautiful, self-hosted network performance monitoring dashboard with real-time speedtest measurements, bufferbloat detection, and historical trend analysis. Built with Flask and featuring a modern glass-morphism UI.

## ✨ Features

### 📊 Performance Monitoring
- **Ookla Speedtest Integration** - Automatic binary download and execution
- **Bufferbloat Testing** - iperf3-based latency under load measurements
- **8 Key Metrics** - Download, Upload, Ping (Idle), Jitter, Loaded Latency (↓/↑), Download/Upload Latency
- **Real-time Updates** - Live dashboard with animated metrics and sparklines

### 📈 Data Visualization
- **Interactive Charts** - Time-series graphs with Chart.js
- **Trend Analysis** - 24h, 7d, 30d, and custom date ranges
- **Global Timeline Slider** - Synchronize all charts to specific time windows
- **Historical Data Table** - Searchable, sortable measurement history

### ⚙️ Automation & Scheduling
- **Built-in Scheduler** - Configurable interval-based measurements (default: 30 min)
- **Manual Triggers** - On-demand speedtest and bufferbloat tests
- **Automatic Retries** - Resilient measurement execution with error handling

### 💾 Data Management
- **SQLite Storage** - Lightweight, file-based database
- **CSV Export** - Filtered and complete dataset exports
- **Raw JSON Logging** - Complete measurement data preservation
- **Delta Tracking** - Automatic comparison with previous measurements

### 🎨 Modern UI
- **Glass-morphism Design** - Frosted glass effects inspired by shadcn/ui
- **Responsive Layout** - Mobile-friendly adaptive design
- **Dark Theme** - Easy on the eyes with gradient backgrounds
- **Toast Notifications** - Real-time feedback for user actions
- **Animated Metrics** - Count-up animations and progress bars

## 🚀 Quick Start

### Prerequisites
- Python 3.10 or higher
- pip (Python package manager)
- Internet connection (for Ookla binary download)

### Installation

#### Option 1: Automated Installer (Recommended)
```bash
# Clone the repository
git clone https://github.com/c4g7-dev/netwatch.git
cd netwatch

# Run the installer
python installer.py
```

The installer will:
- ✅ Create virtual environment
- ✅ Install Python dependencies
- ✅ Download Ookla Speedtest CLI binary
- ✅ Initialize SQLite database
- ✅ Create folder structure

#### Option 2: Manual Installation
```bash
# Clone the repository
git clone https://github.com/c4g7-dev/netwatch.git
cd netwatch

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

### 🏃 Running NetWatch

```bash
# Activate virtual environment (if not already activated)
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Start the server
python main.py
```

The dashboard will be available at: **http://localhost:8000**

## 📁 Project Structure

```
netwatch/
├── app/
│   ├── db/                    # Database models and session management
│   ├── measurements/          # Speedtest and bufferbloat runners
│   ├── web/                   # Flask application and routes
│   │   ├── static/
│   │   │   ├── css/          # Glass-morphism styles
│   │   │   └── js/           # Dashboard logic and charts
│   │   └── templates/        # HTML templates
│   ├── config.py             # Configuration loader
│   └── scheduler.py          # Automated measurement scheduling
├── bin/                      # Downloaded binaries (speedtest, iperf3)
├── data/                     # SQLite database and CSV exports
├── logs/                     # Application logs
├── config.yaml              # User configuration
├── installer.py             # Automated setup script
├── updater.py               # Binary update utility
├── main.py                  # Application entry point
└── requirements.txt         # Python dependencies
```

## ⚙️ Configuration

Edit `config.yaml` to customize NetWatch:

```yaml
# Scheduler Configuration
scheduler:
  enabled: true
  interval_minutes: 30

# Measurement Settings
measurements:
  auto_download_ookla: true
  speedtest_timeout: 60
  bufferbloat_timeout: 120

# Server Configuration
server:
  host: "0.0.0.0"
  port: 8000
  debug: false

# Database
database:
  path: "data/metrics.db"

# Logging
logging:
  level: "INFO"
  path: "logs/netwatch.log"
```

## 🔧 Advanced Usage

### Manual Test Triggers

**Via Dashboard:**
- Click "Speedtest" button for immediate speed measurement
- Click "Bufferbloat" button for latency-under-load test

**Via API:**
```bash
# Trigger speedtest
curl -X POST http://localhost:8000/api/manual/speedtest

# Trigger bufferbloat test
curl -X POST http://localhost:8000/api/manual/bufferbloat
```

### Data Export

**Via Dashboard:**
- Click "Export CSV" to download filtered data based on current time range

**Via API:**
```bash
# Export all data
curl "http://localhost:8000/api/export/csv?scope=complete" -o measurements.csv

# Export filtered data
curl "http://localhost:8000/api/export/csv?start=2025-12-01T00:00:00Z&end=2025-12-02T23:59:59Z" -o measurements.csv
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard UI |
| `/api/status` | GET | System status and configuration |
| `/api/summary/latest` | GET | Latest measurement with delta |
| `/api/measurements` | GET | Historical measurements (supports filtering) |
| `/api/manual/speedtest` | POST | Trigger manual speedtest |
| `/api/manual/bufferbloat` | POST | Trigger manual bufferbloat test |
| `/api/export/csv` | GET | Export data to CSV |

## 🐳 Docker Deployment (Coming Soon)

```bash
docker run -d \
  --name netwatch \
  -p 8000:8000 \
  -v ./data:/app/data \
  -v ./config.yaml:/app/config.yaml \
  c4g7dev/netwatch:latest
```

## 🔄 Updating

### Update Ookla Binary
```bash
python updater.py --component speedtest
```

### Update Application
```bash
git pull origin main
pip install -r requirements.txt --upgrade
```

## 🛠️ Troubleshooting

### Speedtest Not Working
- **Issue:** Ookla binary download failed
- **Solution:** Manually download from [speedtest.net/apps/cli](https://www.speedtest.net/apps/cli) and place in `bin/` folder

### Bufferbloat Tests Failing
- **Issue:** iperf3 not found
- **Solution:** 
  ```bash
  # Ubuntu/Debian
  sudo apt-get install iperf3
  
  # Windows
  # Download from https://iperf.fr/iperf-download.php
  # Place iperf3.exe in bin/ folder
  
  # macOS
  brew install iperf3
  ```

### Database Locked Errors
- **Issue:** SQLite database locked
- **Solution:** Ensure only one instance of NetWatch is running

### Port Already in Use
- **Issue:** Port 8000 is occupied
- **Solution:** Change port in `config.yaml` or stop conflicting service

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Ookla Speedtest CLI](https://www.speedtest.net/apps/cli) - Network performance testing
- [Flask](https://flask.palletsprojects.com/) - Web framework
- [Chart.js](https://www.chartjs.org/) - Data visualization
- [shadcn/ui](https://ui.shadcn.com/) - UI design inspiration

## 📊 Roadmap

- [ ] Docker support with docker-compose
- [ ] Prometheus metrics export
- [ ] Grafana dashboard templates
- [ ] Multi-server monitoring
- [ ] Email/webhook alerts for degraded performance
- [ ] Mobile app (React Native)
- [ ] Historical data comparison (month-over-month)
- [ ] ISP outage detection and logging
- [ ] Bandwidth quota tracking

## 📧 Support

- **Issues:** [GitHub Issues](https://github.com/c4g7-dev/netwatch/issues)
- **Discussions:** [GitHub Discussions](https://github.com/c4g7-dev/netwatch/discussions)

---

<p align="center">Made with ❤️ for network monitoring enthusiasts</p>
<p align="center">⭐ Star this repository if you find it useful!</p>
