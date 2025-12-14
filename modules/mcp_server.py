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


def start_mcp_server(host: str = '0.0.0.0', port: int = 8421, background: bool = False):
    """
    Start the MCP server.
    
    Args:
        host: Host address to bind to (default: 0.0.0.0)
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

