# Changelog

All notable changes to NetWatch will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.1] - 2025-12-04

### Fixed
- **Gateway Ping & Local Latency Display** - Fixed data mapping issue where Gateway Ping and Local Latency metrics were not displaying in the Homenet tab even when data was available
- **Device Charts Not Showing Devices** - Fixed issue where LAN/WiFi device charts showed "No devices found" when devices had "unknown" connection type (now included in WiFi/Wireless chart)
- **Loaded Ping Mapping** - Added proper mapping for loaded ping (ping under load) metric display

---

## [1.3.0] - 2025-12-03

### Added - Homenet Feature 🏠

This release introduces **Homenet** - a comprehensive internal network monitoring system for testing LAN/WiFi device speeds.

#### New Features
- **Internal Network Speedtest Server** - Built-in Python-based speedtest server (port 5201) for LAN testing without external dependencies
- **Device Scanner** - Automatic discovery of network devices using ARP cache and ping sweep
- **Device Management** - Track, name, and organize discovered network devices
- **LAN/WiFi Device Charts** - Visualize speed performance by connection type
- **Bufferbloat Analysis** - New chart showing Idle Ping vs Loaded Ping vs Gateway Ping
- **Auto-Device Registration** - Devices running speedtests are automatically registered
- **Device Details Modal** - View detailed measurements and history per device
- **Gateway Ping Monitoring** - Measure latency to your router/gateway
- **Local Latency Testing** - Test internal network responsiveness

#### UI Improvements
- **Tab-based Navigation** - Switch between "Internet" and "Homenet" views
- **Server Status Indicator** - Real-time display of internal speedtest server status
- **Auto-start Server** - Server starts automatically on app launch
- **Device Cards** - Visual representation of LAN and WiFi devices with last test results
- **Live Test Progress** - Real-time waveform chart during speedtest execution
- **Idle/Loaded Ping Columns** - Device measurements table now shows both ping types

#### Technical Improvements
- **Continuous Ping Measurement** - Measures ping throughout speedtest to capture true loaded latency
- **is_local Device Flag** - Identify the device running NetWatch
- **SSE Streaming** - Server-Sent Events for real-time speedtest progress updates
- **Separate Internal Database** - `internal_metrics.db` for homenet measurements

### Changed
- Dashboard now has Internet/Homenet view toggle with state persistence
- Improved tooltip display for charts (shows all values including null as "—")

### Fixed
- Chart tooltip now properly displays all data series

---

## [1.2.0] - 2025-12-02

### Added
- Advanced scheduler with multiple time slots per day
- Weekly scheduling mode with day selection
- UI-based scheduler configuration modal
- Global timeline slider for synchronized chart navigation

### Changed
- Scheduler configuration moved from config.yaml to UI
- Improved chart responsiveness and animations

---

## [1.1.0] - 2025-11-28

### Added
- Bufferbloat testing with iperf3
- Historical data table with search and sort
- CSV export functionality
- Delta tracking between measurements

### Changed
- Enhanced glass-morphism UI design
- Improved mobile responsiveness

---

## [1.0.0] - 2025-11-25

### Added
- Initial release
- Ookla Speedtest integration with automatic binary download
- Real-time dashboard with Chart.js visualizations
- SQLite database storage
- Basic scheduling (simple interval mode)
- Flask web application with modern UI
- Linux systemd service support
- Windows batch file launcher
