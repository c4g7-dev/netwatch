# NetWatch - Linux Quick Start Guide

## 🚀 One-Command Installation

```bash
curl -sSL https://raw.githubusercontent.com/c4g7-dev/netwatch/master/install-linux.sh | sudo bash
```

Or clone and install:

```bash
git clone https://github.com/c4g7-dev/netwatch.git
cd netwatch
sudo bash install-linux.sh
```

## 📋 What Gets Installed

- **Location:** `/opt/netwatch`
- **Service User:** `netwatch` (non-privileged)
- **Service:** `netwatch.service` (systemd)
- **Port:** 8000 (configurable in `config.yaml`)
- **Data:** `/opt/netwatch/data/` (SQLite database, exports)
- **Logs:** `/opt/netwatch/logs/` + systemd journal

## 🎮 Service Management

```bash
# Status
systemctl status netwatch
systemctl is-active netwatch

# Start/Stop/Restart
sudo systemctl start netwatch
sudo systemctl stop netwatch
sudo systemctl restart netwatch

# Enable/Disable auto-start
sudo systemctl enable netwatch
sudo systemctl disable netwatch

# View logs (live)
journalctl -u netwatch -f

# View last 50 log entries
journalctl -u netwatch -n 50

# View logs from today
journalctl -u netwatch --since today

# View logs with errors only
journalctl -u netwatch -p err -n 50
```

## ⚙️ Configuration

Edit the config file:
```bash
sudo nano /opt/netwatch/config.yaml
```

After changes, restart:
```bash
sudo systemctl restart netwatch
```

## 🔥 Firewall Configuration

### UFW (Ubuntu/Debian)
```bash
sudo ufw allow 8000/tcp
sudo ufw status
```

### firewalld (CentOS/RHEL/Fedora)
```bash
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
sudo firewall-cmd --list-ports
```

### iptables
```bash
sudo iptables -A INPUT -p tcp --dport 8000 -j ACCEPT
sudo iptables-save | sudo tee /etc/iptables/rules.v4
```

## 🌐 Accessing the Dashboard

**Local:** http://localhost:8000
**Network:** http://YOUR_SERVER_IP:8000

Find your IP:
```bash
hostname -I
ip addr show
```

## 🔄 Updating NetWatch

```bash
cd /opt/netwatch
sudo systemctl stop netwatch
sudo -u netwatch git pull origin master
sudo -u netwatch .venv/bin/pip install -r requirements.txt --upgrade
sudo systemctl start netwatch
sudo systemctl status netwatch
```

## 🔧 Manual Operations

Run speedtest manually:
```bash
sudo -u netwatch /opt/netwatch/.venv/bin/python -c "
from app.config import load_config
from app.measurements.speedtest_runner import run_ookla_speedtest
result = run_ookla_speedtest(load_config('/opt/netwatch/config.yaml'))
print(result)
"
```

Or use the API:
```bash
curl -X POST http://localhost:8000/api/manual/speedtest
```

## 🗑️ Uninstallation

```bash
# Stop and disable service
sudo systemctl stop netwatch
sudo systemctl disable netwatch
sudo rm /etc/systemd/system/netwatch.service
sudo systemctl daemon-reload

# Remove files
sudo rm -rf /opt/netwatch

# Remove user (optional)
sudo userdel netwatch

# Remove firewall rule
sudo ufw delete allow 8000/tcp  # UFW
sudo firewall-cmd --permanent --remove-port=8000/tcp  # firewalld
sudo firewall-cmd --reload
```

## 🐛 Troubleshooting

### Service won't start
```bash
# Check logs
journalctl -u netwatch -n 100

# Test manual start
sudo -u netwatch /opt/netwatch/.venv/bin/python /opt/netwatch/main.py

# Check permissions
ls -la /opt/netwatch
sudo chown -R netwatch:netwatch /opt/netwatch
```

### Port already in use
```bash
# Find what's using port 8000
sudo lsof -i :8000
sudo netstat -tulpn | grep :8000

# Kill the process (if needed)
sudo kill -9 <PID>

# Or change port in config
sudo nano /opt/netwatch/config.yaml
# Change: port: 8001
sudo systemctl restart netwatch
```

