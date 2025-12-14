#!/bin/bash
# Web UI Debugging Script
# Run this on your server: bash debug_web_ui.sh

echo "=========================================="
echo "Web UI Debugging Information"
echo "=========================================="
echo ""

echo "1. Bot Service Status:"
echo "----------------------------------------"
sudo systemctl status mesh_bot --no-pager -l
echo ""

echo "2. Port 8420 Status:"
echo "----------------------------------------"
sudo netstat -tlnp 2>/dev/null | grep 8420 || sudo ss -tlnp 2>/dev/null | grep 8420 || echo "Port 8420 not found in listening ports"
echo ""

echo "3. Recent Bot Logs (Web UI related):"
echo "----------------------------------------"
sudo journalctl -u mesh_bot -n 100 --no-pager | grep -i "web\|ui\|8420\|error\|exception" || echo "No web UI related logs found"
echo ""

echo "4. Recent Bot Logs (All errors):"
echo "----------------------------------------"
sudo journalctl -u mesh_bot -n 200 --no-pager | grep -i "error\|exception\|traceback\|failed" | tail -20 || echo "No errors found"
echo ""

echo "5. Python Module Import Test:"
echo "----------------------------------------"
cd /opt/meshing-around 2>/dev/null || cd ~/meshing-around 2>/dev/null || echo "Could not find meshing-around directory"
python3 -c "from modules.web_ui import start_web_ui; print('✓ Import successful')" 2>&1
echo ""

echo "6. Web UI File Check:"
echo "----------------------------------------"
if [ -f "/opt/meshing-around/modules/web_ui.py" ]; then
    echo "✓ web_ui.py exists"
    head -5 /opt/meshing-around/modules/web_ui.py
elif [ -f "~/meshing-around/modules/web_ui.py" ]; then
    echo "✓ web_ui.py exists"
    head -5 ~/meshing-around/modules/web_ui.py
else
    echo "✗ web_ui.py not found"
fi
echo ""

echo "7. Git Status:"
echo "----------------------------------------"
cd /opt/meshing-around 2>/dev/null || cd ~/meshing-around 2>/dev/null
git log --oneline -3 2>/dev/null || echo "Not a git repo or git not available"
echo ""

echo "8. Process Check:"
echo "----------------------------------------"
ps aux | grep -E "mesh_bot|web_ui|8420" | grep -v grep || echo "No related processes found"
echo ""

echo "9. Test Local Connection:"
echo "----------------------------------------"
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" http://localhost:8420 2>&1 || echo "Connection failed"
echo ""

echo "=========================================="
echo "Debugging complete!"
echo "=========================================="

