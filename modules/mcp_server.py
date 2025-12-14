#!/usr/bin/env python3
"""
MCP (Model Context Protocol) Server Module
Exposes read-only node and RF telemetry using existing in-memory structures.
Does not modify UI or Meshtastic interfaces.
"""

import json
import http.server
import socketserver
import urllib.parse
from typing import Dict, Any, Optional
import time

# Import system module functions and globals
# These will be imported at runtime to avoid circular imports
_system_module = None
_globals_dict = None


def get_system_globals():
    """Lazy import of system module globals to avoid circular imports."""
    global _system_module, _globals_dict
    if _system_module is None:
        import sys
        # Try to get system module from already loaded modules
        if 'modules.system' in sys.modules:
            _system_module = sys.modules['modules.system']
        else:
            # Fallback: try to import
            try:
                from modules import system as _system_module
            except ImportError:
                pass
        
        # Get globals from main module (where interfaces are defined)
        # Try multiple approaches to find the right namespace
        _globals_dict = None
        if '__main__' in sys.modules:
            _globals_dict = sys.modules['__main__'].__dict__
        else:
            try:
                import __main__
                _globals_dict = __main__.__dict__
            except:
                pass
        
        # If still None, try to get from calling frame
        if _globals_dict is None:
            try:
                import inspect
                frame = inspect.currentframe()
                while frame:
                    if 'interface1' in frame.f_globals:
                        _globals_dict = frame.f_globals
                        break
                    frame = frame.f_back
            except:
                pass
    return _system_module, _globals_dict


def decimal_to_hex(decimal_number: int) -> str:
    """Convert decimal node ID to hex format."""
    return f"!{decimal_number:08x}"


def get_node_data(interface_num: Optional[int] = None) -> Dict[str, Any]:
    """
    Get node data from interface.nodes.
    Returns data for all interfaces if interface_num is None, otherwise for specific interface.
    """
    system_module, globals_dict = get_system_globals()
    if not system_module or not globals_dict:
        return {"error": "System module not available"}
    
    result = {}
    
    # Determine which interfaces to query
    if interface_num is not None:
        interfaces_to_query = [interface_num]
    else:
        # Query all enabled interfaces (1-9)
        interfaces_to_query = []
        for i in range(1, 10):
            if globals_dict.get(f'interface{i}') and globals_dict.get(f'interface{i}_enabled', True):
                interfaces_to_query.append(i)
    
    for i in interfaces_to_query:
        # Try to get interface from globals dict
        interface = None
        if globals_dict:
            interface = globals_dict.get(f'interface{i}')
        
        # If not found, try to get from system module's globals
        if not interface and system_module:
            try:
                interface = getattr(system_module, f'interface{i}', None)
            except:
                pass
        
        if not interface:
            continue
        
        interface_key = f"interface_{i}"
        nodes_data = []
        
        if hasattr(interface, 'nodes') and interface.nodes:
            # Get my node number from globals or system module
            my_node_num = 0
            if globals_dict:
                my_node_num = globals_dict.get(f'myNodeNum{i}', 0)
            if my_node_num == 0 and system_module:
                try:
                    my_node_num = getattr(system_module, f'myNodeNum{i}', 0)
                except:
                    pass
            
            for node_hex, node_data in interface.nodes.items():
                node_id = node_data.get('num', 0)
                
                # Get node name
                node_name_short = ""
                node_name_long = ""
                if 'user' in node_data:
                    node_name_short = node_data['user'].get('shortName', '')
                    node_name_long = node_data['user'].get('longName', '')
                
                # Build node entry
                node_entry = {
                    "nodeId": node_id,
                    "nodeIdHex": node_hex,
                    "shortName": node_name_short,
                    "longName": node_name_long,
                    "snr": node_data.get('snr', 0),
                    "rssi": node_data.get('rssi', 0),
                    "lastHeard": node_data.get('lastHeard', 0),
                    "isLocal": node_id == my_node_num
                }
                
                # Add position data if available
                if 'position' in node_data and node_data['position']:
                    pos = node_data['position']
                    node_entry["position"] = {
                        "latitude": pos.get('latitude'),
                        "longitude": pos.get('longitude'),
                        "altitude": pos.get('altitude', 0),
                        "time": pos.get('time', 0)
                    }
                
                # Add device metrics if available
                if 'deviceMetrics' in node_data and node_data['deviceMetrics']:
                    metrics = node_data['deviceMetrics']
                    node_entry["deviceMetrics"] = {
                        "channelUtilization": metrics.get('channelUtilization', 0),
                        "airUtilTx": metrics.get('airUtilTx', 0),
                        "uptimeSeconds": metrics.get('uptimeSeconds', 0),
                        "batteryLevel": metrics.get('batteryLevel', 0),
                        "voltage": metrics.get('voltage', 0)
                    }
                
                nodes_data.append(node_entry)
        
        result[interface_key] = {
            "interfaceNumber": i,
            "nodeCount": len(nodes_data),
            "nodes": nodes_data
        }
    
    return result


