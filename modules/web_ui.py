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
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length) if content_length > 0 else b'{}'
                request_data = json.loads(post_data.decode('utf-8')) if post_data else {}
                
                if path_parts[1] == 'config':
                    # Save configuration
                    response = write_config(request_data.get('config', {}))
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
            <button class="tab" onclick="showTab('activity')">📨 Activity</button>
            <button class="tab" onclick="showTab('map')">🗺️ Node Map</button>
            <button class="tab" onclick="showTab('nodes')">📡 Nodes</button>
            <button class="tab" onclick="showTab('node-details')">🔍 Node Details</button>
            <button class="tab" onclick="showTab('telemetry')">📈 RF Telemetry</button>
            <button class="tab" onclick="showTab('statistics')">📊 Statistics</button>
            <button class="tab" onclick="showTab('network')">🌐 Network</button>
            <button class="tab" onclick="showTab('health')">💚 Health</button>
            <button class="tab" onclick="showTab('alerts')">🚨 Alerts</button>
            <button class="tab" onclick="showTab('bbs')">💬 BBS</button>
            <button class="tab" onclick="showTab('composer')">✉️ Send</button>
            <button class="tab" onclick="showTab('management')">👥 Management</button>
            <button class="tab" onclick="showTab('leaderboard')">🏆 Leaderboard</button>
            <button class="tab" onclick="showTab('config')">⚙️ Config</button>
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
            
            // Load appropriate data for each tab
            if (tabName === 'config') {
                loadConfig();
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
            
            if (hasPositions && bounds.length > 0) {
                try {
                    map.fitBounds(bounds, { padding: [20, 20] });
                } catch (e) {
                    console.error('Error fitting bounds:', e);
                }
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

