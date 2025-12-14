#!/usr/bin/env python3
"""
Web UI Module for Meshing-Around
Provides a web-based dashboard and configuration interface.
Runs automatically when the main bot starts.
"""

import json
import http.server
import socketserver
import urllib.parse
import configparser
import os
import shutil
from typing import Dict, Any, Optional
from datetime import datetime
import threading

# Configuration file path
CONFIG_FILE = "config.ini"
CONFIG_BACKUP_DIR = "data/config_backups"

# Ensure backup directory exists
os.makedirs(CONFIG_BACKUP_DIR, exist_ok=True)


def backup_config():
    """Create a backup of the current config file."""
    if os.path.exists(CONFIG_FILE):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(CONFIG_BACKUP_DIR, f"config_{timestamp}.ini")
        shutil.copy2(CONFIG_FILE, backup_path)
        return backup_path
    return None


def read_config() -> Dict[str, Any]:
    """Read the config.ini file and return as dictionary."""
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE, encoding='utf-8')
    
    result = {}
    for section in config.sections():
        result[section] = dict(config.items(section))
    
    return result


def write_config(config_data: Dict[str, Any]) -> Dict[str, Any]:
    """Write configuration data to config.ini file."""
    try:
        # Backup existing config
        backup_path = backup_config()
        
        # Create new config
        config = configparser.ConfigParser()
        
        for section, items in config_data.items():
            config.add_section(section)
            for key, value in items.items():
                config.set(section, key, str(value))
        
        # Write to file
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            config.write(f)
        
        return {
            "success": True,
            "message": "Configuration saved successfully",
            "backup": backup_path
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# Import data access functions from mcp_server
# These access Meshtastic interfaces directly
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
    Get node data directly from interface.nodes.
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
    Get RF telemetry data directly from localTelemetryData.
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
            
            # Helper to safely get values, handling None
            def safe_get(key, default=0):
                value = telemetry.get(key, default)
                return value if value is not None else default
            
            result[interface_key] = {
                "interfaceNumber": i,
                "numPacketsTx": safe_get('numPacketsTx', 0),
                "numPacketsRx": safe_get('numPacketsRx', 0),
                "numPacketsTxErr": safe_get('numPacketsTxErr', 0),
                "numPacketsRxErr": safe_get('numPacketsRxErr', 0),
                "numOnlineNodes": safe_get('numOnlineNodes', 0),
                "numTotalNodes": safe_get('numTotalNodes', 0),
                "numRXDupes": safe_get('numRXDupes', 0),
                "numTxRelays": safe_get('numTxRelays', 0),
                "heapFreeBytes": safe_get('heapFreeBytes', 0),
                "heapTotalBytes": safe_get('heapTotalBytes', 0)
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
    """Get position metadata directly from positionMetadata."""
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
    """Get mesh leaderboard data directly from meshLeaderboard."""
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


def get_bbs_messages() -> Dict[str, Any]:
    """Get BBS messages from bbstools module."""
    try:
        from modules import bbstools
        
        # Access the global bbs_messages list
        bbs_messages = getattr(bbstools, 'bbs_messages', [])
        bbs_dm = getattr(bbstools, 'bbs_dm', [])
        
        # Format: [messageID, subject, message, fromNode, timestamp, threadID, replytoID]
        messages = []
        for msg in bbs_messages:
            if len(msg) >= 4:
                messages.append({
                    "id": msg[0] if len(msg) > 0 else 0,
                    "subject": msg[1] if len(msg) > 1 else "",
                    "message": msg[2] if len(msg) > 2 else "",
                    "fromNode": msg[3] if len(msg) > 3 else 0,
                    "timestamp": msg[4] if len(msg) > 4 else "",
                    "threadID": msg[5] if len(msg) > 5 else 0,
                    "replytoID": msg[6] if len(msg) > 6 else 0
                })
        
        # Format DMs: [toNode, message, fromNode] or similar
        dms = []
        for dm in bbs_dm:
            if len(dm) >= 3:
                dms.append({
                    "toNode": dm[0] if len(dm) > 0 else 0,
                    "message": dm[1] if len(dm) > 1 else "",
                    "fromNode": dm[2] if len(dm) > 2 else 0
                })
        
        return {
            "success": True,
            "messages": messages,
            "dms": dms,
            "messageCount": len(messages),
            "dmCount": len(dms)
        }
    except Exception as e:
        return {
            "error": f"Failed to get BBS messages: {str(e)}",
            "type": type(e).__name__
        }


class WebUIRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP request handler for Web UI."""
    
    def do_GET(self):
        """Handle GET requests."""
        parsed_path = urllib.parse.urlparse(self.path)
        path_parts = parsed_path.path.strip('/').split('/')
        
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        
        try:
            if path_parts[0] == '':
                # Root - serve web UI
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(get_web_ui_html().encode('utf-8'))
                return
            elif path_parts[0] == 'api':
                # API endpoints
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                
                if len(path_parts) > 1:
                    if path_parts[1] == 'config':
                        # Get configuration
                        config_data = read_config()
                        response = {"success": True, "config": config_data}
                    elif path_parts[1] == 'dashboard':
                        # Get dashboard data directly from Meshtastic interfaces
                        nodes = get_node_data()
                        telemetry = get_rf_telemetry()
                        leaderboard = get_leaderboard()
                        response = {
                            "success": True,
                            "nodes": nodes,
                            "telemetry": telemetry,
                            "leaderboard": leaderboard
                        }
                    elif path_parts[1] == 'nodes':
                        # Get nodes directly from interface.nodes
                        if len(path_parts) > 2 and path_parts[2].isdigit():
                            interface_num = int(path_parts[2])
                            if 1 <= interface_num <= 9:
                                response = get_node_data(interface_num)
                            else:
                                response = {"error": "Interface number must be between 1 and 9"}
                        else:
                            response = get_node_data()
                    elif path_parts[1] == 'telemetry':
                        # Get RF telemetry directly from localTelemetryData
                        if len(path_parts) > 2 and path_parts[2].isdigit():
                            interface_num = int(path_parts[2])
                            if 1 <= interface_num <= 9:
                                response = get_rf_telemetry(interface_num)
                            else:
                                response = {"error": "Interface number must be between 1 and 9"}
                        else:
                            response = get_rf_telemetry()
                    elif path_parts[1] == 'position':
                        # Get position metadata directly from positionMetadata
                        response = get_position_metadata()
                    elif path_parts[1] == 'leaderboard':
                        # Get leaderboard directly from meshLeaderboard
                        response = get_leaderboard()
                    elif path_parts[1] == 'bbs':
                        # Get BBS messages
                        response = get_bbs_messages()
                    elif path_parts[1] == 'map':
                        # Get nodes with positions for map
                        nodes = get_node_data()
                        response = {
                            "success": True,
                            "nodes": nodes
                        }
                    else:
                        response = {"error": "Unknown API endpoint"}
                else:
                    response = {"error": "API endpoint required"}
                
                json_response = json.dumps(response, indent=2, default=str)
                self.wfile.write(json_response.encode('utf-8'))
                return
            else:
                # Unknown path
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.send_error(404, "Not Found")
                return
        except Exception as e:
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = {"error": str(e), "type": type(e).__name__}
            json_response = json.dumps(response, indent=2, default=str)
            self.wfile.write(json_response.encode('utf-8'))
    
    def do_POST(self):
        """Handle POST requests."""
        parsed_path = urllib.parse.urlparse(self.path)
        path_parts = parsed_path.path.strip('/').split('/')
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
        try:
            if path_parts[0] == 'api' and len(path_parts) > 1:
                if path_parts[1] == 'config':
                    # Save configuration
                    content_length = int(self.headers['Content-Length'])
                    post_data = self.rfile.read(content_length)
                    config_data = json.loads(post_data.decode('utf-8'))
                    
                    response = write_config(config_data.get('config', {}))
                else:
                    response = {"error": "Unknown POST endpoint"}
            else:
                response = {"error": "Invalid POST request"}
            
            json_response = json.dumps(response, indent=2, default=str)
            self.wfile.write(json_response.encode('utf-8'))
        except Exception as e:
            response = {"error": str(e), "type": type(e).__name__}
            json_response = json.dumps(response, indent=2, default=str)
            self.wfile.write(json_response.encode('utf-8'))
    
    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress default logging unless enabled."""
        import os
        if os.environ.get('WEB_UI_LOGS', 'false').lower() == 'true':
            super().log_message(format, *args)


def get_web_ui_html() -> str:
    """Generate the web UI HTML with dashboard and configuration."""
    # This will be a large HTML file - I'll create it in parts
    # For now, return a basic structure that we'll expand
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Meshing-Around - Dashboard & Configuration</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1600px; margin: 0 auto; }
        header {
            background: rgba(255, 255, 255, 0.95);
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        h1 { color: #667eea; margin-bottom: 10px; }
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
        }
        .tab:hover { background: rgba(255, 255, 255, 1); transform: translateY(-2px); }
        .tab.active { background: #667eea; color: white; }
        .content {
            background: rgba(255, 255, 255, 0.95);
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            min-height: 400px;
        }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
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
        .card h3 { color: #667eea; margin-bottom: 15px; }
        .stat {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #e5e7eb;
        }
        .stat:last-child { border-bottom: none; }
        .config-section {
            margin-bottom: 30px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
        }
        .config-section h3 {
            color: #667eea;
            margin-bottom: 15px;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }
        .form-group {
            margin-bottom: 15px;
        }
        .form-group label {
            display: block;
            margin-bottom: 5px;
            font-weight: 500;
            color: #374151;
        }
        .form-group input,
        .form-group select,
        .form-group textarea {
            width: 100%;
            padding: 8px 12px;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            font-size: 14px;
        }
        .form-group input[type="checkbox"] {
            width: auto;
            margin-right: 8px;
        }
        .btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            margin-right: 10px;
            transition: all 0.3s;
        }
        .btn:hover { background: #5568d3; transform: translateY(-2px); }
        .btn-success { background: #10b981; }
        .btn-danger { background: #ef4444; }
        .loading { text-align: center; padding: 40px; color: #6b7280; }
        .error {
            background: #fee2e2;
            color: #991b1b;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
        }
        .success {
            background: #d1fae5;
            color: #065f46;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
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
        tr:hover { background: #f8f9fa; }
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }
        .badge.success { background: #10b981; color: white; }
        .badge.warning { background: #f59e0b; color: white; }
        .badge.danger { background: #ef4444; color: white; }
        .badge.info { background: #3b82f6; color: white; }
        /* Map Styles */
        #map-container {
            width: 100%;
            height: 600px;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            margin-bottom: 20px;
        }
        #node-map {
            width: 100%;
            height: 100%;
        }
        .map-controls {
            position: absolute;
            top: 10px;
            right: 10px;
            z-index: 1000;
            background: white;
            padding: 8px;
            border-radius: 6px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
        }
        /* BBS Styles */
        .bbs-message {
            background: #f8f9fa;
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 16px;
            border-left: 4px solid #667eea;
        }
        .bbs-message-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            font-weight: 600;
            color: #667eea;
        }
        .bbs-message-body {
            color: #374151;
            margin-top: 8px;
            white-space: pre-wrap;
        }
        .bbs-message-meta {
            font-size: 12px;
            color: #6b7280;
            margin-top: 8px;
        }
    </style>
    <!-- Leaflet CSS for OpenStreetMap -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
</head>
<body>
    <div class="container">
        <header>
            <h1>📡 Meshing-Around Dashboard & Configuration</h1>
            <p>Monitor your mesh network and configure all settings</p>
        </header>
        
        <div class="tabs">
            <button class="tab active" onclick="showTab('dashboard')">📊 Dashboard</button>
            <button class="tab" onclick="showTab('map')">🗺️ Node Map</button>
            <button class="tab" onclick="showTab('bbs')">💬 BBS</button>
            <button class="tab" onclick="showTab('nodes')">📡 Nodes</button>
            <button class="tab" onclick="showTab('telemetry')">📈 RF Telemetry</button>
            <button class="tab" onclick="showTab('leaderboard')">🏆 Leaderboard</button>
            <button class="tab" onclick="showTab('config')">⚙️ Configuration</button>
        </div>
        
        <div class="content">
            <div id="dashboard" class="tab-content active">
                <h2>Dashboard Overview</h2>
                <div id="dashboard-content" class="loading">Loading dashboard data...</div>
            </div>
            
            <div id="config" class="tab-content">
                <h2>Configuration</h2>
                <div id="config-content" class="loading">Loading configuration...</div>
                <div style="margin-top: 20px;">
                    <button class="btn btn-success" onclick="saveConfig()">💾 Save Configuration</button>
                    <button class="btn" onclick="loadConfig()">🔄 Reload Configuration</button>
                </div>
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
            
            <div id="map" class="tab-content">
                <h2>Node Location Map</h2>
                <div id="map-container" style="position: relative;">
                    <div id="node-map"></div>
                </div>
                <p style="color: #6b7280; margin-top: 10px;">
                    Shows nodes with position data from the mesh network. Nodes are updated as packets are received.
                </p>
            </div>
            
            <div id="bbs" class="tab-content">
                <h2>Bulletin Board System (BBS)</h2>
                <div id="bbs-content" class="loading">Loading BBS messages...</div>
            </div>
        </div>
    </div>
    
    <!-- Leaflet JS for OpenStreetMap -->
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    
    <script>
        const API_BASE = window.location.origin;
        let configData = {};
        let autoRefreshInterval = null;
        let map = null;
        let mapMarkers = [];
        
        function showTab(tabName) {
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById(tabName).classList.add('active');
            event.target.classList.add('active');
            
            if (tabName === 'config') {
                loadConfig();
            } else if (tabName === 'map') {
                initMap();
            } else if (tabName === 'bbs') {
                loadBBS();
            } else {
                refreshData();
            }
        }
        
        async function fetchAPI(endpoint, method='GET', data=null) {
            try {
                const options = {
                    method: method,
                    headers: {'Content-Type': 'application/json'}
                };
                if (data) options.body = JSON.stringify(data);
                const response = await fetch(`${API_BASE}/api/${endpoint}`, options);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return await response.json();
            } catch (error) {
                console.error(`Error fetching ${endpoint}:`, error);
                return { error: error.message };
            }
        }
        
        async function loadConfig() {
            const content = document.getElementById('config-content');
            const data = await fetchAPI('config');
            
            if (data.error) {
                content.innerHTML = `<div class="error">Error: ${data.error}</div>`;
                return;
            }
            
            configData = data.config || {};
            let html = '';
            
            // Generate form for each config section
            for (const [section, items] of Object.entries(configData)) {
                html += `<div class="config-section"><h3>${section}</h3>`;
                for (const [key, value] of Object.entries(items)) {
                    const id = `${section}_${key}`;
                    const isBool = value === 'True' || value === 'False' || value === 'true' || value === 'false';
                    
                    html += `<div class="form-group">`;
                    html += `<label for="${id}">${key}</label>`;
                    
                    if (isBool) {
                        const checked = value === 'True' || value === 'true' ? 'checked' : '';
                        html += `<input type="checkbox" id="${id}" ${checked} onchange="updateConfigValue('${section}', '${key}', this.checked)">`;
                        html += `<span>${value}</span>`;
                    } else if (key.toLowerCase().includes('password') || key.toLowerCase().includes('key') || key.toLowerCase().includes('token')) {
                        html += `<input type="password" id="${id}" value="${value}" onchange="updateConfigValue('${section}', '${key}', this.value)">`;
                    } else if (value.includes('\\n') || value.length > 100) {
                        html += `<textarea id="${id}" rows="3" onchange="updateConfigValue('${section}', '${key}', this.value)">${value}</textarea>`;
                    } else {
                        html += `<input type="text" id="${id}" value="${value}" onchange="updateConfigValue('${section}', '${key}', this.value)">`;
                    }
                    
                    html += `</div>`;
                }
                html += `</div>`;
            }
            
            content.innerHTML = html;
        }
        
        function updateConfigValue(section, key, value) {
            if (!configData[section]) configData[section] = {};
            configData[section][key] = value;
        }
        
        async function saveConfig() {
            const result = await fetchAPI('config', 'POST', { config: configData });
            const content = document.getElementById('config-content');
            
            if (result.success) {
                content.innerHTML = `<div class="success">${result.message}${result.backup ? ' (Backup: ' + result.backup + ')' : ''}</div>` + content.innerHTML;
                setTimeout(() => {
                    const msg = content.querySelector('.success');
                    if (msg) msg.remove();
                }, 5000);
            } else {
                content.innerHTML = `<div class="error">Error: ${result.error}</div>` + content.innerHTML;
            }
        }
        
        async function refreshData() {
            const activeTab = document.querySelector('.tab-content.active').id;
            
            try {
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
                }
            } catch (error) {
                console.error('Error refreshing data:', error);
            }
        }
        
        async function loadDashboard() {
            const content = document.getElementById('dashboard-content');
            const data = await fetchAPI('dashboard');
            
            if (data.error) {
                content.innerHTML = `<div class="error">Error: ${data.error}</div>`;
                return;
            }
            
            let html = '<div class="grid">';
            
            // Network overview
            let totalNodes = 0;
            if (data.nodes && !data.nodes.error) {
                for (const key in data.nodes) {
                    if (data.nodes[key].nodeCount !== undefined) {
                        totalNodes += data.nodes[key].nodeCount;
                    }
                }
            }
            
            html += `
                <div class="card">
                    <h3>📊 Network Overview</h3>
                    <div class="stat">
                        <span>Total Nodes</span>
                        <span><strong>${totalNodes}</strong></span>
                    </div>
                </div>
            `;
            
            // RF Statistics
            if (data.telemetry && !data.telemetry.error) {
                let totalTx = 0, totalRx = 0;
                for (const key in data.telemetry) {
                    if (key.startsWith('interface_')) {
                        totalTx += data.telemetry[key].numPacketsTx || 0;
                        totalRx += data.telemetry[key].numPacketsRx || 0;
                    }
                }
                html += `
                    <div class="card">
                        <h3>📡 RF Statistics</h3>
                        <div class="stat">
                            <span>Packets TX</span>
                            <span><strong>${totalTx.toLocaleString()}</strong></span>
                        </div>
                        <div class="stat">
                            <span>Packets RX</span>
                            <span><strong>${totalRx.toLocaleString()}</strong></span>
                        </div>
                    </div>
                `;
            }
            
            html += '</div>';
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
                    html += '<table><thead><tr><th>Node ID</th><th>Name</th><th>SNR</th><th>RSSI</th><th>Last Heard</th></tr></thead><tbody>';
                    
                    data[key].nodes.forEach(node => {
                        const lastHeard = node.lastHeard ? new Date(node.lastHeard * 1000).toLocaleString() : 'Never';
                        html += `
                            <tr>
                                <td>${node.nodeIdHex || node.nodeId}</td>
                                <td>${node.shortName || node.longName || 'Unknown'}</td>
                                <td>${node.snr || 'N/A'}</td>
                                <td>${node.rssi || 'N/A'}</td>
                                <td>${lastHeard}</td>
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
                    // Safely get values with defaults
                    const tx = (tel.numPacketsTx || 0);
                    const rx = (tel.numPacketsRx || 0);
                    const txErr = (tel.numPacketsTxErr || 0);
                    const rxErr = (tel.numPacketsRxErr || 0);
                    const online = (tel.numOnlineNodes || 0);
                    const total = (tel.numTotalNodes || 0);
                    
                    html += `
                        <div class="card">
                            <h3>Interface ${tel.interfaceNumber || 'Unknown'}</h3>
                            <div class="stat">
                                <span>Packets TX</span>
                                <span><strong>${tx.toLocaleString()}</strong></span>
                            </div>
                            <div class="stat">
                                <span>Packets RX</span>
                                <span><strong>${rx.toLocaleString()}</strong></span>
                            </div>
                            <div class="stat">
                                <span>TX Errors</span>
                                <span><strong>${txErr.toLocaleString()}</strong></span>
                            </div>
                            <div class="stat">
                                <span>RX Errors</span>
                                <span><strong>${rxErr.toLocaleString()}</strong></span>
                            </div>
                            <div class="stat">
                                <span>Online Nodes</span>
                                <span><strong>${online}</strong></span>
                            </div>
                            <div class="stat">
                                <span>Total Nodes</span>
                                <span><strong>${total}</strong></span>
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
            const items = [
                { key: 'lowestBattery', label: 'Lowest Battery' },
                { key: 'longestUptime', label: 'Longest Uptime' },
                { key: 'highestDBm', label: 'Best RF Signal' },
                { key: 'mostMessages', label: 'Most Messages' }
            ];
            
            items.forEach(item => {
                if (data[item.key] && data[item.key].value !== undefined) {
                    html += `
                        <div class="card">
                            <h3>${item.label}</h3>
                            <div class="stat">
                                <span>Node ID</span>
                                <span><strong>${data[item.key].nodeId || 'N/A'}</strong></span>
                            </div>
                            <div class="stat">
                                <span>Value</span>
                                <span><strong>${data[item.key].value}</strong></span>
                            </div>
                        </div>
                    `;
                }
            });
            
            html += '</div>';
            content.innerHTML = html || '<p>No leaderboard data available</p>';
        }
        
        // Map Functions
        function initMap() {
            // Wait a bit for the tab to be visible
            setTimeout(() => {
                if (map && typeof map.remove === 'function') {
                    map.remove();
                }
                
                // Check if map container exists
                const mapContainer = document.getElementById('node-map');
                if (!mapContainer) {
                    console.error('Map container not found');
                    return;
                }
                
                // Initialize map centered on a default location (will adjust to nodes)
                try {
                    map = L.map('node-map').setView([37.7749, -122.4194], 10);
                    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                        attribution: '© OpenStreetMap contributors',
                        maxZoom: 19
                    }).addTo(map);
                    
                    mapMarkers = [];
                    loadMapNodes();
                } catch (e) {
                    console.error('Error initializing map:', e);
                    document.getElementById('map-container').innerHTML = 
                        '<div style="padding: 40px; text-align: center; color: #6b7280;"><h3>Map Error</h3><p>Could not initialize map. Please refresh the page.</p></div>';
                }
            }, 100);
        }
        
        async function loadMapNodes() {
            if (!map) return;
            
            const data = await fetchAPI('map');
            if (data.error || !data.nodes) {
                console.error('Error loading nodes for map:', data.error);
                return;
            }
            
            // Clear existing markers
            mapMarkers.forEach(marker => map.removeLayer(marker));
            mapMarkers = [];
            
            let hasPositions = false;
            const bounds = [];
            
            for (const key in data.nodes) {
                if (data.nodes[key].nodes) {
                    data.nodes[key].nodes.forEach(node => {
                        if (node.position && node.position.latitude && node.position.longitude) {
                            hasPositions = true;
                            const lat = node.position.latitude;
                            const lng = node.position.longitude;
                            const name = node.shortName || node.longName || `Node ${node.nodeId}`;
                            
                            // Create marker with different color for local node
                            const markerColor = node.isLocal ? 'green' : 'blue';
                            const marker = L.marker([lat, lng], {
                                icon: L.divIcon({
                                    className: 'custom-marker',
                                    html: `<div style="background-color: ${markerColor}; width: 20px; height: 20px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div>`,
                                    iconSize: [20, 20]
                                })
                            })
                            .bindPopup(`
                                <strong>${name}</strong><br>
                                Node ID: ${node.nodeIdHex || node.nodeId}<br>
                                SNR: ${node.snr || 'N/A'}<br>
                                RSSI: ${node.rssi || 'N/A'}<br>
                                ${node.isLocal ? '<span style="color: green;">Local Node</span>' : ''}
                            `)
                            .addTo(map);
                            
                            mapMarkers.push(marker);
                            bounds.push([lat, lng]);
                        }
                    });
                }
            }
            
            if (hasPositions && bounds.length > 0) {
                try {
                    map.fitBounds(bounds, { padding: [20, 20] });
                } catch (e) {
                    console.error('Error fitting bounds:', e);
                }
            } else {
                // Show message if no positions - but don't overlay on map
                const mapContainer = document.getElementById('map-container');
                if (mapContainer) {
                    const existingMsg = mapContainer.querySelector('.no-positions');
                    if (!existingMsg) {
                        const msg = document.createElement('div');
                        msg.className = 'no-positions';
                        msg.style.cssText = 'padding: 40px; text-align: center; color: #6b7280; background: rgba(255,255,255,0.9); border-radius: 8px; margin: 20px;';
                        msg.innerHTML = '<h3>No Node Positions Available</h3><p>Nodes need to have position data to appear on the map.</p><p>Position data comes from packets received from nodes.</p>';
                        mapContainer.appendChild(msg);
                    }
                }
            }
        }
        
        // BBS Functions
        async function loadBBS() {
            const content = document.getElementById('bbs-content');
            const data = await fetchAPI('bbs');
            
            if (data.error) {
                content.innerHTML = `<div class="error">Error: ${data.error}</div>`;
                return;
            }
            
            let html = '';
            
            // Show stats
            html += `<div class="card" style="margin-bottom: 20px;">
                <h3>BBS Statistics</h3>
                <div class="stat">
                    <span>Public Messages</span>
                    <span><strong>${data.messageCount || 0}</strong></span>
                </div>
                <div class="stat">
                    <span>Pending DMs</span>
                    <span><strong>${data.dmCount || 0}</strong></span>
                </div>
            </div>`;
            
            // Show messages
            if (data.messages && data.messages.length > 0) {
                html += '<h3 style="margin-top: 24px; margin-bottom: 12px;">Public Messages</h3>';
                data.messages.forEach(msg => {
                    const fromNodeName = msg.fromNode ? `Node ${msg.fromNode}` : 'Unknown';
                    html += `
                        <div class="bbs-message">
                            <div class="bbs-message-header">
                                <span>#${msg.id} - ${msg.subject || 'No Subject'}</span>
                                <span>${fromNodeName}</span>
                            </div>
                            <div class="bbs-message-body">${msg.message || ''}</div>
                            <div class="bbs-message-meta">
                                ${msg.timestamp || 'No timestamp'} | 
                                ${msg.threadID ? `Thread: ${msg.threadID}` : ''}
                                ${msg.replytoID ? ` | Reply to: #${msg.replytoID}` : ''}
                            </div>
                        </div>
                    `;
                });
            } else {
                html += '<p>No BBS messages found.</p>';
            }
            
            // Show pending DMs
            if (data.dms && data.dms.length > 0) {
                html += '<h3 style="margin-top: 24px; margin-bottom: 12px;">Pending Direct Messages</h3>';
                data.dms.forEach(dm => {
                    html += `
                        <div class="bbs-message" style="border-left-color: #f59e0b;">
                            <div class="bbs-message-header">
                                <span>DM to Node ${dm.toNode}</span>
                                <span>From Node ${dm.fromNode}</span>
                            </div>
                            <div class="bbs-message-body">${dm.message || ''}</div>
                        </div>
                    `;
                });
            }
            
            content.innerHTML = html;
        }
        
        // Auto-refresh dashboard every 10 seconds
        function startAutoRefresh() {
            stopAutoRefresh();
            autoRefreshInterval = setInterval(() => {
                const activeTab = document.querySelector('.tab-content.active').id;
                if (activeTab === 'config') {
                    // Don't auto-refresh config
                } else if (activeTab === 'map') {
                    loadMapNodes();
                } else if (activeTab === 'bbs') {
                    loadBBS();
                } else {
                    refreshData();
                }
            }, 10000);
        }
        
        function stopAutoRefresh() {
            if (autoRefreshInterval) {
                clearInterval(autoRefreshInterval);
                autoRefreshInterval = null;
            }
        }
        
        // Initialize
        document.addEventListener('DOMContentLoaded', () => {
            refreshData();
            startAutoRefresh();
        });
    </script>
</body>
</html>"""


def start_web_ui(host: str = '0.0.0.0', port: int = 8420, background: bool = False):
    """
    Start the Web UI server.
    
    Args:
        host: Host address to bind to (default: 0.0.0.0)
        port: Port to listen on (default: 8420)
        background: If True, run in background thread (default: False)
    
    Returns:
        Server instance or thread depending on background parameter
    """
    server = socketserver.TCPServer((host, port), WebUIRequestHandler)
    server.allow_reuse_address = True
    
    if background:
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        print(f"Web UI started in background at http://{host}:{port}")
        return server_thread
    else:
        print(f"Web UI started at http://{host}:{port}")
        print("Press Ctrl+C to stop the server")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down Web UI...")
            server.shutdown()
        return server


if __name__ == "__main__":
    # Run as standalone server
    import sys
    
    host = '0.0.0.0'
    port = 8420
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    
    print(f"Starting Web UI on {host}:{port}")
    start_web_ui(host, port, background=False)

