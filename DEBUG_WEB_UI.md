# Web UI Debugging Guide

Run these commands on your server and share the output:

## 1. Check if the bot is running
```bash
sudo systemctl status mesh_bot
```

## 2. Check if port 8420 is listening
```bash
sudo netstat -tlnp | grep 8420
# OR
sudo ss -tlnp | grep 8420
# OR
sudo lsof -i :8420
```

## 3. Check bot logs for Web UI messages
```bash
sudo journalctl -u mesh_bot -n 100 --no-pager | grep -i "web\|ui\|8420"
```

## 4. Check for any errors in bot logs
```bash
sudo journalctl -u mesh_bot -n 200 --no-pager | grep -i "error\|exception\|traceback\|failed"
```

## 5. Check if the web_ui module can be imported
```bash
cd /opt/meshing-around
python3 -c "from modules.web_ui import start_web_ui; print('Import successful')"
```

## 6. Try starting Web UI manually (test if it works standalone)
```bash
cd /opt/meshing-around
python3 -m modules.web_ui
# This should start the web UI on port 8420
# Press Ctrl+C to stop it
```

## 7. Check firewall/iptables rules
```bash
sudo iptables -L -n | grep 8420
sudo ufw status | grep 8420
```

## 8. Check if there are any Python errors
```bash
cd /opt/meshing-around
python3 -c "import modules.web_ui" 2>&1
```

## 9. Check the web_ui.py file exists and is readable
```bash
ls -la /opt/meshing-around/modules/web_ui.py
head -20 /opt/meshing-around/modules/web_ui.py
```

## 10. Check recent git changes
```bash
cd /opt/meshing-around
git log --oneline -5
git status
```

## 11. Test if you can reach the port locally
```bash
curl http://localhost:8420
# OR
curl http://127.0.0.1:8420
```

## 12. Check what user the service runs as
```bash
cat /etc/systemd/system/mesh_bot.service | grep User
```

## Quick Test - Start Web UI Standalone
```bash
cd /opt/meshing-around
sudo systemctl stop mesh_bot
python3 -m modules.web_ui &
sleep 2
curl http://localhost:8420
pkill -f "modules.web_ui"
sudo systemctl start mesh_bot
```

## What to Share
Please share the output of:
1. `sudo systemctl status mesh_bot`
2. `sudo journalctl -u mesh_bot -n 100 | grep -i "web\|ui\|error"`
3. `sudo netstat -tlnp | grep 8420` (or equivalent)
4. `python3 -c "from modules.web_ui import start_web_ui; print('OK')"`

