# MCP Server Module

The MCP (Model Context Protocol) Server module exposes read-only access to node and RF telemetry data using existing in-memory structures. This module provides a RESTful HTTP/JSON API without modifying any UI or Meshtastic interfaces.

## Features

- **Read-only access** to telemetry data
- **RESTful JSON API** for easy integration
- **CORS enabled** for web-based clients
- **No modifications** to existing code or interfaces
- **Standalone or integrated** operation modes

## API Endpoints

All endpoints return JSON data and support CORS.

### Root/Info
- `GET /` or `GET /api` - Returns API information and available endpoints

### Nodes
- `GET /nodes` - Get all nodes from all enabled interfaces
- `GET /nodes/<interface>` - Get nodes from a specific interface (1-9)

**Response format:**
```json
{
  "interface_1": {
    "interfaceNumber": 1,
    "nodeCount": 5,
    "nodes": [
      {
        "nodeId": 12345678,
        "nodeIdHex": "!00bc614e",
        "shortName": "Node1",
        "longName": "My Node",
        "snr": 12.5,
        "rssi": -80,
        "lastHeard": 1234567890,
        "isLocal": false,
        "position": {
          "latitude": 45.123,
          "longitude": -122.456,
          "altitude": 100,
          "time": 1234567890
        },
        "deviceMetrics": {
          "channelUtilization": 15.2,
          "airUtilTx": 8.5,
          "uptimeSeconds": 86400,
          "batteryLevel": 85,
          "voltage": 4.2
        }
      }
    ]
  }
}
```

### RF Telemetry
- `GET /telemetry` - Get RF telemetry from all interfaces
- `GET /telemetry/<interface>` - Get RF telemetry from a specific interface (1-9)

**Response format:**
```json
{
  "interface_1": {
    "interfaceNumber": 1,
    "numPacketsTx": 1234,
    "numPacketsRx": 5678,
    "numPacketsTxErr": 5,
    "numPacketsRxErr": 2,
    "numOnlineNodes": 10,
    "numTotalNodes": 15,
    "numRXDupes": 0,
    "numTxRelays": 0,
    "heapFreeBytes": 0,
    "heapTotalBytes": 0
  },
  "timing": {
    "interface1": 1234567890.123
  }
}
```

### Position Metadata
- `GET /position` - Get position metadata for all nodes

**Response format:**
```json
{
  "nodeCount": 10,
  "nodes": {
    "12345678": {
      "latitude": 45.123,
      "longitude": -122.456,
      "altitude": 100,
      "time": 1234567890
    }
  }
}
```

### Leaderboard
- `GET /leaderboard` - Get mesh leaderboard data

**Response format:**
```json
{
  "lowestBattery": {
    "nodeId": 12345678,
    "value": 15,
    "timestamp": 1234567890
  },
  "longestUptime": {
    "nodeId": 87654321,
    "value": 604800,
    "timestamp": 1234567890
  },
  "nodeMessageCounts": {
    "12345678": 150,
    "87654321": 200
  }
}
```

## Web UI

The server includes a modern web-based monitoring dashboard accessible at the root URL (`/`). The dashboard provides:

- **Dashboard Overview**: Network statistics, RF metrics, and recent nodes
- **Node List**: Detailed view of all nodes with telemetry data
- **RF Telemetry**: Packet statistics and interface metrics
- **Leaderboard**: Mesh network records and achievements
- **Position Data**: Node location information

Features:
- Auto-refresh every 5 seconds (can be toggled)
- Real-time status indicators
- Responsive design for mobile and desktop
- Color-coded badges for battery levels and status

## Usage

### Standalone Mode

Run the server as a standalone process:

```bash
python modules/mcp_server.py [host] [port]
```

Default: `http://0.0.0.0:8421` (accessible from any network interface)

Access the web UI at: `http://localhost:8421` or `http://<server-ip>:8421`

Example:
```bash
python modules/mcp_server.py 0.0.0.0 8421
```

### Integrated Mode

Import and start the server from your application:

```python
from modules.mcp_server import start_mcp_server

# Start in background thread
start_mcp_server(host='127.0.0.1', port=8421, background=True)

# Or run in foreground (blocking)
start_mcp_server(host='127.0.0.1', port=8421, background=False)
```

### Testing

Test the API using curl:

```bash
# Get API info
curl http://localhost:8421/api

# Get all nodes
curl http://localhost:8421/nodes

# Get nodes from interface 1
curl http://localhost:8421/nodes/1

# Get RF telemetry
curl http://localhost:8421/telemetry

# Get position metadata
curl http://localhost:8421/position

# Get leaderboard
curl http://localhost:8421/leaderboard
```

## Configuration

The server uses the following defaults:
- **Host**: `0.0.0.0` (all network interfaces - accessible from other computers)
- **Port**: `8421`
- **Logging**: Disabled by default (set `MCP_SERVER_LOGS=true` environment variable to enable)

## Data Sources

The module reads from existing in-memory structures:
- `interface.nodes` - Node data from Meshtastic interfaces
- `localTelemetryData` - RF telemetry statistics
- `positionMetadata` - Position metadata cache
- `meshLeaderboard` - Leaderboard statistics

**Important**: This module is read-only and does not modify any of these structures.

## Security Considerations

- The server binds to `0.0.0.0` by default (all network interfaces)
- For localhost-only access, change the host to `127.0.0.1` when starting the server
- No authentication is implemented - add authentication if exposing to untrusted networks
- All endpoints are read-only - no data modification is possible
- Consider using a reverse proxy (nginx, Apache) with SSL/TLS for production deployments

## Integration Notes

- The module uses lazy imports to avoid circular dependencies
- It accesses system module globals at runtime
- Compatible with the existing module architecture
- Does not interfere with Meshtastic interfaces or UI components