def get_rf_telemetry(interface_num: Optional[int] = None) -> Dict[str, Any]:
    """
    Get RF telemetry data from localTelemetryData.
    Returns data for all interfaces if interface_num is None, otherwise for specific interface.
    """
    system_module, globals_dict = get_system_globals()
    if not system_module or not globals_dict:
        return {"error": "System module not available"}
    
    # Access localTelemetryData from system module
    local_telemetry_data = getattr(system_module, 'localTelemetryData', {})
    
    result = {}
    
    # Determine which interfaces to query
    if interface_num is not None:
        interfaces_to_query = [interface_num]
    else:
        # Query all interfaces (1-9)
        interfaces_to_query = list(range(1, 10))
    
    for i in interfaces_to_query:
        if i in local_telemetry_data:
            interface_key = f"interface_{i}"
            telemetry = local_telemetry_data[i]
            
            result[interface_key] = {
                "interfaceNumber": i,
                "numPacketsTx": telemetry.get('numPacketsTx', 0),
                "numPacketsRx": telemetry.get('numPacketsRx', 0),
                "numPacketsTxErr": telemetry.get('numPacketsTxErr', 0),
                "numPacketsRxErr": telemetry.get('numPacketsRxErr', 0),
                "numOnlineNodes": telemetry.get('numOnlineNodes', 0),
                "numTotalNodes": telemetry.get('numTotalNodes', 0),
                "numRXDupes": telemetry.get('numRXDupes', 0),
                "numTxRelays": telemetry.get('numTxRelays', 0),
                "heapFreeBytes": telemetry.get('heapFreeBytes', 0),
                "heapTotalBytes": telemetry.get('heapTotalBytes', 0)
            }
    
    # Add timing data from interface 0
    if 0 in local_telemetry_data:
        result["timing"] = {}
        timing_data = local_telemetry_data[0]
        for key, value in timing_data.items():
            if key.startswith('interface'):
                result["timing"][key] = value
    
    return result


def get_position_metadata() -> Dict[str, Any]:
    """Get position metadata for all nodes."""
    system_module, globals_dict = get_system_globals()
    if not system_module or not globals_dict:
        return {"error": "System module not available"}
    
    position_metadata = getattr(system_module, 'positionMetadata', {})
    
    # Convert to serializable format
    result = {
        "nodeCount": len(position_metadata),
        "nodes": {}
    }
    
    for node_id, metadata in position_metadata.items():
        result["nodes"][str(node_id)] = dict(metadata) if isinstance(metadata, dict) else metadata
    
    return result


def get_leaderboard() -> Dict[str, Any]:
    """Get mesh leaderboard data."""
    system_module, globals_dict = get_system_globals()
    if not system_module or not globals_dict:
        return {"error": "System module not available"}
    
    mesh_leaderboard = getattr(system_module, 'meshLeaderboard', {})
    
    # Convert to serializable format, handling special structures
    result = {}
    
    for key, value in mesh_leaderboard.items():
        if isinstance(value, dict) and 'nodeID' in value:
            # Leaderboard entry
            result[key] = {
                "nodeId": value.get('nodeID'),
                "value": value.get('value'),
                "timestamp": value.get('timestamp', 0)
            }
        elif isinstance(value, (list, dict)):
            # Lists and dicts (like emojiCounts, nodeMessageCounts)
            result[key] = value
        else:
            result[key] = value
    
    return result


class MCPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP request handler for MCP server endpoints and web UI."""
    
    def do_GET(self):
        """Handle GET requests."""
        parsed_path = urllib.parse.urlparse(self.path)
        path_parts = parsed_path.path.strip('/').split('/')
        
        # Set CORS headers for API access
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        
            # Route requests
        try:
            if path_parts[0] == '' or path_parts[0] == 'api':
                # API endpoints
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                
                if len(path_parts) > 1:
                    if path_parts[1] == 'nodes':
                        if len(path_parts) > 2 and path_parts[2].isdigit():
                            interface_num = int(path_parts[2])
                            if 1 <= interface_num <= 9:
                                response = get_node_data(interface_num)
                            else:
                                response = {"error": "Interface number must be between 1 and 9"}
                        else:
                            response = get_node_data()
                    elif path_parts[1] == 'telemetry':
                        if len(path_parts) > 2 and path_parts[2].isdigit():
                            interface_num = int(path_parts[2])
                            if 1 <= interface_num <= 9:
                                response = get_rf_telemetry(interface_num)
                            else:
                                response = {"error": "Interface number must be between 1 and 9"}
                        else:
                            response = get_rf_telemetry()
                    elif path_parts[1] == 'position':
                        response = get_position_metadata()
                    elif path_parts[1] == 'leaderboard':
                        response = get_leaderboard()
                    else:
                        response = {
                            "name": "Meshtastic MCP Server",
                            "version": "1.0.0",
                            "description": "Read-only node and RF telemetry API",
                            "endpoints": {
                                "/api/nodes": "Get all nodes from all interfaces",
                                "/api/nodes/<interface>": "Get nodes from specific interface (1-9)",
                                "/api/telemetry": "Get RF telemetry from all interfaces",
                                "/api/telemetry/<interface>": "Get RF telemetry from specific interface (1-9)",
                                "/api/position": "Get position metadata for all nodes",
                                "/api/leaderboard": "Get mesh leaderboard data"
                            }
                        }
                else:
                    response = {
                        "name": "Meshtastic MCP Server",
                        "version": "1.0.0",
                        "description": "Read-only node and RF telemetry API",
                        "endpoints": {
                            "/api/nodes": "Get all nodes from all interfaces",
                            "/api/nodes/<interface>": "Get nodes from specific interface (1-9)",
                            "/api/telemetry": "Get RF telemetry from all interfaces",
                            "/api/telemetry/<interface>": "Get RF telemetry from specific interface (1-9)",
                            "/api/position": "Get position metadata for all nodes",
                            "/api/leaderboard": "Get mesh leaderboard data"
                        }
                    }
                
                json_response = json.dumps(response, indent=2, default=str)
                self.wfile.write(json_response.encode('utf-8'))
                return
            elif path_parts[0] == 'nodes':
                # Legacy /nodes endpoint
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                if len(path_parts) > 1 and path_parts[1].isdigit():
                    interface_num = int(path_parts[1])
                    if 1 <= interface_num <= 9:
                        response = get_node_data(interface_num)
                    else:
                        response = {"error": "Interface number must be between 1 and 9"}
                else:
                    response = get_node_data()
                json_response = json.dumps(response, indent=2, default=str)
                self.wfile.write(json_response.encode('utf-8'))
                return
            elif path_parts[0] == 'telemetry':
                # Legacy /telemetry endpoint
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                if len(path_parts) > 1 and path_parts[1].isdigit():
                    interface_num = int(path_parts[1])
                    if 1 <= interface_num <= 9:
                        response = get_rf_telemetry(interface_num)
                    else:
                        response = {"error": "Interface number must be between 1 and 9"}
                else:
                    response = get_rf_telemetry()
                json_response = json.dumps(response, indent=2, default=str)
                self.wfile.write(json_response.encode('utf-8'))
                return
            elif path_parts[0] == 'position':
                # Legacy /position endpoint
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = get_position_metadata()
                json_response = json.dumps(response, indent=2, default=str)
                self.wfile.write(json_response.encode('utf-8'))
                return
            elif path_parts[0] == 'leaderboard':
                # Legacy /leaderboard endpoint
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = get_leaderboard()
                json_response = json.dumps(response, indent=2, default=str)
                self.wfile.write(json_response.encode('utf-8'))
                return
            else:
                # Unknown endpoint
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = {"error": "Unknown endpoint", "path": self.path}
                json_response = json.dumps(response, indent=2, default=str)
                self.wfile.write(json_response.encode('utf-8'))
                return
        except Exception as e:
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = {"error": str(e), "type": type(e).__name__}
            json_response = json.dumps(response, indent=2, default=str)
            self.wfile.write(json_response.encode('utf-8'))
    
    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress default logging unless enabled."""
        # Can be enabled via environment variable or config
        import os
        if os.environ.get('MCP_SERVER_LOGS', 'false').lower() == 'true':
            super().log_message(format, *args)


