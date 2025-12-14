#!/bin/bash
# Script to check what's using port 8420 (Web UI) or 8421 (MCP Server)

PORT=${1:-8420}

echo "Checking what's using port $PORT..."
echo ""

# Try lsof first
if command -v lsof &> /dev/null; then
    echo "=== Using lsof ==="
    sudo lsof -i :$PORT
    echo ""
fi

# Try fuser as fallback
if command -v fuser &> /dev/null; then
    echo "=== Using fuser ==="
    sudo fuser $PORT/tcp
    echo ""
fi

# Try ss (modern Linux)
if command -v ss &> /dev/null; then
    echo "=== Using ss ==="
    sudo ss -tlnp | grep :$PORT
    echo ""
fi

# Try netstat as last resort
if command -v netstat &> /dev/null; then
    echo "=== Using netstat ==="
    sudo netstat -tlnp | grep :$PORT
    echo ""
fi

echo "To kill a process, use: sudo kill -9 <PID>"
echo "Or to kill all Python processes using this port:"
echo "  sudo pkill -f 'python.*web_ui'"
echo "  sudo pkill -f 'python.*mesh_bot'"

