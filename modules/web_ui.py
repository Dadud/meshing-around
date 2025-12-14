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
import time
import subprocess
import re
from typing import Dict, Any, Optional
from datetime import datetime
import threading
import queue

# Configuration file path
CONFIG_FILE = "config.ini"
CONFIG_BACKUP_DIR = "data/config_backups"

# Ensure backup directory exists
os.makedirs(CONFIG_BACKUP_DIR, exist_ok=True)

# SSE clients for real-time updates
sse_clients = []
sse_lock = threading.Lock()
update_interval = 5  # Default 5 seconds
auto_update_enabled = False  # Disabled by default - must be explicitly enabled


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


def get_message_history(limit: int = 100) -> Dict[str, Any]:
    """Get message history from settings module."""
    try:
        system_module, globals_dict = get_system_globals()
        if not system_module or not globals_dict:
            return {"error": "System module not available"}
        
        # Access msg_history from settings
        import modules.settings as settings_module
        msg_history = getattr(settings_module, 'msg_history', [])
        
        # Format: (name, message_string, channel_number, timestamp, rxNode)
        messages = []
        for msg in msg_history[-limit:]:  # Get most recent
            if len(msg) >= 5:
                messages.append({
                    "fromName": msg[0] if len(msg) > 0 else "Unknown",
                    "message": msg[1] if len(msg) > 1 else "",
                    "channel": msg[2] if len(msg) > 2 else 0,
                    "timestamp": msg[3] if len(msg) > 3 else "",
                    "interface": msg[4] if len(msg) > 4 else 1
                })
        
        return {
            "success": True,
            "messages": list(reversed(messages)),  # Most recent first
            "count": len(messages)
        }
    except Exception as e:
        return {
            "error": f"Failed to get message history: {str(e)}",
            "type": type(e).__name__
        }


def get_node_details(node_id: str, interface_num: Optional[int] = None) -> Dict[str, Any]:
    """Get detailed information about a specific node."""
    try:
        system_module, globals_dict = get_system_globals()
        if not system_module or not globals_dict:
            return {"error": "System module not available"}
        
        # Try to find node across all interfaces
        node_data = None
        found_interface = None
        
        interfaces_to_check = [interface_num] if interface_num else range(1, 10)
        
        for i in interfaces_to_check:
            interface = globals_dict.get(f'interface{i}')
            if not interface:
                continue
            
            if hasattr(interface, 'nodes') and interface.nodes:
                # Try both hex and decimal node ID
                node_hex = node_id if '!' in node_id else None
                node_dec = int(node_id) if node_id.isdigit() else None
                
                for hex_id, data in interface.nodes.items():
                    if (node_hex and hex_id == node_hex) or (node_dec and data.get('num') == node_dec):
                        node_data = data
                        found_interface = i
                        break
                
                if node_data:
                    break
        
        if not node_data:
            return {"error": f"Node {node_id} not found"}
        
        # Get my node number
        my_node_num = globals_dict.get(f'myNodeNum{found_interface}', 0)
        
        # Build detailed node info
        result = {
            "nodeId": node_data.get('num', 0),
            "nodeIdHex": node_id if '!' in node_id else hex(node_data.get('num', 0)),
            "interface": found_interface,
            "isLocal": node_data.get('num', 0) == my_node_num,
            "shortName": "",
            "longName": "",
            "snr": node_data.get('snr', 0),
            "rssi": node_data.get('rssi', 0),
            "lastHeard": node_data.get('lastHeard', 0),
            "position": None,
            "deviceMetrics": None,
            "user": node_data.get('user', {})
        }
        
        if 'user' in node_data:
            result["shortName"] = node_data['user'].get('shortName', '')
            result["longName"] = node_data['user'].get('longName', '')
        
        if 'position' in node_data and node_data['position']:
            result["position"] = {
                "latitude": node_data['position'].get('latitude'),
                "longitude": node_data['position'].get('longitude'),
                "altitude": node_data['position'].get('altitude', 0),
                "time": node_data['position'].get('time', 0)
            }
        
        if 'deviceMetrics' in node_data and node_data['deviceMetrics']:
            result["deviceMetrics"] = node_data['deviceMetrics']
        
        # Get message count from leaderboard
        mesh_leaderboard = getattr(system_module, 'meshLeaderboard', {})
        node_message_counts = mesh_leaderboard.get('nodeMessageCounts', {})
        result["messageCount"] = node_message_counts.get(str(result["nodeId"]), 0)
        
        return result
    except Exception as e:
        return {
            "error": f"Failed to get node details: {str(e)}",
            "type": type(e).__name__
        }


def get_system_health() -> Dict[str, Any]:
    """Get system health information."""
    try:
        system_module, globals_dict = get_system_globals()
        if not system_module or not globals_dict:
            return {"error": "System module not available"}
        
        import time
        
        # Get interface status
        interfaces = []
        for i in range(1, 10):
            interface = globals_dict.get(f'interface{i}')
            enabled = globals_dict.get(f'interface{i}_enabled', False)
            retry = globals_dict.get(f'retry_int{i}', False)
            
            if enabled:
                status = "connected" if interface and not retry else "disconnected" if retry else "unknown"
                interfaces.append({
                    "number": i,
                    "enabled": enabled,
                    "status": status,
                    "retrying": retry
                })
        
        # Get uptime (approximate - time since import)
        uptime_seconds = time.time() - (globals_dict.get('start_time', time.time()))
        
        result = {
            "success": True,
            "uptime": uptime_seconds,
            "uptimeFormatted": format_uptime(uptime_seconds),
            "interfaces": interfaces,
            "memory": {"used": 0, "percent": 0},
            "cpu": {"percent": 0}
        }
        
        # Try to get process info if psutil is available
        try:
            import psutil
            import os
            process = psutil.Process(os.getpid())
            result["memory"] = {
                "used": process.memory_info().rss / 1024 / 1024,  # MB
                "percent": process.memory_percent()
            }
            result["cpu"] = {
                "percent": process.cpu_percent(interval=0.1)
            }
        except ImportError:
            result["note"] = "psutil not available for detailed stats"
        
        return result
    except Exception as e:
        return {
            "error": f"Failed to get system health: {str(e)}",
            "type": type(e).__name__
        }


