#!/bin/bash
# Web UI Debugging Script
# Run this on your server: bash debug_web_ui.sh

set -e  # Exit on error, but we'll catch errors manually
exec 2>&1  # Redirect stderr to stdout

echo "=========================================="
echo "Web UI Debugging Information"
echo "Date: $(date)"
echo "=========================================="
echo ""

echo "1. Bot Service Status:"
echo "----------------------------------------"
sudo systemctl status mesh_bot --no-pager -l || echo "ERROR: Could not get service status"
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
MESH_DIR=""
if [ -d "/opt/meshing-around" ]; then
    MESH_DIR="/opt/meshing-around"
elif [ -d "$HOME/meshing-around" ]; then
    MESH_DIR="$HOME/meshing-around"
elif [ -d "./meshing-around" ]; then
    MESH_DIR="./meshing-around"
else
    echo "ERROR: Could not find meshing-around directory"
    echo "Searched: /opt/meshing-around, $HOME/meshing-around, ./meshing-around"
fi

if [ -n "$MESH_DIR" ]; then
    echo "Using directory: $MESH_DIR"
    cd "$MESH_DIR" || exit 1
    python3 -c "from modules.web_ui import start_web_ui; print('✓ Import successful')" 2>&1 || echo "✗ Import failed"
else
    echo "Skipping import test - directory not found"
fi
echo ""

echo "6. Web UI File Check:"
echo "----------------------------------------"
if [ -n "$MESH_DIR" ] && [ -f "$MESH_DIR/modules/web_ui.py" ]; then
    echo "✓ web_ui.py exists at: $MESH_DIR/modules/web_ui.py"
    echo "First 5 lines:"
    head -5 "$MESH_DIR/modules/web_ui.py"
else
    echo "✗ web_ui.py not found"
    echo "Searched: $MESH_DIR/modules/web_ui.py"
fi
echo ""

echo "7. Git Status:"
echo "----------------------------------------"
if [ -n "$MESH_DIR" ] && [ -d "$MESH_DIR/.git" ]; then
    cd "$MESH_DIR" || exit 1
    echo "Recent commits:"
    git log --oneline -3 2>&1 || echo "Git command failed"
    echo ""
    echo "Current status:"
    git status --short 2>&1 || echo "Git status failed"
else
    echo "Not a git repository or .git directory not found"
fi
echo ""

echo "8. Process Check:"
echo "----------------------------------------"
ps aux | grep -E "mesh_bot|web_ui|8420" | grep -v grep || echo "No related processes found"
echo ""

echo "9. Test Local Connection:"
echo "----------------------------------------"
if command -v curl >/dev/null 2>&1; then
    curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" http://localhost:8420 2>&1 || echo "Connection failed - curl error"
else
    echo "curl not available, trying wget..."
    if command -v wget >/dev/null 2>&1; then
        wget -q -O /dev/null http://localhost:8420 2>&1 && echo "Connection successful" || echo "Connection failed"
    else
        echo "Neither curl nor wget available"
    fi
fi
echo ""

echo "=========================================="
echo "Debugging complete!"
echo "=========================================="