# Web UI has been moved to modules/web_ui.py - this file is now API-only
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Meshtastic MCP Server - Monitoring Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        header {
            background: rgba(255, 255, 255, 0.95);
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        
        h1 {
            color: #667eea;
            margin-bottom: 10px;
        }
        
        .status {
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 14px;
            margin-left: 10px;
        }
        
        .status.online {
            background: #10b981;
            color: white;
        }
        
        .status.offline {
            background: #ef4444;
            color: white;
        }
        
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        
        .tab {
            background: rgba(255, 255, 255, 0.9);
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
            font-weight: 500;
            transition: all 0.3s;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }
        
        .tab:hover {
            background: rgba(255, 255, 255, 1);
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
        }
        
        .tab.active {
            background: #667eea;
            color: white;
        }
        
        .content {
            background: rgba(255, 255, 255, 0.95);
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            min-height: 400px;
        }
        
        .tab-content {
            display: none;
        }
        
        .tab-content.active {
            display: block;
        }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        
        .card {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }
        
        .card h3 {
            color: #667eea;
            margin-bottom: 15px;
            font-size: 18px;
        }
        
        .stat {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #e5e7eb;
        }
        
        .stat:last-child {
            border-bottom: none;
        }
        
        .stat-label {
            color: #6b7280;
            font-weight: 500;
        }
        
        .stat-value {
            color: #111827;
            font-weight: 600;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e5e7eb;
        }
        
        th {
            background: #667eea;
            color: white;
            font-weight: 600;
        }
        
        tr:hover {
            background: #f8f9fa;
        }
        
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }
        
        .badge.success {
            background: #10b981;
            color: white;
        }
        
        .badge.warning {
            background: #f59e0b;
            color: white;
        }
        
        .badge.danger {
            background: #ef4444;
            color: white;
        }
        
        .badge.info {
            background: #3b82f6;
            color: white;
        }
        
        .refresh-btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            margin-bottom: 20px;
            transition: all 0.3s;
        }
        
        .refresh-btn:hover {
            background: #5568d3;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
        }
        
        .loading {
            text-align: center;
            padding: 40px;
            color: #6b7280;
        }
        
        .error {
            background: #fee2e2;
            color: #991b1b;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
        }
        
        .auto-refresh {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 20px;
        }
        
        .auto-refresh input[type="checkbox"] {
            width: 20px;
            height: 20px;
            cursor: pointer;
        }
        
        .timestamp {
            color: #6b7280;
            font-size: 14px;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📡 Meshtastic MCP Server <span class="status online" id="status">Online</span></h1>
            <p>Real-time monitoring and configuration dashboard for meshing-around</p>
        </header>
        
        <div class="tabs">
            <button class="tab active" onclick="showTab('dashboard')">Dashboard</button>
            <button class="tab" onclick="showTab('nodes')">Nodes</button>
            <button class="tab" onclick="showTab('telemetry')">RF Telemetry</button>
            <button class="tab" onclick="showTab('leaderboard')">Leaderboard</button>
            <button class="tab" onclick="showTab('position')">Position Data</button>
        </div>
        
        <div class="content">
            <div class="auto-refresh">
                <input type="checkbox" id="autoRefresh" checked onchange="toggleAutoRefresh()">
                <label for="autoRefresh">Auto-refresh (5s)</label>
                <button class="refresh-btn" onclick="refreshData()">🔄 Refresh Now</button>
            </div>
            
            <div id="dashboard" class="tab-content active">
                <h2>Dashboard Overview</h2>
                <div id="dashboard-content" class="loading">Loading dashboard data...</div>
            </div>
            
            <div id="nodes" class="tab-content">
                <h2>Node List</h2>
                <div id="nodes-content" class="loading">Loading nodes...</div>
            </div>
            
            <div id="telemetry" class="tab-content">
                <h2>RF Telemetry</h2>
                <div id="telemetry-content" class="loading">Loading telemetry...</div>
            </div>
            
            <div id="leaderboard" class="tab-content">
                <h2>Mesh Leaderboard</h2>
                <div id="leaderboard-content" class="loading">Loading leaderboard...</div>
            </div>
            
            <div id="position" class="tab-content">
                <h2>Position Metadata</h2>
                <div id="position-content" class="loading">Loading position data...</div>
            </div>
            
            <div class="timestamp" id="lastUpdate"></div>
        </div>
    </div>
    
    <script>
        let autoRefreshInterval = null;
        const API_BASE = window.location.origin;
        
        function showTab(tabName) {
            // Hide all tab contents
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });
            
            // Remove active class from all tabs
            document.querySelectorAll('.tab').forEach(tab => {
                tab.classList.remove('active');
            });
            
            // Show selected tab content
            document.getElementById(tabName).classList.add('active');
            
            // Add active class to clicked tab
            event.target.classList.add('active');
            
            // Refresh data for the active tab
            refreshData();
        }
        
        function toggleAutoRefresh() {
            const checkbox = document.getElementById('autoRefresh');
            if (checkbox.checked) {
                startAutoRefresh();
            } else {
                stopAutoRefresh();
            }
        }
        
        function startAutoRefresh() {
            stopAutoRefresh();
            autoRefreshInterval = setInterval(refreshData, 5000);
        }
        
        function stopAutoRefresh() {
            if (autoRefreshInterval) {
                clearInterval(autoRefreshInterval);
                autoRefreshInterval = null;
            }
        }
        
        async function fetchAPI(endpoint) {
            try {
                const response = await fetch(`${API_BASE}/api/${endpoint}`);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return await response.json();
            } catch (error) {
                console.error(`Error fetching ${endpoint}:`, error);
                return { error: error.message };
            }
        }
        
        function formatTimestamp(timestamp) {
            if (!timestamp || timestamp === 0) return 'Never';
            const date = new Date(timestamp * 1000);
            return date.toLocaleString();
        }
        
        function formatUptime(seconds) {
            if (!seconds) return '0s';
            const days = Math.floor(seconds / 86400);
            const hours = Math.floor((seconds % 86400) / 3600);
            const mins = Math.floor((seconds % 3600) / 60);
            const secs = seconds % 60;
            if (days > 0) return `${days}d ${hours}h ${mins}m`;
            if (hours > 0) return `${hours}h ${mins}m ${secs}s`;
            if (mins > 0) return `${mins}m ${secs}s`;
            return `${secs}s`;
        }
        
        function getBatteryBadge(level) {
            if (level === 101) return '<span class="badge info">AC</span>';
            if (level < 10) return `<span class="badge danger">${level}%</span>`;
            if (level < 25) return `<span class="badge warning">${level}%</span>`;
            return `<span class="badge success">${level}%</span>`;
        }
        
        async function refreshData() {
            const activeTab = document.querySelector('.tab-content.active').id;
            
            try {
                updateStatus('online');
                
                switch(activeTab) {
                    case 'dashboard':
                        await loadDashboard();
                        break;
                    case 'nodes':
                        await loadNodes();
                        break;
                    case 'telemetry':
                        await loadTelemetry();
                        break;
                    case 'leaderboard':
                        await loadLeaderboard();
                        break;
                    case 'position':
                        await loadPosition();
                        break;
                }
                
                document.getElementById('lastUpdate').textContent = `Last updated: ${new Date().toLocaleString()}`;
            } catch (error) {
                console.error('Error refreshing data:', error);
                updateStatus('offline');
            }
        }
        
        function updateStatus(status) {
            const statusEl = document.getElementById('status');
            statusEl.className = `status ${status}`;
            statusEl.textContent = status === 'online' ? 'Online' : 'Offline';
        }
        
        async function loadDashboard() {
            const content = document.getElementById('dashboard-content');
            const [nodesData, telemetryData, leaderboardData] = await Promise.all([
                fetchAPI('nodes'),
                fetchAPI('telemetry'),
                fetchAPI('leaderboard')
            ]);
            
            if (nodesData.error || telemetryData.error) {
                content.innerHTML = `<div class="error">Error loading data: ${nodesData.error || telemetryData.error}</div>`;
                return;
            }
            
            let html = '<div class="grid">';
            
            // Total nodes
            let totalNodes = 0;
            let totalOnline = 0;
            for (const key in nodesData) {
                if (nodesData[key].nodeCount !== undefined) {
                    totalNodes += nodesData[key].nodeCount;
                    totalOnline += nodesData[key].nodes.filter(n => n.lastHeard > Date.now() / 1000 - 3600).length;
                }
            }
            
            html += `
                <div class="card">
                    <h3>📊 Network Overview</h3>
                    <div class="stat">
                        <span class="stat-label">Total Nodes</span>
                        <span class="stat-value">${totalNodes}</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">Online (1h)</span>
                        <span class="stat-value">${totalOnline}</span>
                    </div>
                </div>
            `;
            
            // RF Statistics
            let totalTx = 0, totalRx = 0, totalTxErr = 0, totalRxErr = 0;
            for (const key in telemetryData) {
                if (key.startsWith('interface_')) {
                    totalTx += telemetryData[key].numPacketsTx || 0;
                    totalRx += telemetryData[key].numPacketsRx || 0;
                    totalTxErr += telemetryData[key].numPacketsTxErr || 0;
                    totalRxErr += telemetryData[key].numPacketsRxErr || 0;
                }
            }
            
            html += `
                <div class="card">
                    <h3>📡 RF Statistics</h3>
                    <div class="stat">
                        <span class="stat-label">Packets TX</span>
                        <span class="stat-value">${totalTx.toLocaleString()}</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">Packets RX</span>
                        <span class="stat-value">${totalRx.toLocaleString()}</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">TX Errors</span>
                        <span class="stat-value">${totalTxErr.toLocaleString()}</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">RX Errors</span>
                        <span class="stat-value">${totalRxErr.toLocaleString()}</span>
                    </div>
                </div>
            `;
            
            // Leaderboard highlights
            if (leaderboardData && !leaderboardData.error) {
                html += `
                    <div class="card">
                        <h3>🏆 Leaderboard Highlights</h3>
                        ${leaderboardData.lowestBattery ? `<div class="stat"><span class="stat-label">Lowest Battery</span><span class="stat-value">${leaderboardData.lowestBattery.value}%</span></div>` : ''}
                        ${leaderboardData.longestUptime ? `<div class="stat"><span class="stat-label">Longest Uptime</span><span class="stat-value">${formatUptime(leaderboardData.longestUptime.value)}</span></div>` : ''}
                        ${leaderboardData.highestDBm ? `<div class="stat"><span class="stat-label">Best RF</span><span class="stat-value">${leaderboardData.highestDBm.value} dBm</span></div>` : ''}
                    </div>
                `;
            }
            
            html += '</div>';
            
            // Recent nodes table
            html += '<h3 style="margin-top: 30px;">Recent Nodes</h3><table><thead><tr><th>Node ID</th><th>Name</th><th>SNR</th><th>RSSI</th><th>Battery</th><th>Last Heard</th></tr></thead><tbody>';
            
            const allNodes = [];
            for (const key in nodesData) {
                if (nodesData[key].nodes) {
                    allNodes.push(...nodesData[key].nodes);
                }
            }
            
            allNodes.sort((a, b) => (b.lastHeard || 0) - (a.lastHeard || 0));
            allNodes.slice(0, 10).forEach(node => {
                const battery = node.deviceMetrics?.batteryLevel || 'N/A';
                html += `
                    <tr>
                        <td>${node.nodeIdHex || node.nodeId}</td>
                        <td>${node.shortName || node.longName || 'Unknown'}</td>
                        <td>${node.snr || 'N/A'}</td>
                        <td>${node.rssi || 'N/A'}</td>
                        <td>${typeof battery === 'number' ? getBatteryBadge(battery) : battery}</td>
                        <td>${formatTimestamp(node.lastHeard)}</td>
                    </tr>
                `;
            });
            
            html += '</tbody></table>';
            content.innerHTML = html;
        }
        
        async function loadNodes() {
            const content = document.getElementById('nodes-content');
            const data = await fetchAPI('nodes');
            
            if (data.error) {
                content.innerHTML = `<div class="error">Error: ${data.error}</div>`;
                return;
            }
            
            let html = '';
            for (const key in data) {
                if (data[key].interfaceNumber) {
                    html += `<h3>Interface ${data[key].interfaceNumber} (${data[key].nodeCount} nodes)</h3>`;
                    html += '<table><thead><tr><th>Node ID</th><th>Name</th><th>SNR</th><th>RSSI</th><th>Battery</th><th>Uptime</th><th>Last Heard</th></tr></thead><tbody>';
                    
                    data[key].nodes.forEach(node => {
                        const battery = node.deviceMetrics?.batteryLevel || 'N/A';
                        const uptime = node.deviceMetrics?.uptimeSeconds || 0;
                        html += `
                            <tr>
                                <td>${node.nodeIdHex || node.nodeId}</td>
                                <td>${node.shortName || node.longName || 'Unknown'} ${node.isLocal ? '<span class="badge info">Local</span>' : ''}</td>
                                <td>${node.snr || 'N/A'}</td>
                                <td>${node.rssi || 'N/A'}</td>
                                <td>${typeof battery === 'number' ? getBatteryBadge(battery) : battery}</td>
                                <td>${formatUptime(uptime)}</td>
                                <td>${formatTimestamp(node.lastHeard)}</td>
                            </tr>
                        `;
                    });
                    
                    html += '</tbody></table><br>';
                }
            }
            
            content.innerHTML = html || '<p>No nodes found</p>';
        }
        
        async function loadTelemetry() {
            const content = document.getElementById('telemetry-content');
            const data = await fetchAPI('telemetry');
            
            if (data.error) {
                content.innerHTML = `<div class="error">Error: ${data.error}</div>`;
                return;
            }
            
            let html = '<div class="grid">';
            for (const key in data) {
                if (key.startsWith('interface_')) {
                    const tel = data[key];
                    html += `
                        <div class="card">
                            <h3>Interface ${tel.interfaceNumber}</h3>
                            <div class="stat">
                                <span class="stat-label">Packets TX</span>
                                <span class="stat-value">${tel.numPacketsTx.toLocaleString()}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Packets RX</span>
                                <span class="stat-value">${tel.numPacketsRx.toLocaleString()}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">TX Errors</span>
                                <span class="stat-value">${tel.numPacketsTxErr.toLocaleString()}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">RX Errors</span>
                                <span class="stat-value">${tel.numPacketsRxErr.toLocaleString()}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Online Nodes</span>
                                <span class="stat-value">${tel.numOnlineNodes}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Total Nodes</span>
                                <span class="stat-value">${tel.numTotalNodes}</span>
                            </div>
                        </div>
                    `;
                }
            }
            html += '</div>';
            content.innerHTML = html || '<p>No telemetry data available</p>';
        }
        
        async function loadLeaderboard() {
            const content = document.getElementById('leaderboard-content');
            const data = await fetchAPI('leaderboard');
            
            if (data.error) {
                content.innerHTML = `<div class="error">Error: ${data.error}</div>`;
                return;
            }
            
            let html = '<div class="grid">';
            const leaderboardItems = [
                { key: 'lowestBattery', label: 'Lowest Battery', format: (v) => `${v}%` },
                { key: 'longestUptime', label: 'Longest Uptime', format: (v) => formatUptime(v) },
                { key: 'highestDBm', label: 'Best RF Signal', format: (v) => `${v} dBm` },
                { key: 'weakestDBm', label: 'Weakest RF Signal', format: (v) => `${v} dBm` },
                { key: 'mostMessages', label: 'Most Messages', format: (v) => v },
                { key: 'mostTMessages', label: 'Most Telemetry', format: (v) => v }
            ];
            
            leaderboardItems.forEach(item => {
                if (data[item.key] && data[item.key].value !== undefined) {
                    html += `
                        <div class="card">
                            <h3>${item.label}</h3>
                            <div class="stat">
                                <span class="stat-label">Node ID</span>
                                <span class="stat-value">${data[item.key].nodeId || 'N/A'}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Value</span>
                                <span class="stat-value">${item.format(data[item.key].value)}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Timestamp</span>
                                <span class="stat-value">${formatTimestamp(data[item.key].timestamp)}</span>
                            </div>
                        </div>
                    `;
                }
            });
            
            html += '</div>';
            content.innerHTML = html || '<p>No leaderboard data available</p>';
        }
        
        async function loadPosition() {
            const content = document.getElementById('position-content');
            const data = await fetchAPI('position');
            
            if (data.error) {
                content.innerHTML = `<div class="error">Error: ${data.error}</div>`;
                return;
            }
            
            if (!data.nodes || Object.keys(data.nodes).length === 0) {
                content.innerHTML = '<p>No position data available</p>';
                return;
            }
            
            let html = `<p>Total nodes with position data: ${data.nodeCount}</p>`;
            html += '<table><thead><tr><th>Node ID</th><th>Latitude</th><th>Longitude</th><th>Altitude</th><th>Time</th></tr></thead><tbody>';
            
            for (const nodeId in data.nodes) {
                const node = data.nodes[nodeId];
                html += `
                    <tr>
                        <td>${nodeId}</td>
                        <td>${node.latitude || 'N/A'}</td>
                        <td>${node.longitude || 'N/A'}</td>
                        <td>${node.altitude || 0}m</td>
                        <td>${formatTimestamp(node.time)}</td>
                    </tr>
                `;
            }
            
            html += '</tbody></table>';
            content.innerHTML = html;
        }
        
        // Initialize
        document.addEventListener('DOMContentLoaded', () => {
            refreshData();
            startAutoRefresh();
# Web UI code removed - see modules/web_ui.py


def start_mcp_server(host: str = '0.0.0.0', port: int = 8421, background: bool = False):
    """
    Start the MCP server.
    
    Args:
        host: Host address to bind to (default: 127.0.0.1)
        port: Port to listen on (default: 8421)
        background: If True, run in background thread (default: False)
    
    Returns:
        Server instance or thread depending on background parameter
    """
    server = socketserver.TCPServer((host, port), MCPRequestHandler)
    server.allow_reuse_address = True
    
    if background:
        import threading
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        print(f"MCP Server started in background at http://{host}:{port}")
        return server_thread
    else:
        print(f"MCP Server started at http://{host}:{port}")
        print("Press Ctrl+C to stop the server")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down MCP Server...")
            server.shutdown()
        return server


if __name__ == "__main__":
    # Run as standalone server
    import sys
    
    host = '0.0.0.0'  # Listen on all interfaces by default
    port = 8421
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    
    print(f"Starting MCP Server on {host}:{port}")
    print(f"API endpoints available at: http://{host if host != '0.0.0.0' else 'localhost'}:{port}/api")
    print(f"Note: Web UI is available via modules/web_ui.py")
    
    start_mcp_server(host, port, background=False)