def format_uptime(seconds: float) -> str:
    """Format uptime in human-readable format."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    elif seconds < 86400:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"
    else:
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        return f"{days}d {hours}h"


def get_node_management() -> Dict[str, Any]:
    """Get node management information (ban list, admin list, etc.)."""
    try:
        import modules.settings as settings_module
        
        bbs_ban_list = getattr(settings_module, 'bbs_ban_list', [])
        bbs_admin_list = getattr(settings_module, 'bbs_admin_list', [])
        auto_banlist = getattr(settings_module, 'autoBanlist', [])
        
        return {
            "success": True,
            "bannedNodes": [str(n) for n in bbs_ban_list] if isinstance(bbs_ban_list, list) else [],
            "adminNodes": [str(n) for n in bbs_admin_list] if isinstance(bbs_admin_list, list) else [],
            "autoBanned": [str(n) for n in auto_banlist] if isinstance(auto_banlist, list) else []
        }
    except Exception as e:
        return {
            "error": f"Failed to get node management data: {str(e)}",
            "type": type(e).__name__
        }


def get_log_data(log_type: str = 'system', lines: int = 500, level_filter: str = None) -> Dict[str, Any]:
    """
    Get log data from log files.
    
    Args:
        log_type: Type of log to retrieve ('system' or 'messages')
        lines: Number of lines to retrieve (default: 500, max: 5000)
        level_filter: Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    
    Returns:
        Dictionary with log data
    """
    try:
        import glob
        
        # Determine log file path
        if log_type == 'messages':
            log_file = 'logs/messages.log'
        else:
            log_file = 'logs/meshbot.log'
        
        # Check if log file exists
        if not os.path.exists(log_file):
            # Try to find rotated log files
            rotated_logs = glob.glob(f'{log_file}.*')
            if rotated_logs:
                # Use the most recent rotated log
                rotated_logs.sort(reverse=True)
                log_file = rotated_logs[0]
            else:
                return {
                    "error": f"Log file not found: {log_file}",
                    "logs": [],
                    "count": 0
                }
        
        # Read log file - use efficient tail reading for large files
        log_lines = []
        try:
            # For large files, read from the end instead of loading everything
            file_size = os.path.getsize(log_file)
            max_read_size = min(10 * 1024 * 1024, file_size)  # Read max 10MB
            
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                if file_size > max_read_size:
                    # For large files, seek to near the end and read from there
                    f.seek(max(0, file_size - max_read_size))
                    # Skip the first (possibly incomplete) line
                    f.readline()
                    all_lines = f.readlines()
                else:
                    # For smaller files, read normally
                    all_lines = f.readlines()
                
                # Get the last N lines
                log_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        except Exception as e:
            return {
                "error": f"Error reading log file: {str(e)}",
                "logs": [],
                "count": 0
            }
        
        # Parse and filter log lines
        parsed_logs = []
        for line in log_lines:
            line = line.strip()
            if not line:
                continue
            
            # Parse log line format: "2025-12-14 22:00:55,922 |    DEBUG | System: message"
            log_entry = {
                "raw": line,
                "timestamp": "",
                "level": "",
                "message": line
            }
            
            # Try to parse structured log format
            if ' | ' in line:
                parts = line.split(' | ', 2)
                if len(parts) >= 3:
                    log_entry["timestamp"] = parts[0].strip()
                    log_entry["level"] = parts[1].strip()
                    log_entry["message"] = parts[2].strip()
                elif len(parts) == 2:
                    log_entry["timestamp"] = parts[0].strip()
                    log_entry["message"] = parts[1].strip()
            
            # Apply level filter if specified
            if level_filter and log_entry["level"].upper() != level_filter.upper():
                continue
            
            parsed_logs.append(log_entry)
        
        return {
            "success": True,
            "logs": parsed_logs,
            "count": len(parsed_logs),
            "total_lines": len(log_lines),
            "log_file": log_file,
            "log_type": log_type
        }
        
    except Exception as e:
        return {
            "error": f"Failed to get log data: {str(e)}",
            "type": type(e).__name__,
            "logs": [],
            "count": 0
        }


def send_mesh_message(message: str, channel: int = 0, node_id: int = 0, interface: int = 1) -> Dict[str, Any]:
    """Send a message via the mesh network."""
    try:
        system_module, globals_dict = get_system_globals()
        if not system_module or not globals_dict:
            return {"error": "System module not available"}
        
        # Import send_message function
        send_message_func = getattr(system_module, 'send_message', None)
        if not send_message_func:
            return {"error": "send_message function not available"}
        
        # Send the message
        result = send_message_func(message, channel, node_id, interface)
        
        if result:
            return {
                "success": True,
                "message": "Message sent successfully"
            }
        else:
            return {
                "error": "Failed to send message"
            }
    except Exception as e:
        return {
            "error": f"Failed to send message: {str(e)}",
            "type": type(e).__name__
        }


class WebUIRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP request handler for Web UI."""
    
    def handle(self):
        """Override handle to catch all exceptions and prevent server crashes."""
        try:
            super().handle()
        except Exception as e:
            import sys
            import traceback
            print(f"Web UI: Unhandled exception in request handler: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            # Try to send error response
            try:
                if not self.wfile.closed:
                    self.send_response(500)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    response = {"error": str(e), "type": type(e).__name__}
                    json_response = json.dumps(response, indent=2, default=str)
                    self.wfile.write(json_response.encode('utf-8'))
            except:
                pass
    
    def do_GET(self):
        """Handle GET requests."""
        global update_interval, auto_update_enabled
        parsed_path = urllib.parse.urlparse(self.path)
        path_parts = parsed_path.path.strip('/').split('/')
        
        try:
            if path_parts[0] == '':
                # Root - serve web UI
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type')
                self.end_headers()
                self.wfile.write(get_web_ui_html().encode('utf-8'))
                return
            elif path_parts[0] == 'events':
                # Server-Sent Events endpoint for real-time updates
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Connection', 'keep-alive')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                
                # Add this client to the SSE clients list
                with sse_lock:
                    sse_clients.append(self.wfile)
                
                # Send initial connection message
                try:
                    self.wfile.write(f"data: {json.dumps({'type': 'connected', 'interval': update_interval, 'enabled': auto_update_enabled})}\n\n".encode('utf-8'))
                    self.wfile.flush()
                except:
                    pass
                
                # Keep connection alive and send periodic updates
                try:
                    while True:
                        if not auto_update_enabled:
                            time.sleep(1)
                            continue
                        
                        # Send heartbeat every 30 seconds to keep connection alive
                        self.wfile.write(f": heartbeat\n\n".encode('utf-8'))
                        self.wfile.flush()
                        time.sleep(update_interval)
                        
                        # Send update event
                        update_data = {
                            'type': 'update',
                            'timestamp': datetime.now().isoformat(),
                            'interval': update_interval
                        }
                        self.wfile.write(f"data: {json.dumps(update_data)}\n\n".encode('utf-8'))
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    # Client disconnected
                    pass
                finally:
                    # Remove client from list
                    with sse_lock:
                        if self.wfile in sse_clients:
                            sse_clients.remove(self.wfile)
                return
            elif path_parts[0] == 'api':
                # API endpoints
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type')
                self.end_headers()
                
                if len(path_parts) > 1:
                    if path_parts[1] == 'update-settings':
                        # Get or update auto-update settings
                        if self.command == 'GET':
                            # Return current settings
                            response = {
                                "success": True,
                                "interval": update_interval,
                                "enabled": auto_update_enabled
                            }
                        else:
                            # Update settings (POST)
                            content_length = int(self.headers.get('Content-Length', 0))
                            if content_length > 0:
                                post_data = self.rfile.read(content_length)
                                request_data = json.loads(post_data.decode('utf-8'))
                                if 'interval' in request_data:
                                    update_interval = max(1, min(60, int(request_data['interval'])))
                                if 'enabled' in request_data:
                                    auto_update_enabled = bool(request_data['enabled'])
                                
                                # Broadcast settings change to all SSE clients
                                with sse_lock:
                                    for client in sse_clients[:]:
                                        try:
                                            settings_data = {
                                                'type': 'settings',
                                                'interval': update_interval,
                                                'enabled': auto_update_enabled
                                            }
                                            client.write(f"data: {json.dumps(settings_data)}\n\n".encode('utf-8'))
                                            client.flush()
                                        except:
                                            if client in sse_clients:
                                                sse_clients.remove(client)
                            
                            response = {
                                "success": True,
                                "interval": update_interval,
                                "enabled": auto_update_enabled
                            }
                    elif path_parts[1] == 'config':
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
                        position = get_position_metadata()
                        response = {
                            "success": True,
                            "nodes": nodes,
                            "position": position
                        }
                    elif path_parts[1] == 'activity':
                        # Get message history/activity feed
                        limit = 100
                        if len(path_parts) > 2 and path_parts[2].isdigit():
                            limit = int(path_parts[2])
                        response = get_message_history(limit)
                    elif path_parts[1] == 'node':
                        # Get detailed node information
                        if len(path_parts) > 2:
                            node_id = path_parts[2]
                            interface_num = None
                            if len(path_parts) > 3 and path_parts[3].isdigit():
                                interface_num = int(path_parts[3])
                            response = get_node_details(node_id, interface_num)
                        else:
                            response = {"error": "Node ID required"}
                    elif path_parts[1] == 'health':
                        # Get system health
                        response = get_system_health()
                    elif path_parts[1] == 'management':
                        # Get node management data
                        response = get_node_management()
                    elif path_parts[1] == 'export':
                        # Export data
                        export_type = path_parts[2] if len(path_parts) > 2 else 'nodes'
                        if export_type == 'nodes':
                            response = get_node_data()
                        elif export_type == 'telemetry':
                            response = get_rf_telemetry()
                        elif export_type == 'bbs':
                            response = get_bbs_messages()
                        elif export_type == 'activity':
                            response = get_message_history(1000)
                        else:
                            response = {"error": "Unknown export type"}
                    elif path_parts[1] == 'update':
                        # Update status and operations
                        from modules.updater import get_update_status, perform_update, check_for_updates, get_changelog
                        if len(path_parts) > 2 and path_parts[2] == 'check':
                            response = check_for_updates()
                        elif len(path_parts) > 2 and path_parts[2] == 'changelog':
                            # Parse limit from query string
                            limit = 20
                            if parsed_path.query:
                                query_params = urllib.parse.parse_qs(parsed_path.query)
                                if 'limit' in query_params:
                                    try:
                                        limit = int(query_params['limit'][0])
                                    except (ValueError, IndexError):
                                        limit = 20
                            response = get_changelog(limit=limit)
                        elif len(path_parts) > 2 and path_parts[2] == 'status':
                            response = get_update_status()
                        else:
                            response = get_update_status()
                    elif path_parts[1] == 'logs':
                        # Get log data
                        log_type = 'system'  # default to system logs
                        lines = 500  # default to last 500 lines
                        level_filter = None
                        
                        if parsed_path.query:
                            query_params = urllib.parse.parse_qs(parsed_path.query)
                            if 'type' in query_params:
                                log_type = query_params['type'][0]
                            if 'lines' in query_params:
                                try:
                                    lines = int(query_params['lines'][0])
                                    lines = max(1, min(5000, lines))  # Limit between 1 and 5000
                                except (ValueError, IndexError):
                                    lines = 500
                            if 'level' in query_params:
                                level_filter = query_params['level'][0].upper()
                        
                        response = get_log_data(log_type=log_type, lines=lines, level_filter=level_filter)
                    else:
                        response = {"error": "Unknown API endpoint"}
                else:
                    response = {"error": "API endpoint required"}
                
                json_response = json.dumps(response, indent=2, default=str)
                self.wfile.write(json_response.encode('utf-8'))
                return
            else:
                # Unknown path
                self.send_response(404)
                self.send_header('Content-Type', 'text/html')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.send_error(404, "Not Found")
                return
        except Exception as e:
            # Log the error for debugging
            import sys
            import traceback
            print(f"Web UI: Error handling GET request for {self.path}: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            
            # Ensure we can send error response even if headers were partially sent
            try:
                # Try to send error response
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                response = {"error": str(e), "type": type(e).__name__}
                json_response = json.dumps(response, indent=2, default=str)
                self.wfile.write(json_response.encode('utf-8'))
            except Exception as send_error:
                # If we can't send error response (headers already sent), try to write to body
                print(f"Web UI: Failed to send error response: {send_error}", file=sys.stderr)
                try:
                    # Try to write error to response body if headers were already sent
                    response = {"error": str(e), "type": type(e).__name__}
                    json_response = json.dumps(response, indent=2, default=str)
                    self.wfile.write(json_response.encode('utf-8'))
                except:
                    # Last resort - try send_error
                    try:
                        self.send_error(500, "Internal Server Error")
                    except:
                        pass
    
    def do_POST(self):
        """Handle POST requests."""
        try:
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
                    content_length = int(self.headers.get('Content-Length', 0))
                    post_data = self.rfile.read(content_length) if content_length > 0 else b'{}'
                    request_data = json.loads(post_data.decode('utf-8')) if post_data else {}
                    
                    if path_parts[1] == 'config':
                        # Save configuration
                        response = write_config(request_data.get('config', {}))
                    elif path_parts[1] == 'update':
                        # Perform update
                        from modules.updater import perform_update
                        dry_run = request_data.get('dry_run', False)
                        reset_on_conflict = request_data.get('reset_on_conflict', False)
                        response = perform_update(dry_run=dry_run, reset_on_conflict=reset_on_conflict)
                    elif path_parts[1] == 'send':
                        # Send a message
                        message = request_data.get('message', '')
                        channel = request_data.get('channel', 0)
                        node_id = request_data.get('node_id', 0)
                        interface = request_data.get('interface', 1)
                        
                        if not message:
                            response = {"error": "Message is required"}
                        else:
                            response = send_mesh_message(message, channel, node_id, interface)
                    else:
                        response = {"error": "Unknown POST endpoint"}
                else:
                    response = {"error": "Invalid POST request"}
                
                json_response = json.dumps(response, indent=2, default=str)
                self.wfile.write(json_response.encode('utf-8'))
            except Exception as e:
                # Inner exception - response headers already sent
                response = {"error": str(e), "type": type(e).__name__}
                json_response = json.dumps(response, indent=2, default=str)
                self.wfile.write(json_response.encode('utf-8'))
        except Exception as e:
            # Log the error for debugging
            import sys
            import traceback
            print(f"Web UI: Error handling POST request for {self.path}: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            
            # Outer exception - ensure we can send error response
            try:
                # Check if headers were sent by trying to send them
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                response = {"error": str(e), "type": type(e).__name__}
                json_response = json.dumps(response, indent=2, default=str)
                self.wfile.write(json_response.encode('utf-8'))
            except Exception as send_error:
                # If we can't send error response (headers already sent), log it
                print(f"Web UI: Failed to send error response: {send_error}", file=sys.stderr)
                try:
                    # Try to write error to response body if headers were already sent
                    response = {"error": str(e), "type": type(e).__name__}
                    json_response = json.dumps(response, indent=2, default=str)
                    self.wfile.write(json_response.encode('utf-8'))
                except:
                    pass
    
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
        
        :root {
            --primary: #6366f1;
            --primary-dark: #4f46e5;
            --primary-light: #818cf8;
            --secondary: #8b5cf6;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
            --info: #3b82f6;
            --bg-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
            --card-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
            --card-shadow-hover: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Inter', sans-serif;
            background: var(--bg-gradient);
            background-attachment: fixed;
            color: #1f2937;
            min-height: 100vh;
            padding: 20px;
            line-height: 1.6;
        }
        .container { max-width: 1800px; margin: 0 auto; }
        header {
            background: rgba(255, 255, 255, 0.98);
            backdrop-filter: blur(10px);
            padding: 24px 32px;
            border-radius: 16px;
            margin-bottom: 24px;
            box-shadow: var(--card-shadow);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        h1 { 
            color: var(--primary);
            margin-bottom: 8px;
            font-size: 28px;
            font-weight: 700;
            letter-spacing: -0.5px;
        }
        .tabs {
            display: flex;
            gap: 8px;
            margin-bottom: 24px;
            flex-wrap: wrap;
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            padding: 8px;
            border-radius: 12px;
        }
        .tab {
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            color: #4b5563;
            position: relative;
            overflow: hidden;
        }
        .tab::before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.3), transparent);
            transition: left 0.5s;
        }
        .tab:hover::before {
            left: 100%;
        }
        .tab:hover { 
            background: rgba(255, 255, 255, 0.95);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }
        .tab.active { 
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: white;
            box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
            transform: translateY(-2px);
        }
        .content {
            background: rgba(255, 255, 255, 0.98);
            backdrop-filter: blur(10px);
            padding: 32px;
            border-radius: 16px;
            box-shadow: var(--card-shadow);
            min-height: 500px;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        .tab-content { 
            display: none;
            animation: fadeIn 0.3s ease-in;
        }
        .tab-content.active { 
            display: block; 
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 24px;
            margin-bottom: 24px;
        }
        .card {
            background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
            padding: 24px;
            border-radius: 12px;
            border: 1px solid rgba(226, 232, 240, 0.8);
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
        }
        .card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
            background: linear-gradient(180deg, var(--primary) 0%, var(--secondary) 100%);
            transition: width 0.3s;
        }
        .card:hover {
            transform: translateY(-4px);
            box-shadow: var(--card-shadow-hover);
            border-color: rgba(99, 102, 241, 0.3);
        }
        .card:hover::before {
            width: 100%;
            opacity: 0.05;
        }
        .card h3 { 
            color: var(--primary);
            margin-bottom: 16px;
            font-size: 18px;
            font-weight: 700;
            position: relative;
            z-index: 1;
        }
        .stat {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid rgba(226, 232, 240, 0.8);
            transition: background 0.2s;
        }
        .stat:hover {
            background: rgba(99, 102, 241, 0.05);
            margin: 0 -24px;
            padding-left: 24px;
            padding-right: 24px;
            border-radius: 8px;
        }
        .stat:last-child { border-bottom: none; }
        .stat span:last-child {
            font-weight: 600;
            color: var(--primary);
            font-size: 15px;
        }
        .config-section {
            margin-bottom: 32px;
            background: linear-gradient(135deg, #f8fafc 0%, #ffffff 100%);
            border-radius: 12px;
            border: 1px solid rgba(226, 232, 240, 0.8);
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
            overflow: hidden;
        }
        .config-section-header {
            padding: 20px 24px;
            cursor: pointer;
            user-select: none;
            display: flex;
            align-items: center;
            justify-content: space-between;
            transition: background 0.2s;
        }
        .config-section-header:hover {
            background: rgba(99, 102, 241, 0.05);
        }
        .config-section h3 {
            color: var(--primary);
            margin: 0;
            font-size: 20px;
            font-weight: 700;
            flex: 1;
        }
        .config-section-toggle {
            font-size: 18px;
            color: var(--primary);
            transition: transform 0.3s;
            margin-left: 12px;
        }
        .config-section.collapsed .config-section-toggle {
            transform: rotate(-90deg);
        }
        .config-section-content {
            padding: 0 24px 24px 24px;
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease-out, padding 0.3s ease-out;
        }
        .config-section:not(.collapsed) .config-section-content {
            max-height: 10000px;
            padding: 0 24px 24px 24px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #374151;
            font-size: 14px;
        }
        .form-group input,
        .form-group select,
        .form-group textarea {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            font-size: 14px;
            transition: all 0.2s;
            background: white;
        }
        .form-group input:focus,
        .form-group select:focus,
        .form-group textarea:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
        }
        .form-group input[type="checkbox"] {
            width: auto;
            margin-right: 8px;
            cursor: pointer;
        }
        .btn {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            margin-right: 12px;
            margin-bottom: 8px;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 4px 6px rgba(99, 102, 241, 0.25);
            position: relative;
            overflow: hidden;
        }
        .btn::before {
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            width: 0;
            height: 0;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.3);
            transform: translate(-50%, -50%);
            transition: width 0.6s, height 0.6s;
        }
        .btn:hover::before {
            width: 300px;
            height: 300px;
        }
        .btn:hover { 
            transform: translateY(-2px);
            box-shadow: 0 6px 12px rgba(99, 102, 241, 0.35);
        }
        .btn:active {
            transform: translateY(0);
        }
        .btn-success { 
            background: linear-gradient(135deg, var(--success) 0%, #059669 100%);
            box-shadow: 0 4px 6px rgba(16, 185, 129, 0.25);
        }
        .btn-success:hover {
            box-shadow: 0 6px 12px rgba(16, 185, 129, 0.35);
        }
        .btn-danger { 
            background: linear-gradient(135deg, var(--danger) 0%, #dc2626 100%);
            box-shadow: 0 4px 6px rgba(239, 68, 68, 0.25);
        }
        .btn-danger:hover {
            box-shadow: 0 6px 12px rgba(239, 68, 68, 0.35);
        }
        .loading { 
            text-align: center; 
            padding: 60px; 
            color: #6b7280;
            font-size: 16px;
        }
        .loading::after {
            content: '...';
            animation: dots 1.5s steps(4, end) infinite;
        }
        @keyframes dots {
            0%, 20% { content: '.'; }
            40% { content: '..'; }
            60%, 100% { content: '...'; }
        }
        .error {
            background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%);
            color: #991b1b;
            padding: 16px 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            border-left: 4px solid var(--danger);
            box-shadow: 0 2px 4px rgba(239, 68, 68, 0.1);
        }
        .success {
            background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%);
            color: #065f46;
            padding: 16px 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            border-left: 4px solid var(--success);
            box-shadow: 0 2px 4px rgba(16, 185, 129, 0.1);
        }
        table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            margin-top: 24px;
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        }
        th, td {
            padding: 14px 16px;
            text-align: left;
            border-bottom: 1px solid #e5e7eb;
        }
        th {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            font-weight: 700;
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        tr {
            transition: background 0.2s;
        }
        tr:hover { 
            background: rgba(99, 102, 241, 0.05);
        }
        tr:last-child td {
            border-bottom: none;
        }
        .badge {
            display: inline-block;
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }
        .badge.success { 
            background: linear-gradient(135deg, var(--success) 0%, #059669 100%);
            color: white; 
        }
        .badge.warning { 
            background: linear-gradient(135deg, var(--warning) 0%, #d97706 100%);
            color: white; 
        }
        .badge.danger { 
            background: linear-gradient(135deg, var(--danger) 0%, #dc2626 100%);
            color: white; 
        }
        .badge.info { 
            background: linear-gradient(135deg, var(--info) 0%, #2563eb 100%);
            color: white; 
        }
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
            background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 16px;
            border-left: 4px solid var(--primary);
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            transition: all 0.2s;
        }
        .bbs-message:hover {
            transform: translateX(4px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }
        .bbs-message-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 12px;
            font-weight: 700;
            color: var(--primary);
            font-size: 13px;
        }
        .bbs-message-body {
            color: #374151;
            margin-top: 12px;
            white-space: pre-wrap;
            line-height: 1.6;
        }
        .bbs-message-meta {
            font-size: 12px;
            color: #6b7280;
            margin-top: 12px;
            padding-top: 12px;
            border-top: 1px solid rgba(226, 232, 240, 0.8);
        }
    </style>
    <!-- Leaflet CSS for OpenStreetMap -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
</head>
<body>
    <div class="container">
        <header>
            <h1>📡 Meshing-Around Dashboard & Configuration</h1>
            <p style="color: #6b7280; font-size: 15px; margin-top: 4px;">Monitor your mesh network and configure all settings</p>
        </header>
        
        <div class="tabs">
            <button class="tab active" onclick="showTab('dashboard', this)">📊 Dashboard</button>
            <button class="tab" onclick="showTab('activity', this)">📨 Activity</button>
            <button class="tab" onclick="showTab('map', this)">🗺️ Node Map</button>
            <button class="tab" onclick="showTab('nodes', this)">📡 Nodes</button>
            <button class="tab" onclick="showTab('node-details', this)">🔍 Node Details</button>
            <button class="tab" onclick="showTab('telemetry', this)">📈 RF Telemetry</button>
            <button class="tab" onclick="showTab('statistics', this)">📊 Statistics</button>
            <button class="tab" onclick="showTab('network', this)">🌐 Network</button>
            <button class="tab" onclick="showTab('health', this)">💚 Health</button>
            <button class="tab" onclick="showTab('alerts', this)">🚨 Alerts</button>
            <button class="tab" onclick="showTab('bbs', this)">💬 BBS</button>
            <button class="tab" onclick="showTab('composer', this)">✉️ Send</button>
            <button class="tab" onclick="showTab('management', this)">👥 Management</button>
            <button class="tab" onclick="showTab('leaderboard', this)">🏆 Leaderboard</button>
            <button class="tab" onclick="showTab('update', this)">🔄 Update</button>
            <button class="tab" onclick="showTab('logs', this)">📋 Logs</button>
            <button class="tab" onclick="showTab('config', this)">⚙️ Config</button>
        </div>
        
        <div class="content">
            <div id="dashboard" class="tab-content active">
                <h2>Dashboard Overview</h2>
                <div id="dashboard-content" class="loading">Loading dashboard data...</div>
            </div>
            
            <div id="update" class="tab-content">
                <h2>🔄 Auto-Update</h2>
                <div id="update-content" class="loading">Loading update status...</div>
            </div>
            
            <div id="logs" class="tab-content">
                <h2>📋 Log Viewer</h2>
                <div id="logs-content" class="loading">Loading logs...</div>
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
                <div style="margin-bottom: 20px;">
                    <button class="btn" onclick="exportData('telemetry')">📥 Export Telemetry (JSON)</button>
                </div>
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
                <div style="margin-bottom: 20px;">
                    <button class="btn" onclick="exportData('bbs')">📥 Export BBS (JSON)</button>
                </div>
                <div id="bbs-content" class="loading">Loading BBS messages...</div>
            </div>
            
            <div id="activity" class="tab-content">
                <h2>Activity Feed</h2>
                <div style="margin-bottom: 20px;">
                    <input type="text" id="activity-filter" placeholder="Filter messages..." style="padding: 8px; width: 300px; border-radius: 6px; border: 1px solid #d1d5db;" onkeyup="filterActivity()">
                    <button class="btn" onclick="loadActivity()" style="margin-left: 10px;">🔄 Refresh</button>
                </div>
                <div id="activity-content" class="loading">Loading activity feed...</div>
            </div>
            
            <div id="node-details" class="tab-content">
                <h2>Node Details</h2>
                <div style="margin-bottom: 20px;">
                    <input type="text" id="node-search" placeholder="Enter Node ID (hex or decimal)" style="padding: 8px; width: 300px; border-radius: 6px; border: 1px solid #d1d5db;">
                    <button class="btn" onclick="loadNodeDetails()" style="margin-left: 10px;">🔍 Search</button>
                </div>
                <div id="node-details-content" class="loading">Enter a Node ID to view details</div>
            </div>
            
            <div id="statistics" class="tab-content">
                <h2>Statistics & Charts</h2>
                <div style="margin-bottom: 20px;">
                    <select id="stat-timeframe" onchange="loadStatistics()" style="padding: 8px; border-radius: 6px; border: 1px solid #d1d5db;">
                        <option value="hour">Last Hour</option>
                        <option value="day" selected>Last 24 Hours</option>
                        <option value="week">Last Week</option>
                    </select>
                </div>
                <div id="statistics-content" class="loading">Loading statistics...</div>
            </div>
            
            <div id="network" class="tab-content">
                <h2>Network Graph / Topology</h2>
                <div id="network-content" class="loading">Loading network graph...</div>
            </div>
            
            <div id="health" class="tab-content">
                <h2>System Health</h2>
                <div id="health-content" class="loading">Loading system health...</div>
            </div>
            
            <div id="alerts" class="tab-content">
                <h2>Alert Center</h2>
                <div id="alerts-content" class="loading">Loading alerts...</div>
            </div>
            
            <div id="composer" class="tab-content">
                <h2>Message Composer</h2>
                <div class="config-section">
                    <div class="form-group">
                        <label>Message</label>
                        <textarea id="composer-message" rows="4" placeholder="Enter your message..." style="width: 100%; padding: 10px; border-radius: 6px; border: 1px solid #d1d5db;"></textarea>
                    </div>
                    <div class="form-group">
                        <label>Send To</label>
                        <select id="composer-type" onchange="updateComposerType()" style="width: 100%; padding: 10px; border-radius: 6px; border: 1px solid #d1d5db;">
                            <option value="channel">Channel</option>
                            <option value="node">Direct Message (Node)</option>
                        </select>
                    </div>
                    <div class="form-group" id="composer-channel-group">
                        <label>Channel Number</label>
                        <input type="number" id="composer-channel" value="0" min="0" style="width: 100%; padding: 10px; border-radius: 6px; border: 1px solid #d1d5db;">
                    </div>
                    <div class="form-group" id="composer-node-group" style="display: none;">
                        <label>Node ID (hex or decimal)</label>
                        <input type="text" id="composer-node" placeholder="!12345678 or 12345678" style="width: 100%; padding: 10px; border-radius: 6px; border: 1px solid #d1d5db;">
                    </div>
                    <div class="form-group">
                        <label>Interface</label>
                        <select id="composer-interface" style="width: 100%; padding: 10px; border-radius: 6px; border: 1px solid #d1d5db;">
                            <option value="1">Interface 1</option>
                            <option value="2">Interface 2</option>
                            <option value="3">Interface 3</option>
                            <option value="4">Interface 4</option>
                            <option value="5">Interface 5</option>
                            <option value="6">Interface 6</option>
                            <option value="7">Interface 7</option>
                            <option value="8">Interface 8</option>
                            <option value="9">Interface 9</option>
                        </select>
                    </div>
                    <button class="btn btn-success" onclick="sendMessage()">📤 Send Message</button>
                    <div id="composer-result" style="margin-top: 15px;"></div>
                </div>
            </div>
            
            <div id="management" class="tab-content">
                <h2>Node Management</h2>
                <div id="management-content" class="loading">Loading management data...</div>
            </div>
        </div>
    </div>
    
    <!-- Leaflet JS for OpenStreetMap -->
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <!-- Chart.js for statistics -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    
    <script>
        // Define showTab first to ensure it's available
        function showTab(tabName, buttonElement) {
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            
            const tabContent = document.getElementById(tabName);
            if (!tabContent) {
                console.error('Tab content not found:', tabName);
                return;
            }
            tabContent.classList.add('active');
            
            // Activate the clicked tab button
            if (buttonElement) {
                buttonElement.classList.add('active');
            } else {
                // Fallback: find button by onclick attribute
                const tabButtons = document.querySelectorAll('.tab');
                tabButtons.forEach(btn => {
                    if (btn.getAttribute('onclick') && btn.getAttribute('onclick').includes(tabName)) {
                        btn.classList.add('active');
                    }
                });
            }
            
            // Load appropriate data for each tab
            try {
                if (tabName === 'config') {
                    loadConfig();
                } else if (tabName === 'update') {
                    loadUpdateStatus();
                } else if (tabName === 'logs') {
                    loadLogs().catch(err => {
                        console.error('Error loading logs tab:', err);
                        const content = document.getElementById('logs-content');
                        if (content) {
                            content.innerHTML = `<div class="error" style="padding: 40px; text-align: center;">
                                <h3>Error Loading Logs</h3>
                                <p>${err.message || 'Unknown error'}</p>
                                <button class="btn" onclick="showTab('logs', this)" style="margin-top: 20px;">Retry</button>
                            </div>`;
                        }
                    });
                } else if (tabName === 'map') {
                    initMap();
                } else if (tabName === 'bbs') {
                    loadBBS();
                } else if (tabName === 'activity') {
                    loadActivity();
                } else if (tabName === 'health') {
                    loadHealth();
                } else if (tabName === 'management') {
                    loadManagement();
                } else if (tabName === 'statistics') {
                    loadStatistics();
                } else if (tabName === 'network') {
                    loadNetworkGraph();
                } else if (tabName === 'alerts') {
                    loadAlerts();
                } else {
                    refreshData();
                }
            } catch (error) {
                console.error('Error loading tab:', tabName, error);
                const content = tabContent.querySelector('.loading, [id$="-content"]');
                if (content) {
                    content.innerHTML = `<div class="error">Error loading tab: ${error.message}</div>`;
                }
            }
        }
        
        // Initialize variables
        const API_BASE = window.location.origin;
        let configData = {};
        let autoRefreshInterval = null;
        let map = null;
        let mapMarkers = [];
        let mapInitialized = false; // Track if map has been initialized
        let mapBoundsFitted = false; // Track if bounds have been fitted (to preserve zoom on updates)
        
        async function fetchAPI(endpoint, method='GET', data=null, timeout=30000) {
            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), timeout);
                
                const options = {
                    method: method,
                    headers: {'Content-Type': 'application/json'},
                    signal: controller.signal
                };
                if (data) options.body = JSON.stringify(data);
                
                const response = await fetch(`${API_BASE}/api/${endpoint}`, options);
                clearTimeout(timeoutId);
                
                if (!response.ok) {
                    const errorText = await response.text();
                    throw new Error(`HTTP ${response.status}: ${errorText.substring(0, 100)}`);
                }
                return await response.json();
            } catch (error) {
                if (error.name === 'AbortError') {
                    console.error(`Timeout fetching ${endpoint} after ${timeout}ms`);
                    return { error: `Request timed out after ${timeout/1000}s` };
                }
                console.error(`Error fetching ${endpoint}:`, error);
                return { error: error.message || 'Network error - server may be unavailable' };
            }
        }
        
        // User-friendly labels and descriptions for config options
        const configLabels = {
            'web_ui': {
                'enabled': { label: 'Enable Web Dashboard', desc: 'Turn the web interface on or off' },
                'host': { label: 'Network Address', desc: 'IP address to listen on (0.0.0.0 = all networks)' },
                'port': { label: 'Port Number', desc: 'Web interface port (default: 8420)' }
            },
            'mcp_server': {
                'enabled': { label: 'Enable API Server', desc: 'Turn the API server on or off' },
                'host': { label: 'Network Address', desc: 'IP address to listen on (0.0.0.0 = all networks)' },
                'port': { label: 'Port Number', desc: 'API server port (default: 8421)' }
            },
            'general': {
                'respond_by_dm_only': { label: 'Only Respond to Direct Messages', desc: 'If enabled, bot only responds to DMs, not channel messages' },
                'defaultChannel': { label: 'Default Channel', desc: 'Main public channel number (usually 0)' },
                'ignoreDefaultChannel': { label: 'Ignore Default Channel', desc: 'Do not respond to messages on the default channel' },
                'ignoreChannels': { label: 'Channels to Ignore', desc: 'Comma-separated list of channel numbers to ignore (e.g., 4,5)' },
                'explicitCmd': { label: 'Require Explicit Commands', desc: 'Only process messages that start with a command word' },
                'cmdBang': { label: 'Require ! Before Commands', desc: 'Commands must start with ! (e.g., !ping)' },
                'motd': { label: 'Message of the Day', desc: 'Message shown when bot starts' },
                'welcome_message': { label: 'Welcome Message', desc: 'Message sent to new users' },
                'whoami': { label: 'Enable Who Am I Command', desc: 'Allow users to ask who the bot is' },
                'zuluTime': { label: 'Use 24-Hour Time Format', desc: 'Display time in 24-hour format instead of 12-hour' },
                'favoriteNodeList': { label: 'Favorite Nodes', desc: 'Comma-separated list of node IDs to add as favorites' }
            },
            'bbs': {
                'enabled': { label: 'Enable Bulletin Board System', desc: 'Turn on the BBS messaging feature' },
                'bbs_ban_list': { label: 'Banned Node IDs', desc: 'Comma-separated list of node IDs that cannot use BBS' },
                'bbs_admin_list': { label: 'BBS Admin Node IDs', desc: 'Comma-separated list of node IDs with admin privileges' },
                'bbslink_enabled': { label: 'Enable BBS Linking', desc: 'Sync BBS messages with other bots' },
                'bbslink_whitelist': { label: 'BBS Link Whitelist', desc: 'Node IDs allowed to sync (empty = all)' }
            },
            'location': {
                'enabled': { label: 'Enable Location Features', desc: 'Turn on location-based features' },
                'lat': { label: 'Latitude', desc: 'Your location latitude (for weather, alerts, etc.)' },
                'lon': { label: 'Longitude', desc: 'Your location longitude (for weather, alerts, etc.)' },
                'fuzzConfigLocation': { label: 'Fuzz Location', desc: 'Add random offset to protect privacy' },
                'useMetric': { label: 'Use Metric Units', desc: 'Display distances in metric instead of imperial' }
            },
            'sentry': {
                'SentryEnabled': { label: 'Enable Proximity Alerts', desc: 'Alert when nodes get close to your location' },
                'SentryRadius': { label: 'Alert Radius (meters)', desc: 'Distance in meters to trigger proximity alert' },
                'SentryChannel': { label: 'Alert Channel', desc: 'Channel number to send proximity alerts' },
                'SentryHoldoff': { label: 'Alert Holdoff Time', desc: 'Wait time before sending another alert (multiplied by 20 seconds)' },
                'sentryIgnoreList': { label: 'Nodes to Ignore', desc: 'Comma-separated node IDs to ignore for proximity' },
                'sentryWatchList': { label: 'Nodes to Watch', desc: 'Comma-separated node IDs to specifically watch' },
                'highFlyingAlert': { label: 'High Altitude Alerts', desc: 'Alert when nodes are detected at high altitude' },
                'highFlyingAlertAltitude': { label: 'High Altitude Threshold (meters)', desc: 'Altitude in meters to trigger alert' }
            },
            'games': {
                'dopeWars': { label: 'Dope Wars Game', desc: 'Enable the Dope Wars game' },
                'lemonade': { label: 'Lemonade Stand Game', desc: 'Enable the Lemonade Stand game' },
                'blackjack': { label: 'Blackjack Game', desc: 'Enable the Blackjack game' },
                'videopoker': { label: 'Video Poker Game', desc: 'Enable the Video Poker game' },
                'mastermind': { label: 'Mastermind Game', desc: 'Enable the Mastermind game' },
                'golfsim': { label: 'Golf Simulator', desc: 'Enable the Golf Simulator game' },
                'hangman': { label: 'Hangman Game', desc: 'Enable the Hangman game' },
                'hamtest': { label: 'Ham Test Practice', desc: 'Enable ham radio test practice questions' },
                'tictactoe': { label: 'Tic Tac Toe Game', desc: 'Enable the Tic Tac Toe game' },
                'wordOfTheDay': { label: 'Word of the Day', desc: 'Enable the Word of the Day feature' },
                'battleShip': { label: 'Battleship Game', desc: 'Enable the Battleship game' },
                'quiz': { label: 'Quiz Game', desc: 'Enable the quiz game module' },
                'survey': { label: 'Survey Game', desc: 'Enable the survey game module' }
            },
            'messagingSettings': {
                'responseDelay': { label: 'Response Delay (seconds)', desc: 'Wait time before sending responses to avoid collisions' },
                'splitDelay': { label: 'Split Message Delay (seconds)', desc: 'Wait time between message chunks' },
                'MESSAGE_CHUNK_SIZE': { label: 'Max Message Size (characters)', desc: 'Maximum characters per message chunk' },
                'wantAck': { label: 'Request Message Acknowledgement', desc: 'Request confirmation that messages were received' },
                'maxBuffer': { label: 'Max Buffer Size (bytes)', desc: 'Maximum buffer size for radio testing' }
            },
            'emergencyHandler': {
                'enabled': { label: 'Enable Emergency Handler', desc: 'Detect and respond to emergency keywords' },
                'alert_channel': { label: 'Alert Channel', desc: 'Channel to send emergency alerts' },
                'alert_interface': { label: 'Alert Interface', desc: 'Radio interface to send alerts from' }
            },
            'repeater': {
                'enabled': { label: 'Enable Repeater Mode', desc: 'Forward messages between channels/interfaces' },
                'repeater_channels': { label: 'Repeater Channels', desc: 'Comma-separated list of channels to repeat (e.g., 2,3)' }
            },
            'scheduler': {
                'enabled': { label: 'Enable Message Scheduler', desc: 'Schedule automatic messages' },
                'interface': { label: 'Scheduler Interface', desc: 'Radio interface to send scheduled messages' },
                'channel': { label: 'Scheduler Channel', desc: 'Channel to send scheduled messages' },
                'message': { label: 'Scheduled Message', desc: 'Message text to send' },
                'value': { label: 'Schedule Type', desc: 'Schedule type: min, hour, day, or special (weather, joke, etc.)' },
                'interval': { label: 'Interval', desc: 'Interval value (e.g., every 2 hours)' },
                'time': { label: 'Time of Day', desc: 'Time in 24-hour format (HH:MM) for daily schedules' }
            },
            'interface': {
                'type': { label: 'Connection Type', desc: 'How to connect: serial, tcp, or ble' },
                'port': { label: 'Serial Port', desc: 'Serial port device (e.g., /dev/ttyACM0)' },
                'hostname': { label: 'TCP Hostname', desc: 'IP address or hostname for TCP connection' },
                'mac': { label: 'Bluetooth MAC Address', desc: 'MAC address for Bluetooth Low Energy connection' },
                'enabled': { label: 'Enable Interface', desc: 'Turn this radio interface on or off' }
            }
        };
        
        // Group config sections logically
        const configGroups = {
            'Web Interface': ['web_ui', 'mcp_server'],
            'Radio Interfaces': ['interface', 'interface2', 'interface3', 'interface4', 'interface5', 'interface6', 'interface7', 'interface8', 'interface9'],
            'Basic Bot Settings': ['general'],
            'Messaging': ['messagingSettings', 'StoreForward'],
            'Bulletin Board System': ['bbs'],
            'Location & Weather': ['location'],
            'Alerts & Monitoring': ['sentry', 'emergencyHandler'],
            'Games & Entertainment': ['games'],
            'Information Sources': ['rss', 'wikipedia', 'news'],
            'AI & Language': ['ollama', 'OpenWebUI'],
            'Advanced Features': ['repeater', 'scheduler', 'checklist', 'inventory', 'qrz'],
            'Radio Monitoring': ['radioMon', 'fileMon'],
            'Email & Communication': ['smtp'],
            'Logging & Debugging': ['logging']
        };
        
        function getConfigLabel(section, key) {
            if (configLabels[section] && configLabels[section][key]) {
                return configLabels[section][key];
            }
            // Generate friendly label from key name
            const friendly = key
                .replace(/([A-Z])/g, ' $1')
                .replace(/^./, str => str.toUpperCase())
                .trim();
            return { label: friendly, desc: '' };
        }
        
        function formatSectionName(section) {
            if (section.startsWith('interface')) {
                const num = section.replace('interface', '');
                return num === '' ? 'Primary Radio' : `Radio ${num}`;
            }
            return section
                .replace(/([A-Z])/g, ' $1')
                .replace(/^./, str => str.toUpperCase())
                .trim();
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
            
            // Group and display config by logical groups
            for (const [groupName, sections] of Object.entries(configGroups)) {
                const groupSections = sections.filter(s => configData[s]);
                if (groupSections.length === 0) continue;
                
                const sectionId = `config-group-${groupName.replace(/\s+/g, '-').toLowerCase()}`;
                html += `<div class="config-section collapsed" id="${sectionId}">`;
                html += `<div class="config-section-header" onclick="toggleConfigSection('${sectionId}')">`;
                html += `<h3>${groupName}</h3>`;
                html += `<span class="config-section-toggle">▼</span>`;
                html += `</div>`;
                html += `<div class="config-section-content">`;
                
                for (const section of groupSections) {
                    const items = configData[section];
                    const sectionTitle = formatSectionName(section);
                    
                    if (sections.length > 1) {
                        html += `<h4 style="color: var(--primary); margin-top: 20px; margin-bottom: 12px; font-size: 16px; font-weight: 600;">${sectionTitle}</h4>`;
                    }
                    
                    for (const [key, value] of Object.entries(items)) {
                        const id = `${section}_${key}`;
                        const isBool = value === 'True' || value === 'False' || value === 'true' || value === 'false';
                        const labelInfo = getConfigLabel(section, key);
                        
                        html += `<div class="form-group">`;
                        html += `<label for="${id}">${labelInfo.label}</label>`;
                        if (labelInfo.desc) {
                            html += `<small style="display: block; color: #6b7280; margin-bottom: 6px; font-size: 12px;">${labelInfo.desc}</small>`;
                        }
                        
                        if (isBool) {
                            const checked = value === 'True' || value === 'true' ? 'checked' : '';
                            html += `<label style="display: flex; align-items: center; cursor: pointer; margin-top: 8px;">
                                <input type="checkbox" id="${id}" ${checked} style="width: 20px; height: 20px; margin-right: 10px;" onchange="updateConfigValue('${section}', '${key}', this.checked)">
                                <span>${checked ? 'Enabled' : 'Disabled'}</span>
                            </label>`;
                        } else if (key.toLowerCase().includes('password') || key.toLowerCase().includes('key') || key.toLowerCase().includes('token') || key.toLowerCase().includes('api')) {
                            html += `<input type="password" id="${id}" value="${value}" onchange="updateConfigValue('${section}', '${key}', this.value)" placeholder="Enter ${labelInfo.label.toLowerCase()}">`;
                        } else if (value.includes('\\n') || value.length > 100) {
                            html += `<textarea id="${id}" rows="4" onchange="updateConfigValue('${section}', '${key}', this.value)" placeholder="Enter ${labelInfo.label.toLowerCase()}">${value}</textarea>`;
                        } else if (key.toLowerCase().includes('port') || key.toLowerCase().includes('channel') || key.toLowerCase().includes('interval') || key.toLowerCase().includes('timeout') || key.toLowerCase().includes('radius') || key.toLowerCase().includes('altitude')) {
                            html += `<input type="number" id="${id}" value="${value}" onchange="updateConfigValue('${section}', '${key}', this.value)" placeholder="Enter ${labelInfo.label.toLowerCase()}">`;
                        } else {
                            html += `<input type="text" id="${id}" value="${value}" onchange="updateConfigValue('${section}', '${key}', this.value)" placeholder="Enter ${labelInfo.label.toLowerCase()}">`;
                        }
                        
                        html += `</div>`;
                    }
                }
                
                html += `</div></div>`;
            }
            
            // Handle any remaining sections not in groups
            const handledSections = new Set(Object.values(configGroups).flat());
            for (const [section, items] of Object.entries(configData)) {
                if (handledSections.has(section)) continue;
                
                const sectionId = `config-section-${section.replace(/\s+/g, '-').toLowerCase()}`;
                html += `<div class="config-section collapsed" id="${sectionId}">`;
                html += `<div class="config-section-header" onclick="toggleConfigSection('${sectionId}')">`;
                html += `<h3>${formatSectionName(section)}</h3>`;
                html += `<span class="config-section-toggle">▼</span>`;
                html += `</div>`;
                html += `<div class="config-section-content">`;
                for (const [key, value] of Object.entries(items)) {
                    const id = `${section}_${key}`;
                    const isBool = value === 'True' || value === 'False' || value === 'true' || value === 'false';
                    const labelInfo = getConfigLabel(section, key);
                    
                    html += `<div class="form-group">`;
                    html += `<label for="${id}">${labelInfo.label}</label>`;
                    if (labelInfo.desc) {
                        html += `<small style="display: block; color: #6b7280; margin-bottom: 6px; font-size: 12px;">${labelInfo.desc}</small>`;
                    }
                    
                    if (isBool) {
                        const checked = value === 'True' || value === 'true' ? 'checked' : '';
                        html += `<label style="display: flex; align-items: center; cursor: pointer; margin-top: 8px;">
                            <input type="checkbox" id="${id}" ${checked} style="width: 20px; height: 20px; margin-right: 10px;" onchange="updateConfigValue('${section}', '${key}', this.checked)">
                            <span>${checked ? 'Enabled' : 'Disabled'}</span>
                        </label>`;
                    } else {
                        html += `<input type="text" id="${id}" value="${value}" onchange="updateConfigValue('${section}', '${key}', this.value)">`;
                    }
                    
                    html += `</div>`;
                }
                html += `</div></div>`;
            }
            
            content.innerHTML = html;
        }
        
        // Store restart message globally so it persists across reloads
        let pendingRestartMessage = null;
        
        async function loadUpdateStatus() {
            const content = document.getElementById('update-content');
            try {
                const data = await fetchAPI('update/status');
                if (data.error) {
                    content.innerHTML = `<div class="error">Error: ${data.error}</div>`;
                    return;
                }
                
                const gitInfo = data.git_info || {};
                const canUpdate = data.can_update || false;
                const updateAvailable = data.update_available || false;
                
                let html = '';
                
                // Show persistent restart message if one exists
                if (pendingRestartMessage) {
                    html += '<div style="background: #fef3c7; padding: 16px; border-radius: 8px; border: 2px solid #f59e0b; margin-bottom: 24px;">';
                    html += '<p style="margin: 0; font-weight: 600; color: #92400e; font-size: 16px;">🔄 Restart Required</p>';
                    html += `<p style="margin: 8px 0 0 0; color: #78350f; font-size: 14px;">${pendingRestartMessage}</p>`;
                    html += '<p style="margin: 8px 0 0 0; color: #78350f; font-size: 13px;">The bot needs to be restarted to apply the latest updates. The restart message will disappear once you refresh the page after restarting.</p>';
                    html += '<button class="btn" onclick="pendingRestartMessage = null; loadUpdateStatus();" style="margin-top: 12px; padding: 6px 12px; font-size: 13px;">Dismiss</button>';
                    html += '</div>';
                }
                
                html += '<div class="config-section">';
                html += '<h3>Repository Information</h3>';
                
                if (!gitInfo.is_git_repo) {
                    html += '<div class="error">';
                    html += '<p><strong>Not a Git Repository</strong></p>';
                    html += `<p>${gitInfo.error || 'This installation is not a git repository. Updates are not available.'}</p>`;
                    html += '</div>';
                } else {
                    html += '<div class="form-group">';
                    html += `<label>Repository</label>`;
                    if (gitInfo.repo_owner && gitInfo.repo_name) {
                        html += `<p><strong>${gitInfo.repo_owner}/${gitInfo.repo_name}</strong></p>`;
                    } else if (gitInfo.remote_url) {
                        html += `<p><strong>${gitInfo.remote_url}</strong></p>`;
                    }
                    html += '</div>';
                    
                    html += '<div class="form-group">';
                    html += `<label>Branch</label>`;
                    html += `<p><strong>${gitInfo.branch || 'Unknown'}</strong></p>`;
                    html += '</div>';
                    
                    html += '<div class="form-group">';
                    html += `<label>Current Commit</label>`;
                    html += `<p><code>${gitInfo.current_commit || 'Unknown'}</code></p>`;
                    html += '</div>';
                    
                    if (gitInfo.remote_commit) {
                        html += '<div class="form-group">';
                        html += `<label>Remote Commit</label>`;
                        html += `<p><code>${gitInfo.remote_commit}</code></p>`;
                        html += '</div>';
                    }
                    
                    if (updateAvailable) {
                        html += '<div class="form-group" style="background: #fef3c7; padding: 16px; border-radius: 8px; border: 2px solid #f59e0b; margin: 20px 0;">';
                        html += '<p style="margin: 0; font-weight: 600; color: #92400e;">🔄 Update Available!</p>';
                        html += '<p style="margin: 8px 0 0 0; color: #78350f;">A new version is available from the remote repository.</p>';
                        html += '</div>';
                    } else {
                        html += '<div class="form-group" style="background: #d1fae5; padding: 16px; border-radius: 8px; border: 2px solid #10b981; margin: 20px 0;">';
                        html += '<p style="margin: 0; font-weight: 600; color: #065f46;">✅ Up to Date</p>';
                        html += '<p style="margin: 8px 0 0 0; color: #047857;">Your installation is up to date with the remote repository.</p>';
                        html += '</div>';
                    }
                    
                    html += '<div class="form-group" style="margin-top: 24px;">';
                    html += '<button class="btn btn-success" onclick="performUpdate(false)" style="margin-right: 12px;">🔄 Update Now</button>';
                    html += '<button class="btn" onclick="performUpdate(true)" style="margin-right: 12px;">🔍 Check for Updates</button>';
                    html += '<button class="btn btn-danger" onclick="performUpdate(false, true)" style="margin-right: 12px;">⚠️ Force Update (Reset)</button>';
                    html += '</div>';
                    
                    html += '<div class="form-group" style="margin-top: 16px;">';
                    html += '<small style="color: #6b7280;">';
                    html += '<strong>Update Now:</strong> Pulls latest changes from the remote repository.<br>';
                    html += '<strong>Check for Updates:</strong> Checks if updates are available without making changes.<br>';
                    html += '<strong>Force Update:</strong> Resets to remote version, discarding any local changes.';
                    html += '</small>';
                    html += '</div>';
                }
                
                html += '</div>';
                
                // Add auto-update settings section
                html += '<div class="config-section" style="margin-top: 32px;">';
                html += '<h3>⚙️ Auto-Update Settings</h3>';
                html += '<div id="auto-update-settings" class="loading">Loading auto-update settings...</div>';
                html += '</div>';
                
                // Add changelog section
                html += '<div class="config-section" style="margin-top: 32px;">';
                html += '<h3>📋 Recent Changelog</h3>';
                html += '<div id="changelog-content" class="loading">Loading changelog...</div>';
                html += '</div>';
                
                content.innerHTML = html;
                
                // Load auto-update settings and changelog
                loadAutoUpdateSettings();
                loadChangelog();
            } catch (error) {
                content.innerHTML = `<div class="error">Error loading update status: ${error.message}</div>`;
            }
        }
        
        async function performUpdate(dryRun = false, resetOnConflict = false) {
            const content = document.getElementById('update-content');
            const originalContent = content.innerHTML;
            
            try {
                content.innerHTML = '<div class="loading">Updating...</div>';
                
                const response = await fetch(`${API_BASE}/api/update`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        dry_run: dryRun,
                        reset_on_conflict: resetOnConflict
                    })
                });
                
                const data = await response.json();
                
                if (data.error) {
                    content.innerHTML = `<div class="error"><p><strong>Update Failed</strong></p><p>${data.error}</p></div>`;
                    if (data.message) {
                        content.innerHTML += `<p style="margin-top: 12px;">${data.message}</p>`;
                    }
                } else if (data.success) {
                    let html = '<div style="background: #d1fae5; padding: 16px; border-radius: 8px; border: 2px solid #10b981; margin: 20px 0;">';
                    html += '<p style="margin: 0; font-weight: 600; color: #065f46;">✅ Update Successful!</p>';
                    if (data.output && data.output.length > 0) {
                        html += '<ul style="margin: 8px 0 0 0; padding-left: 20px;">';
                        data.output.forEach(msg => {
                            html += `<li style="color: #047857;">${msg}</li>`;
                        });
                        html += '</ul>';
                    }
                    if (data.new_commit) {
                        html += `<p style="margin-top: 8px; color: #047857;">New commit: <code>${data.new_commit}</code></p>`;
                    }
                    if (data.restart_required) {
                        // Store restart message globally so it persists
                        pendingRestartMessage = data.restart_message || 'Please restart the bot to apply changes.';
                        html += '<div style="margin-top: 12px; padding: 12px; background: #fef3c7; border-radius: 6px; border: 1px solid #f59e0b;">';
                        html += '<p style="margin: 0; font-weight: 600; color: #92400e;">🔄 Restart Required</p>';
                        html += `<p style="margin: 8px 0 0 0; color: #78350f; font-size: 14px;">${pendingRestartMessage}</p>`;
                        html += '<p style="margin: 8px 0 0 0; color: #78350f; font-size: 13px;"><strong>This message will persist until you dismiss it or restart the bot.</strong></p>';
                        html += '</div>';
                    }
                    html += '</div>';
                    content.innerHTML = html;
                    
                    // Reload status after a moment (but keep restart message)
                    setTimeout(() => {
                        loadUpdateStatus();
                    }, 2000);
                } else {
                    content.innerHTML = `<div class="error"><p><strong>Update Failed</strong></p><p>${data.message || 'Unknown error'}</p></div>`;
                }
            } catch (error) {
                content.innerHTML = `<div class="error">Error performing update: ${error.message}</div>`;
            }
        }
        
        async function loadAutoUpdateSettings() {
            const content = document.getElementById('auto-update-settings');
            if (!content) return;
            
            try {
                // Get current settings
                const response = await fetch(`${API_BASE}/api/update-settings`, {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
                
                const data = await response.json();
                
                if (data.error) {
                    content.innerHTML = `<div class="error">Error loading settings: ${data.error}</div>`;
                    return;
                }
                
                const enabled = data.enabled || false;
                const interval = data.interval || 5;
                
                let html = '<div class="form-group">';
                html += '<label style="display: flex; align-items: center; cursor: pointer; margin-bottom: 16px;">';
                html += `<input type="checkbox" id="auto-update-enabled" ${enabled ? 'checked' : ''} style="width: 20px; height: 20px; margin-right: 10px;" onchange="updateAutoUpdateSettings()">`;
                html += '<span style="font-weight: 500; font-size: 16px;">Enable Auto-Update</span>';
                html += '</label>';
                html += '<small style="display: block; color: #6b7280; margin-top: 4px; margin-left: 30px;">Automatically check for and apply updates from the repository</small>';
                html += '</div>';
                
                html += '<div class="form-group" style="margin-top: 20px;">';
                html += '<label for="auto-update-interval">Update Check Interval (seconds)</label>';
                html += `<input type="number" id="auto-update-interval" value="${interval}" min="1" max="60" style="width: 100px; margin-top: 8px;" onchange="updateAutoUpdateSettings()">`;
                html += '<small style="display: block; color: #6b7280; margin-top: 4px;">How often to check for updates (1-60 seconds). Default: 5 seconds.</small>';
                html += '</div>';
                
                html += '<div class="form-group" style="margin-top: 16px; padding: 12px; background: #f3f4f6; border-radius: 6px;">';
                html += '<small style="color: #6b7280;">';
                html += '<strong>Note:</strong> Auto-update is disabled by default for safety. Enable it only if you trust the repository and want automatic updates.';
                html += '</small>';
                html += '</div>';
                
                content.innerHTML = html;
            } catch (error) {
                content.innerHTML = `<div class="error">Error loading auto-update settings: ${error.message}</div>`;
            }
        }
        
        async function updateAutoUpdateSettings() {
            const enabled = document.getElementById('auto-update-enabled').checked;
            const interval = parseInt(document.getElementById('auto-update-interval').value) || 5;
            
            // Clamp interval between 1 and 60
            const clampedInterval = Math.max(1, Math.min(60, interval));
            if (clampedInterval !== interval) {
                document.getElementById('auto-update-interval').value = clampedInterval;
            }
            
            try {
                const response = await fetch(`${API_BASE}/api/update-settings`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        enabled: enabled,
                        interval: clampedInterval
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    // Show success message briefly
                    const content = document.getElementById('auto-update-settings');
                    const successMsg = document.createElement('div');
                    successMsg.style.cssText = 'background: #d1fae5; color: #065f46; padding: 8px; border-radius: 4px; margin-bottom: 12px; font-size: 14px;';
                    successMsg.textContent = '✅ Settings saved';
                    content.insertBefore(successMsg, content.firstChild);
                    setTimeout(() => successMsg.remove(), 3000);
                } else {
                    alert(`Error saving settings: ${data.error || 'Unknown error'}`);
                }
            } catch (error) {
                alert(`Error saving settings: ${error.message}`);
            }
        }
        
        // Log Viewer Functions
        let logAutoScroll = true;
        let logRefreshInterval = null;
        let currentLogType = 'system';
        let currentLogLevel = 'all';
        let currentLogLines = 500;
        
        async function loadLogs() {
            const content = document.getElementById('logs-content');
            if (!content) return;
            
            // Check if controls already exist - if not, build them
            let logViewer = document.getElementById('log-viewer');
            if (!logViewer) {
                // Build controls HTML (only on first load)
                let html = '<div id="log-controls" style="margin-bottom: 20px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center;">';
                html += '<div class="form-group" style="margin: 0;">';
                html += '<label for="log-type" style="margin-right: 8px;">Log Type:</label>';
                html += `<select id="log-type" onchange="currentLogType = this.value; loadLogs();" style="padding: 6px 12px; border-radius: 6px; border: 1px solid #d1d5db;">`;
                html += `<option value="system" ${currentLogType === 'system' ? 'selected' : ''}>System Logs</option>`;
                html += `<option value="messages" ${currentLogType === 'messages' ? 'selected' : ''}>Message Logs</option>`;
                html += '</select>';
                html += '</div>';
                
                html += '<div class="form-group" style="margin: 0;">';
                html += '<label for="log-level" style="margin-right: 8px;">Level:</label>';
                html += `<select id="log-level" onchange="currentLogLevel = this.value; loadLogs();" style="padding: 6px 12px; border-radius: 6px; border: 1px solid #d1d5db;">`;
                html += '<option value="all">All Levels</option>';
                html += '<option value="DEBUG">DEBUG</option>';
                html += '<option value="INFO">INFO</option>';
                html += '<option value="WARNING">WARNING</option>';
                html += '<option value="ERROR">ERROR</option>';
                html += '<option value="CRITICAL">CRITICAL</option>';
                html += '</select>';
                html += '</div>';
                
                html += '<div class="form-group" style="margin: 0;">';
                html += '<label for="log-lines" style="margin-right: 8px;">Lines:</label>';
                html += `<input type="number" id="log-lines" value="${currentLogLines}" min="50" max="5000" step="50" onchange="currentLogLines = parseInt(this.value) || 500; loadLogs();" style="width: 100px; padding: 6px; border-radius: 6px; border: 1px solid #d1d5db;">`;
                html += '</div>';
                
                html += '<div class="form-group" style="margin: 0;">';
                html += `<label style="display: flex; align-items: center; cursor: pointer;"><input type="checkbox" id="log-autoscroll" ${logAutoScroll ? 'checked' : ''} onchange="logAutoScroll = this.checked;" style="margin-right: 6px;">Auto-scroll</label>`;
                html += '</div>';
                
                html += '<button class="btn" onclick="loadLogs()" style="padding: 6px 12px;">🔄 Refresh</button>';
                html += '<button class="btn" onclick="clearLogs()" style="padding: 6px 12px;">🗑️ Clear</button>';
                html += '</div>';
                
                html += '<div id="log-viewer" style="background: #1e293b; color: #e2e8f0; font-family: "Courier New", monospace; font-size: 13px; padding: 16px; border-radius: 8px; max-height: 600px; overflow-y: auto; white-space: pre-wrap; word-wrap: break-word; line-height: 1.5;">';
                html += '<div class="loading" style="color: #94a3b8;">Loading logs...</div>';
                html += '</div>';
                
                html += '<div id="log-count" style="margin-top: 12px; color: #94a3b8; font-size: 12px;"></div>';
                
                content.innerHTML = html;
                logViewer = document.getElementById('log-viewer');
            } else {
                // Just update the loading indicator
                logViewer.innerHTML = '<div class="loading" style="color: #94a3b8;">Loading logs...</div>';
            }
            
            // Update controls with current values
            const typeSelect = document.getElementById('log-type');
            const levelSelect = document.getElementById('log-level');
            const linesInput = document.getElementById('log-lines');
            const autoscrollCheck = document.getElementById('log-autoscroll');
            
            if (typeSelect) typeSelect.value = currentLogType;
            if (levelSelect) levelSelect.value = currentLogLevel;
            if (linesInput) linesInput.value = currentLogLines;
            if (autoscrollCheck) autoscrollCheck.checked = logAutoScroll;
            
            // Load log data
            try {
                const levelParam = currentLogLevel !== 'all' ? `&level=${currentLogLevel}` : '';
                const data = await fetchAPI(`logs?type=${currentLogType}&lines=${currentLogLines}${levelParam}`, 'GET', null, 15000);
                
                if (!logViewer) return;
                
                if (data.error) {
                    logViewer.innerHTML = `<div style="color: #f87171; padding: 20px; text-align: center;">
                        <strong>Error loading logs:</strong><br>
                        ${data.error}<br>
                        <button class="btn" onclick="loadLogs()" style="margin-top: 10px; padding: 6px 12px;">Retry</button>
                    </div>`;
                    return;
                }
                
                if (data.logs && data.logs.length > 0) {
                    let logHtml = '';
                    data.logs.forEach(log => {
                        // Color code by log level
                        let levelColor = '#94a3b8'; // default gray
                        if (log.level) {
                            const level = log.level.toUpperCase();
                            if (level === 'DEBUG') levelColor = '#60a5fa';
                            else if (level === 'INFO') levelColor = '#34d399';
                            else if (level === 'WARNING') levelColor = '#fbbf24';
                            else if (level === 'ERROR') levelColor = '#f87171';
                            else if (level === 'CRITICAL') levelColor = '#ef4444';
                        }
                        
                        logHtml += `<div style="margin-bottom: 4px; padding: 4px 0; border-bottom: 1px solid rgba(148, 163, 184, 0.1);">`;
                        if (log.timestamp) {
                            logHtml += `<span style="color: #64748b; margin-right: 12px;">${log.timestamp}</span>`;
                        }
                        if (log.level) {
                            logHtml += `<span style="color: ${levelColor}; font-weight: 600; margin-right: 12px; min-width: 80px; display: inline-block;">${log.level}</span>`;
                        }
                        logHtml += `<span style="color: #e2e8f0;">${log.message}</span>`;
                        logHtml += `</div>`;
                    });
                    
                    logViewer.innerHTML = logHtml;
                    
                    // Auto-scroll to bottom if enabled
                    if (logAutoScroll) {
                        setTimeout(() => {
                            if (logViewer) {
                                logViewer.scrollTop = logViewer.scrollHeight;
                            }
                        }, 100);
                    }
                } else {
                    logViewer.innerHTML = '<div style="color: #94a3b8; text-align: center; padding: 40px;">No log entries found</div>';
                }
                
                // Update log count display (replace, don't append)
                const logCount = document.getElementById('log-count');
                if (logCount) {
                    logCount.textContent = `Showing ${data.count} of ${data.total_lines || 0} lines from ${data.log_file || 'log file'}`;
                }
                
            } catch (error) {
                if (logViewer) {
                    logViewer.innerHTML = `<div style="color: #f87171;">Error loading logs: ${error.message}</div>`;
                }
            }
        }
        
        function clearLogs() {
            const logViewer = document.getElementById('log-viewer');
            if (logViewer) {
                logViewer.innerHTML = '<div style="color: #94a3b8; text-align: center; padding: 40px;">Logs cleared</div>';
            }
        }
        
        async function loadChangelog() {
            const content = document.getElementById('changelog-content');
            if (!content) return;
            
            try {
                const data = await fetchAPI('update/changelog?limit=20');
                if (data.error) {
                    content.innerHTML = `<div class="error">Error loading changelog: ${data.error}</div>`;
                    return;
                }
                
                if (data.commits && data.commits.length > 0) {
                    let html = '<div style="max-height: 400px; overflow-y: auto; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px;">';
                    data.commits.forEach(commit => {
                        html += '<div style="padding: 12px; border-bottom: 1px solid #e5e7eb; margin-bottom: 8px;">';
                        html += `<div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 4px;">`;
                        html += `<code style="background: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-size: 12px;">${commit.hash}</code>`;
                        html += `<span style="color: #6b7280; font-size: 12px;">${commit.date}</span>`;
                        html += `</div>`;
                        html += `<p style="margin: 4px 0; font-weight: 500; color: #1f2937;">${commit.message}</p>`;
                        html += `<p style="margin: 0; color: #6b7280; font-size: 12px;">by ${commit.author}</p>`;
                        html += '</div>';
                    });
                    html += '</div>';
                    content.innerHTML = html;
                } else {
                    content.innerHTML = '<div style="color: #6b7280; padding: 20px; text-align: center;">No commits found</div>';
                }
            } catch (error) {
                content.innerHTML = `<div class="error">Error loading changelog: ${error.message}</div>`;
            }
        }
        
        function toggleConfigSection(sectionId) {
            const section = document.getElementById(sectionId);
            if (section) {
                section.classList.toggle('collapsed');
            }
        }
        
        function updateConfigValue(section, key, value) {
            if (!configData[section]) configData[section] = {};
            // Convert boolean to string format expected by config
            if (typeof value === 'boolean') {
                configData[section][key] = value ? 'True' : 'False';
                // Update checkbox label
                const checkbox = document.getElementById(`${section}_${key}`);
                if (checkbox) {
                    const label = checkbox.closest('label');
                    if (label) {
                        const span = label.querySelector('span');
                        if (span) span.textContent = value ? 'Enabled' : 'Disabled';
                    }
                }
            } else {
                configData[section][key] = value;
            }
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
            const activeTabElement = document.querySelector('.tab-content.active');
            if (!activeTabElement) {
                console.warn('No active tab found');
                return;
            }
            
            const activeTab = activeTabElement.id;
            
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
                    default:
                        // Tab has its own loader, don't refresh
                        break;
                }
            } catch (error) {
                console.error('Error refreshing data:', error);
                const content = activeTabElement.querySelector('[id$="-content"]');
                if (content) {
                    content.innerHTML = `<div class="error">Error loading data: ${error.message}</div>`;
                }
            }
        }
        
        async function loadDashboard() {
            const content = document.getElementById('dashboard-content');
            if (!content) {
                console.error('Dashboard content element not found');
                return;
            }
            
            try {
                const data = await fetchAPI('dashboard');
                
                if (data.error) {
                    content.innerHTML = `<div class="error">Error: ${data.error}<br><small>Check browser console (F12) for details</small></div>`;
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
            } catch (error) {
                console.error('Error loading dashboard:', error);
                content.innerHTML = `<div class="error">Error loading dashboard: ${error.message}<br><small>Check browser console (F12) for details</small></div>`;
            }
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
                // Only reinitialize if map doesn't exist
                if (!map) {
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
                        mapInitialized = true; // Map is now initialized
                        mapBoundsFitted = false; // Bounds not yet fitted (will fit on first load)
                        loadMapNodes();
                    } catch (e) {
                        console.error('Error initializing map:', e);
                        document.getElementById('map-container').innerHTML = 
                            '<div style="padding: 40px; text-align: center; color: #6b7280;"><h3>Map Error</h3><p>Could not initialize map. Please refresh the page.</p></div>';
                    }
                } else {
                    // Map already exists, just update nodes without resetting view
                    loadMapNodes();
                }
            }, 100);
        }
        
        let positionTrails = {}; // Store position history for trails
        
        async function loadMapNodes() {
            if (!map) return;
            
            const data = await fetchAPI('map');
            
            if (data.error || !data.nodes) {
                console.error('Error loading nodes for map:', data.error);
                return;
            }
            
            // Clear existing markers and trails
            mapMarkers.forEach(marker => map.removeLayer(marker));
            mapMarkers = [];
            
            // Clear existing trails
            Object.values(positionTrails).forEach(trail => {
                if (trail && map.hasLayer(trail)) {
                    map.removeLayer(trail);
                }
            });
            positionTrails = {};
            
            let hasPositions = false;
            const bounds = [];
            
            // Process position metadata for trails (if available in future)
            const nodePositions = {};
            if (data.position && !data.position.error && data.position.nodes) {
                for (const nodeId in data.position.nodes) {
                    const posData = data.position.nodes[nodeId];
                    // If position history is stored, it would be here
                    if (posData.positions && Array.isArray(posData.positions)) {
                        nodePositions[nodeId] = posData.positions;
                    }
                }
            }
            
            for (const key in data.nodes) {
                if (data.nodes[key].nodes) {
                    data.nodes[key].nodes.forEach(node => {
                        if (node.position && node.position.latitude && node.position.longitude) {
                            hasPositions = true;
                            const lat = node.position.latitude;
                            const lng = node.position.longitude;
                            const name = node.shortName || node.longName || `Node ${node.nodeId}`;
                            const nodeId = node.nodeIdHex || node.nodeId;
                            
                            // Draw position trail if available
                            if (nodePositions[nodeId] && nodePositions[nodeId].length > 1) {
                                const trailCoords = nodePositions[nodeId]
                                    .filter(p => p.latitude && p.longitude)
                                    .map(p => [p.latitude, p.longitude]);
                                
                                if (trailCoords.length > 1) {
                                    const trail = L.polyline(trailCoords, {
                                        color: node.isLocal ? '#10b981' : '#3b82f6',
                                        weight: 2,
                                        opacity: 0.6
                                    }).addTo(map);
                                    positionTrails[nodeId] = trail;
                                }
                            }
                            
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
                                ${node.position.altitude ? `Altitude: ${node.position.altitude}m<br>` : ''}
                                ${node.isLocal ? '<span style="color: green;">Local Node</span>' : ''}
                                ${nodePositions[nodeId] && nodePositions[nodeId].length > 1 ? `<br><small>Trail: ${nodePositions[nodeId].length} positions</small>` : ''}
                            `)
                            .addTo(map);
                            
                            mapMarkers.push(marker);
                            bounds.push([lat, lng]);
                        }
                    });
                }
            }
            
            // Only fit bounds on first load, preserve zoom/center on subsequent updates
            if (hasPositions && bounds.length > 0) {
                if (!mapBoundsFitted) {
                    // First load - fit bounds to show all nodes
                    try {
                        map.fitBounds(bounds, { padding: [20, 20] });
                        mapBoundsFitted = true; // Mark that we've fitted bounds once
                    } catch (e) {
                        console.error('Error fitting bounds:', e);
                        mapBoundsFitted = true; // Mark as fitted even on error to prevent retries
                    }
                }
                // On subsequent updates, don't change the view - just update markers
            } else {
                // Show message if no positions
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
        
        // Activity Feed Functions
        async function loadActivity() {
            const content = document.getElementById('activity-content');
            const data = await fetchAPI('activity');
            
            if (data.error) {
                content.innerHTML = `<div class="error">Error: ${data.error}</div>`;
                return;
            }
            
            let html = '';
            if (data.messages && data.messages.length > 0) {
                html = '<div style="max-height: 600px; overflow-y: auto;">';
                data.messages.forEach(msg => {
                    html += `
                        <div class="bbs-message" style="margin-bottom: 12px;">
                            <div class="bbs-message-header">
                                <span><strong>${msg.fromName || 'Unknown'}</strong></span>
                                <span>Ch ${msg.channel} | Int ${msg.interface} | ${msg.timestamp || ''}</span>
                            </div>
                            <div class="bbs-message-body">${msg.message || ''}</div>
                        </div>
                    `;
                });
                html += '</div>';
            } else {
                html = '<p>No recent activity</p>';
            }
            
            content.innerHTML = html;
        }
        
        function filterActivity() {
            const filter = document.getElementById('activity-filter').value.toLowerCase();
            const messages = document.querySelectorAll('#activity-content .bbs-message');
            messages.forEach(msg => {
                const text = msg.textContent.toLowerCase();
                msg.style.display = text.includes(filter) ? 'block' : 'none';
            });
        }
        
        // Node Details Functions
        async function loadNodeDetails() {
            const nodeId = document.getElementById('node-search').value.trim();
            if (!nodeId) {
                document.getElementById('node-details-content').innerHTML = '<div class="error">Please enter a Node ID</div>';
                return;
            }
            
            const content = document.getElementById('node-details-content');
            content.innerHTML = '<div class="loading">Loading node details...</div>';
            
            const data = await fetchAPI(`node/${nodeId}`);
            
            if (data.error) {
                content.innerHTML = `<div class="error">Error: ${data.error}</div>`;
                return;
            }
            
            let html = '<div class="grid">';
            html += `
                <div class="card">
                    <h3>Basic Information</h3>
                    <div class="stat">
                        <span>Node ID</span>
                        <span><strong>${data.nodeIdHex || data.nodeId}</strong></span>
                    </div>
                    <div class="stat">
                        <span>Short Name</span>
                        <span><strong>${data.shortName || 'N/A'}</strong></span>
                    </div>
                    <div class="stat">
                        <span>Long Name</span>
                        <span><strong>${data.longName || 'N/A'}</strong></span>
                    </div>
                    <div class="stat">
                        <span>Interface</span>
                        <span><strong>${data.interface || 'N/A'}</strong></span>
                    </div>
                    <div class="stat">
                        <span>Status</span>
                        <span><strong>${data.isLocal ? '<span class="badge success">Local Node</span>' : '<span class="badge info">Remote</span>'}</strong></span>
                    </div>
                </div>
            `;
            
            if (data.position) {
                html += `
                    <div class="card">
                        <h3>Position</h3>
                        <div class="stat">
                            <span>Latitude</span>
                            <span><strong>${data.position.latitude || 'N/A'}</strong></span>
                        </div>
                        <div class="stat">
                            <span>Longitude</span>
                            <span><strong>${data.position.longitude || 'N/A'}</strong></span>
                        </div>
                        <div class="stat">
                            <span>Altitude</span>
                            <span><strong>${data.position.altitude || 0}m</strong></span>
                        </div>
                    </div>
                `;
            }
            
            if (data.deviceMetrics) {
                html += `
                    <div class="card">
                        <h3>Device Metrics</h3>
                        <div class="stat">
                            <span>Battery</span>
                            <span><strong>${data.deviceMetrics.batteryLevel !== undefined ? data.deviceMetrics.batteryLevel + '%' : 'N/A'}</strong></span>
                        </div>
                        <div class="stat">
                            <span>Voltage</span>
                            <span><strong>${data.deviceMetrics.voltage || 'N/A'}V</strong></span>
                        </div>
                        <div class="stat">
                            <span>Uptime</span>
                            <span><strong>${data.deviceMetrics.uptimeSeconds ? formatUptime(data.deviceMetrics.uptimeSeconds) : 'N/A'}</strong></span>
                        </div>
                        <div class="stat">
                            <span>Channel Util</span>
                            <span><strong>${data.deviceMetrics.channelUtilization || 0}%</strong></span>
                        </div>
                    </div>
                `;
            }
            
            html += `
                <div class="card">
                    <h3>RF Statistics</h3>
                    <div class="stat">
                        <span>SNR</span>
                        <span><strong>${data.snr || 'N/A'}</strong></span>
                    </div>
                    <div class="stat">
                        <span>RSSI</span>
                        <span><strong>${data.rssi || 'N/A'}</strong></span>
                    </div>
                    <div class="stat">
                        <span>Last Heard</span>
                        <span><strong>${data.lastHeard ? new Date(data.lastHeard * 1000).toLocaleString() : 'Never'}</strong></span>
                    </div>
                    <div class="stat">
                        <span>Messages</span>
                        <span><strong>${data.messageCount || 0}</strong></span>
                    </div>
                </div>
            `;
            
            html += '</div>';
            content.innerHTML = html;
        }
        
        function formatUptime(seconds) {
            if (seconds < 60) return `${seconds}s`;
            if (seconds < 3600) return `${Math.floor(seconds/60)}m`;
            if (seconds < 86400) return `${Math.floor(seconds/3600)}h`;
            return `${Math.floor(seconds/86400)}d`;
        }
        
        // Statistics Functions
        async function loadStatistics() {
            const content = document.getElementById('statistics-content');
            const timeframe = document.getElementById('stat-timeframe').value;
            
            // Get current telemetry data
            const telData = await fetchAPI('telemetry');
            const nodeData = await fetchAPI('nodes');
            
            if (telData.error || nodeData.error) {
                content.innerHTML = `<div class="error">Error loading statistics</div>`;
                return;
            }
            
            let html = '<div style="margin-bottom: 30px;">';
            
            // Create charts container
            html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;">';
            html += '<div><canvas id="packetsChart"></canvas></div>';
            html += '<div><canvas id="nodesChart"></canvas></div>';
            html += '</div>';
            
            // Summary stats
            html += '<div class="grid">';
            let totalTx = 0, totalRx = 0, totalNodes = 0;
            for (const key in telData) {
                if (key.startsWith('interface_')) {
                    totalTx += telData[key].numPacketsTx || 0;
                    totalRx += telData[key].numPacketsRx || 0;
                }
            }
            for (const key in nodeData) {
                if (nodeData[key].nodeCount !== undefined) {
                    totalNodes += nodeData[key].nodeCount;
                }
            }
            
            html += `
                <div class="card">
                    <h3>Summary</h3>
                    <div class="stat">
                        <span>Total Packets TX</span>
                        <span><strong>${totalTx.toLocaleString()}</strong></span>
                    </div>
                    <div class="stat">
                        <span>Total Packets RX</span>
                        <span><strong>${totalRx.toLocaleString()}</strong></span>
                    </div>
                    <div class="stat">
                        <span>Total Nodes</span>
                        <span><strong>${totalNodes}</strong></span>
                    </div>
                </div>
            `;
            html += '</div>';
            html += '</div>';
            
            content.innerHTML = html;
            
            // Create charts (simplified - using current data)
            setTimeout(() => {
                if (typeof Chart !== 'undefined') {
                    // Packets chart
                    const packetsCtx = document.getElementById('packetsChart');
                    if (packetsCtx) {
                        new Chart(packetsCtx, {
                            type: 'bar',
                            data: {
                                labels: ['TX', 'RX'],
                                datasets: [{
                                    label: 'Packets',
                                    data: [totalTx, totalRx],
                                    backgroundColor: ['#667eea', '#10b981']
                                }]
                            },
                            options: {
                                responsive: true,
                                plugins: {
                                    title: { display: true, text: 'Packet Statistics' }
                                }
                            }
                        });
                    }
                    
                    // Nodes chart
                    const nodesCtx = document.getElementById('nodesChart');
                    if (nodesCtx) {
                        const interfaceCounts = [];
                        const interfaceLabels = [];
                        for (const key in nodeData) {
                            if (nodeData[key].interfaceNumber) {
                                interfaceLabels.push(`Int ${nodeData[key].interfaceNumber}`);
                                interfaceCounts.push(nodeData[key].nodeCount || 0);
                            }
                        }
                        new Chart(nodesCtx, {
                            type: 'doughnut',
                            data: {
                                labels: interfaceLabels,
                                datasets: [{
                                    data: interfaceCounts,
                                    backgroundColor: ['#667eea', '#10b981', '#f59e0b', '#ef4444', '#3b82f6']
                                }]
                            },
                            options: {
                                responsive: true,
                                plugins: {
                                    title: { display: true, text: 'Nodes per Interface' }
                                }
                            }
                        });
                    }
                }
            }, 100);
        }
        
        // Network Graph Functions
        async function loadNetworkGraph() {
            const content = document.getElementById('network-content');
            const data = await fetchAPI('nodes');
            
            if (data.error) {
                content.innerHTML = `<div class="error">Error: ${data.error}</div>`;
                return;
            }
            
            let html = '<div class="grid">';
            
            // Build network connections (simplified visualization)
            for (const key in data) {
                if (data[key].interfaceNumber) {
                    const intf = data[key];
                    html += `
                        <div class="card">
                            <h3>Interface ${intf.interfaceNumber} Network</h3>
                            <div style="margin-top: 15px;">
                                <strong>Nodes: ${intf.nodeCount}</strong>
                                <div style="margin-top: 10px; display: flex; flex-wrap: wrap; gap: 8px;">
                    `;
                    
                    intf.nodes.forEach(node => {
                        const nodeName = node.shortName || node.longName || `Node ${node.nodeId}`;
                        html += `
                            <div style="padding: 8px; background: ${node.isLocal ? '#10b981' : '#3b82f6'}; color: white; border-radius: 6px; font-size: 12px;">
                                ${nodeName}
                            </div>
                        `;
                    });
                    
                    html += `
                                </div>
                            </div>
                        </div>
                    `;
                }
            }
            
            html += '</div>';
            content.innerHTML = html;
        }
        
        // System Health Functions
        async function loadHealth() {
            const content = document.getElementById('health-content');
            const data = await fetchAPI('health');
            
            if (data.error) {
                content.innerHTML = `<div class="error">Error: ${data.error}</div>`;
                return;
            }
            
            let html = '<div class="grid">';
            
            html += `
                <div class="card">
                    <h3>System Status</h3>
                    <div class="stat">
                        <span>Uptime</span>
                        <span><strong>${data.uptimeFormatted || 'Unknown'}</strong></span>
                    </div>
                    <div class="stat">
                        <span>Memory Usage</span>
                        <span><strong>${data.memory ? data.memory.used.toFixed(1) + ' MB (' + data.memory.percent.toFixed(1) + '%)' : 'N/A'}</strong></span>
                    </div>
                    <div class="stat">
                        <span>CPU Usage</span>
                        <span><strong>${data.cpu ? data.cpu.percent.toFixed(1) + '%' : 'N/A'}</strong></span>
                    </div>
                </div>
            `;
            
            if (data.interfaces && data.interfaces.length > 0) {
                html += '<div class="card"><h3>Interface Status</h3>';
                data.interfaces.forEach(intf => {
                    const statusColor = intf.status === 'connected' ? 'success' : 'danger';
                    html += `
                        <div class="stat">
                            <span>Interface ${intf.number}</span>
                            <span><strong><span class="badge ${statusColor}">${intf.status}</span></strong></span>
                        </div>
                    `;
                });
                html += '</div>';
            }
            
            html += '</div>';
            content.innerHTML = html;
        }
        
        // Alerts Functions
        async function loadAlerts() {
            const content = document.getElementById('alerts-content');
            // For now, show a placeholder - alerts would need to be tracked
            content.innerHTML = `
                <div class="card">
                    <h3>Recent Alerts</h3>
                    <p style="color: #6b7280;">Alert tracking coming soon. This will show FEMA alerts, weather warnings, system errors, and other notifications.</p>
                </div>
            `;
        }
        
        // Management Functions
        async function loadManagement() {
            const content = document.getElementById('management-content');
            const data = await fetchAPI('management');
            
            if (data.error) {
                content.innerHTML = `<div class="error">Error: ${data.error}</div>`;
                return;
            }
            
            let html = '<div class="grid">';
            
            html += `
                <div class="card">
                    <h3>Banned Nodes</h3>
                    <div style="margin-top: 10px;">
                        ${data.bannedNodes && data.bannedNodes.length > 0 ? 
                            data.bannedNodes.map(n => `<div class="badge danger" style="margin: 4px;">${n}</div>`).join('') : 
                            '<p style="color: #6b7280;">No banned nodes</p>'}
                    </div>
                </div>
            `;
            
            html += `
                <div class="card">
                    <h3>Admin Nodes</h3>
                    <div style="margin-top: 10px;">
                        ${data.adminNodes && data.adminNodes.length > 0 ? 
                            data.adminNodes.map(n => `<div class="badge success" style="margin: 4px;">${n}</div>`).join('') : 
                            '<p style="color: #6b7280;">No admin nodes configured</p>'}
                    </div>
                </div>
            `;
            
            html += `
                <div class="card">
                    <h3>Auto-Banned Nodes</h3>
                    <div style="margin-top: 10px;">
                        ${data.autoBanned && data.autoBanned.length > 0 ? 
                            data.autoBanned.map(n => `<div class="badge warning" style="margin: 4px;">${n}</div>`).join('') : 
                            '<p style="color: #6b7280;">No auto-banned nodes</p>'}
                    </div>
                </div>
            `;
            
            html += '</div>';
            content.innerHTML = html;
        }
        
        // Message Composer Functions
        function updateComposerType() {
            const type = document.getElementById('composer-type').value;
            document.getElementById('composer-channel-group').style.display = type === 'channel' ? 'block' : 'none';
            document.getElementById('composer-node-group').style.display = type === 'node' ? 'block' : 'none';
        }
        
        async function sendMessage() {
            const message = document.getElementById('composer-message').value.trim();
            const type = document.getElementById('composer-type').value;
            const interface = parseInt(document.getElementById('composer-interface').value);
            const resultDiv = document.getElementById('composer-result');
            
            if (!message) {
                resultDiv.innerHTML = '<div class="error">Please enter a message</div>';
                return;
            }
            
            let channel = 0;
            let node_id = 0;
            
            if (type === 'channel') {
                channel = parseInt(document.getElementById('composer-channel').value) || 0;
            } else {
                const nodeInput = document.getElementById('composer-node').value.trim();
                if (!nodeInput) {
                    resultDiv.innerHTML = '<div class="error">Please enter a Node ID</div>';
                    return;
                }
                // Convert hex to decimal if needed
                if (nodeInput.startsWith('!')) {
                    node_id = parseInt(nodeInput.substring(1), 16);
                } else {
                    node_id = parseInt(nodeInput);
                }
                if (isNaN(node_id)) {
                    resultDiv.innerHTML = '<div class="error">Invalid Node ID format</div>';
                    return;
                }
            }
            
            resultDiv.innerHTML = '<div class="loading">Sending message...</div>';
            
            const result = await fetchAPI('send', 'POST', {
                message: message,
                channel: channel,
                node_id: node_id,
                interface: interface
            });
            
            if (result.success) {
                resultDiv.innerHTML = '<div class="success">Message sent successfully!</div>';
                document.getElementById('composer-message').value = '';
            } else {
                resultDiv.innerHTML = `<div class="error">Error: ${result.error || 'Failed to send message'}</div>`;
            }
        }
        
        // Export Functions
        function exportData(type) {
            fetchAPI(`export/${type}`).then(data => {
                const jsonStr = JSON.stringify(data, null, 2);
                const blob = new Blob([jsonStr], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `mesh_${type}_${new Date().toISOString().split('T')[0]}.json`;
                a.click();
                URL.revokeObjectURL(url);
            });
        }
        
        // Auto-refresh dashboard every 10 seconds
        function startAutoRefresh() {
            stopAutoRefresh();
            autoRefreshInterval = setInterval(() => {
                const activeTab = document.querySelector('.tab-content.active').id;
                if (activeTab === 'config' || activeTab === 'composer' || activeTab === 'node-details') {
                    // Don't auto-refresh these tabs
                } else if (activeTab === 'map') {
                    loadMapNodes();
                } else if (activeTab === 'bbs') {
                    loadBBS();
                } else if (activeTab === 'activity') {
                    loadActivity();
                } else if (activeTab === 'health') {
                    loadHealth();
                } else if (activeTab === 'management') {
                    loadManagement();
                } else if (activeTab === 'statistics') {
                    loadStatistics();
                } else if (activeTab === 'logs') {
                    // Only update log content, don't rebuild controls
                    const logViewer = document.getElementById('log-viewer');
                    if (logViewer) {
                        // Only refresh if not currently loading
                        if (!logViewer.querySelector('.loading')) {
                            loadLogs().catch(err => {
                                console.error('Error in loadLogs:', err);
                                if (logViewer) {
                                    logViewer.innerHTML = `<div style="color: #f87171; padding: 20px; text-align: center;">
                                        <strong>Error:</strong> ${err.message}<br>
                                        <button class="btn" onclick="loadLogs()" style="margin-top: 10px; padding: 6px 12px;">Retry</button>
                                    </div>`;
                                }
                            });
                        }
                    }
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


def free_locked_tcp_port(port: int, auto_kill: bool = True):
    """
    Attempt to free a locked TCP port by identifying and killing the process using it.
    
    Args:
        port: TCP port number
        auto_kill: If True, attempt to kill the process automatically
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    if not auto_kill:
        return False, "Auto-kill disabled"
    
    try:
        # First, try to find and kill any existing Web UI server threads/processes
        # Check for processes listening on the port
        pids_to_kill = []
        
        # Method 1: Use lsof to find process using the port
        try:
            lsof_result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if lsof_result.returncode == 0 and lsof_result.stdout.strip():
                pids_to_kill.extend([int(pid.strip()) for pid in lsof_result.stdout.strip().split('\n') if pid.strip().isdigit()])
        except:
            pass
        
        # Method 2: Use fuser as fallback
        if not pids_to_kill:
            try:
                fuser_result = subprocess.run(
                    ["fuser", f"{port}/tcp"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if fuser_result.returncode == 0:
                    pids = re.findall(r'\d+', fuser_result.stdout)
                    pids_to_kill.extend([int(pid) for pid in pids if pid.isdigit()])
            except:
                pass
        
        # Method 3: Use netstat/ss as last resort
        if not pids_to_kill:
            try:
                # Try ss first (modern Linux)
                ss_result = subprocess.run(
                    ["ss", "-tlnp"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if ss_result.returncode == 0:
                    for line in ss_result.stdout.split('\n'):
                        if f':{port} ' in line and 'LISTEN' in line:
                            # Extract PID from line like "users:(("python",pid=1234,fd=3))"
                            pid_match = re.search(r'pid=(\d+)', line)
                            if pid_match:
                                pids_to_kill.append(int(pid_match.group(1)))
            except:
                pass
        
        # Remove duplicates
        pids_to_kill = list(set(pids_to_kill))
        
        if not pids_to_kill:
            return False, "No process found using the port"
        
        killed_any = False
        messages = []
        
        for pid in pids_to_kill:
            try:
                # Get process details
                ps_result = subprocess.run(
                    ["ps", "-p", str(pid), "-o", "comm=,args="],
                    capture_output=True,
                    text=True,
                    timeout=3
                )
                
                if ps_result.returncode != 0:
                    # Process might have already died
                    continue
                
                proc_info = ps_result.stdout.strip()
                proc_name = proc_info.split()[0].lower() if proc_info else "unknown"
                proc_args = proc_info if len(proc_info.split()) > 1 else ""
                
                # Check if it's a Python/meshtastic process
                is_python = 'python' in proc_name or 'python3' in proc_name
                is_mesh = any(keyword in proc_args.lower() for keyword in ['mesh', 'meshtastic', 'web_ui', '8420'])
                
                # Kill if it's Python and related to mesh/web_ui, or if it's definitely our process
                if is_python and (is_mesh or 'web_ui' in proc_args.lower() or 'mesh_bot' in proc_args.lower()):
                    # Try kill without sudo first
                    kill_result = subprocess.run(
                        ["kill", "-9", str(pid)],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    
                    if kill_result.returncode == 0:
                        time.sleep(1)  # Wait longer for port to be released
                        killed_any = True
                        messages.append(f"Killed process {pid} ({proc_name})")
                    else:
                        # Try with sudo
                        sudo_kill = subprocess.run(
                            ["sudo", "kill", "-9", str(pid)],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if sudo_kill.returncode == 0:
                            time.sleep(1)
                            killed_any = True
                            messages.append(f"Killed process {pid} ({proc_name}) with sudo")
                        else:
                            messages.append(f"Failed to kill process {pid}: {sudo_kill.stderr.strip()}")
                else:
                    messages.append(f"Port locked by {proc_name} (PID {pid}) - not a mesh/web_ui process, skipping")
            except (ValueError, subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
                continue
        
        if killed_any:
            # Wait a bit more to ensure port is fully released
            time.sleep(1)
            return True, "; ".join(messages)
        else:
            return False, "; ".join(messages) if messages else "No safe processes to kill"
        
    except FileNotFoundError:
        return False, "lsof/fuser/ss not available - cannot auto-free port"
    except subprocess.TimeoutExpired:
        return False, "Timeout checking port status"
    except Exception as e:
        return False, f"Error freeing port: {str(e)}"


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
    # Try to start server with automatic port recovery
    max_retries = 3
    retry_delay = 2
    server = None
    
    for attempt in range(max_retries):
        try:
            server = socketserver.TCPServer((host, port), WebUIRequestHandler)
            server.allow_reuse_address = True
            break  # Success, exit retry loop
        except OSError as e:
            if "Address already in use" in str(e) or "errno 98" in str(e).lower():
                if attempt < max_retries - 1:
                    # Try to automatically free the port
                    try:
                        from modules.settings import auto_kill_port_lock
                    except:
                        auto_kill_port_lock = True  # Default to enabled
                    
                    if auto_kill_port_lock:
                        freed, message = free_locked_tcp_port(port, auto_kill_port_lock)
                        if freed:
                            print(f"Web UI: {message}")
                            time.sleep(2)  # Wait longer for port to be fully released
                            continue  # Retry immediately
                        else:
                            print(f"Web UI: Port {port} is in use. {message}")
                            # Try one more time with a longer wait
                            if attempt < max_retries - 1:
                                print(f"Web UI: Waiting {retry_delay}s before retry (attempt {attempt + 1}/{max_retries})...")
                                time.sleep(retry_delay)
                                retry_delay += 1
                                # Try to free the port again
                                freed, message = free_locked_tcp_port(port, auto_kill_port_lock)
                                if freed:
                                    print(f"Web UI: Port freed on retry: {message}")
                                    time.sleep(2)
                                    continue
                    else:
                        print(f"Web UI: Port {port} is in use. Auto-kill disabled.")
                        print(f"Web UI: Waiting {retry_delay}s before retry (attempt {attempt + 1}/{max_retries})...")
                        time.sleep(retry_delay)
                        retry_delay += 1
                else:
                    # Final attempt failed - provide helpful error message
                    import subprocess
                    try:
                        # Try to identify what's using the port
                        lsof_result = subprocess.run(
                            ["lsof", "-i", f":{port}"],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        port_info = lsof_result.stdout if lsof_result.returncode == 0 else "Unable to identify process"
                    except:
                        port_info = "Unable to identify process (lsof not available)"
                    
                    error_msg = (
                        f"Failed to start Web UI on port {port} after {max_retries} attempts.\n"
                        f"Port is in use. To fix this:\n"
                        f"1. Check what's using the port: sudo lsof -i :{port} or sudo fuser {port}/tcp\n"
                        f"2. Kill the process: sudo kill -9 <PID> (replace <PID> with the process ID)\n"
                        f"3. Or disable auto-kill and manually free the port\n"
                        f"Current port status:\n{port_info}"
                    )
                    raise Exception(error_msg)
            else:
                # Different error, re-raise it
                raise
        except Exception as e:
            # Any other exception during server creation
            raise Exception(f"Failed to start Web UI server: {str(e)}")
    
    # Ensure server was created successfully
    if server is None:
        raise Exception(f"Failed to create Web UI server on {host}:{port}")
    
    if background:
        # Store server reference globally to prevent garbage collection
        if not hasattr(start_web_ui, '_server_instances'):
            start_web_ui._server_instances = []
        start_web_ui._server_instances.append(server)
        
        def run_server():
            """Run server with error handling to prevent silent crashes."""
            import sys
            try:
                print(f"Web UI: Server thread starting on {host}:{port}", file=sys.stderr)
                server.serve_forever()
            except KeyboardInterrupt:
                print(f"Web UI: Server interrupted", file=sys.stderr)
            except Exception as e:
                print(f"Web UI: Server crashed: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)
            finally:
                # Ensure server socket is properly closed
                try:
                    server.shutdown()
                    server.server_close()
                    print(f"Web UI: Server socket closed", file=sys.stderr)
                except:
                    pass
                print(f"Web UI: Server thread exiting", file=sys.stderr)
        
        server_thread = threading.Thread(target=run_server, daemon=True, name=f"WebUI-{port}")
        server_thread.start()
        
        # Give the thread a moment to start and verify it's alive
        time.sleep(0.1)
        if server_thread.is_alive():
            print(f"Web UI started in background at http://{host}:{port}")
        else:
            # Clean up server if thread died
            try:
                server.shutdown()
                server.server_close()
            except:
                pass
            raise Exception(f"Web UI server thread died immediately after start")
        
        # Store thread reference
        if not hasattr(start_web_ui, '_server_threads'):
            start_web_ui._server_threads = []
        start_web_ui._server_threads.append(server_thread)
        
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