### Homenet speedtest server won't start (Port 5201 conflict)
If you see "Port 5201 is already in use" errors in the logs:

```bash
# Check what's using port 5201
sudo lsof -i :5201

# Common culprit: iperf3 server running as a separate service
sudo systemctl stop iperf3
sudo systemctl disable iperf3  # Prevent auto-start

# Restart NetWatch
sudo systemctl restart netwatch

# Verify homenet server started
journalctl -u netwatch -n 50 | grep "Internal speedtest"
```

**Note:** NetWatch's homenet feature uses its own pure Python speedtest server on port 5201 and does NOT require iperf3 to be installed. If you have a standalone iperf3 server running, it will conflict with NetWatch's internal server.

### Bufferbloat tests failing (iperf3 not found)
Bufferbloat tests require the `iperf3` binary to be installed and accessible in PATH:

```bash
# Install iperf3
sudo apt install iperf3       # Debian/Ubuntu
sudo yum install iperf3       # CentOS/RHEL
sudo dnf install iperf3       # Fedora

# Verify iperf3 is accessible
which iperf3
iperf3 --version

# Check if netwatch user can run iperf3
sudo -u netwatch which iperf3

# Restart NetWatch
sudo systemctl restart netwatch
```

**Note:** If iperf3 is not installed, the bufferbloat tests will be skipped automatically without crashing the service. You will see warnings in the logs, but internet speedtests and homenet tests will continue to work normally.

### Python/pip issues
```bash
# Reinstall dependencies
cd /opt/netwatch
sudo -u netwatch .venv/bin/pip install --upgrade pip
sudo -u netwatch .venv/bin/pip install -r requirements.txt --force-reinstall
```

### Database locked
```bash
# Check for multiple instances
ps aux | grep netwatch
sudo systemctl status netwatch

# Kill duplicate processes
sudo killall python

# Restart service cleanly
sudo systemctl restart netwatch
```

## 📊 Performance Tuning

### Adjust measurement interval
Measurement scheduling is now configured through the **dashboard UI**:

1. Open NetWatch at http://localhost:8000
2. Click the ⚙️ button next to the scheduler status
3. Choose your scheduling mode:
   - **Simple:** 24/7 with fixed interval (5-120 min)
   - **Weekly:** Select specific days and time windows
   - **Advanced:** Configure multiple time slots per day

### Limit log size
```bash
# Configure systemd journal
sudo nano /etc/systemd/journald.conf
```
Add:
```ini
SystemMaxUse=100M
RuntimeMaxUse=100M
```
Then:
```bash
sudo systemctl restart systemd-journald
```

### Database maintenance
```bash
# Vacuum database (reclaim space)
sudo -u netwatch sqlite3 /opt/netwatch/data/metrics.db "VACUUM;"

# Check database size
du -h /opt/netwatch/data/metrics.db

# Backup database
sudo cp /opt/netwatch/data/metrics.db /opt/netwatch/data/metrics.db.backup
```

## 🔐 Security Best Practices

### Restrict network access
```bash
# Only allow from specific IP
sudo ufw allow from 192.168.1.0/24 to any port 8000

# Or use nginx reverse proxy with authentication
sudo apt install nginx
```

### Run behind nginx (recommended)
```nginx
server {
    listen 80;
    server_name netwatch.example.com;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        
        # Optional: Basic auth
        auth_basic "NetWatch Dashboard";
        auth_basic_user_file /etc/nginx/.htpasswd;
    }
}
```

## 📈 Monitoring NetWatch Itself

```bash
# Check service health
systemctl is-active netwatch

# Monitor resource usage
top -p $(pgrep -f "netwatch")
ps aux | grep netwatch

# Check disk usage
df -h /opt/netwatch
du -sh /opt/netwatch/*

# Network connections
sudo netstat -tulpn | grep :8000
```

## 🆘 Getting Help

- **Documentation:** https://github.com/c4g7-dev/netwatch
- **Issues:** https://github.com/c4g7-dev/netwatch/issues
- **Discussions:** https://github.com/c4g7-dev/netwatch/discussions
