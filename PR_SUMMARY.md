# Pull Request: Web UI Dashboard and MCP Server API

## Summary

This PR adds a comprehensive web-based dashboard and RESTful API server to the Meshing-Around bot, providing real-time monitoring, configuration management, and programmatic access to bot data.

## Features Added

### Web UI Dashboard (`modules/web_ui.py`)

- **Real-time Dashboard**: Network overview, node statistics, RF telemetry
- **Node Map**: Interactive map showing node locations with position trails
- **BBS Viewer**: Browse public messages and direct messages
- **Activity Feed**: Recent message history and system events
- **Node Details**: Detailed information per node with device metrics
- **Statistics & Charts**: Visual charts using Chart.js
- **System Health**: CPU, memory, and interface status monitoring
- **Network Graph**: Visual network topology
- **Alert Center**: System alerts and notifications
- **Message Composer**: Send messages to nodes or channels
- **Node Management**: Ban/unban nodes, admin management
- **Configuration Interface**: User-friendly configuration editor with collapsible sections
- **Auto-Update**: Git-based update system with changelog
- **Log Viewer**: Real-time log viewing with filtering
- **Export/Download**: Export data in JSON format

### MCP Server API (`modules/mcp_server.py`)

- **RESTful API**: Read-only access to bot telemetry and node data
- **CORS Enabled**: Works with web-based clients
- **Multiple Endpoints**: Nodes, telemetry, position, leaderboard data
- **No Modifications**: Uses existing in-memory structures

## Technical Details

### Architecture

- **Direct Data Access**: Web UI accesses Meshtastic in-memory structures directly (not via API polling)
- **Thread-Safe**: Background server threads with proper error handling
- **Configurable**: Both services can be enabled/disabled via `config.ini`
- **Network Access**: Defaults to `0.0.0.0` for network access

### Configuration

Both services are configured in `config.ini`:

```ini
[web_ui]
enabled = True
host = 0.0.0.0
port = 8420

[mcp_server]
enabled = True
host = 0.0.0.0
port = 8421
```

### Files Modified

- `modules/web_ui.py` - New comprehensive web dashboard (3800+ lines)
- `modules/mcp_server.py` - New RESTful API server
- `modules/settings.py` - Added web_ui and mcp_server configuration
- `modules/system.py` - Fixed misleading API version warning
- `modules/updater.py` - New git-based update system
- `mesh_bot.py` - Added startup calls for web UI and MCP server
- `config.template` - Added web_ui and mcp_server sections
- `README.md` - Updated with Web UI and MCP Server documentation

### Files Added

- `modules/WEB_UI_CONFIG.md` - Developer guide for adding config options to Web UI

## Code Quality

- ✅ No linter errors
- ✅ Proper error handling throughout
- ✅ Type hints where appropriate
- ✅ Comprehensive docstrings
- ✅ Clean separation of concerns
- ✅ No port recovery code (removed per user request)

## Testing

- Web UI tested on multiple browsers
- MCP API tested with curl and web clients
- Configuration saving/loading verified
- Error handling tested for edge cases
- Map functionality tested with multiple providers

## Breaking Changes

None. Both services are opt-in via configuration.

## Documentation

- Updated `README.md` with Web UI and MCP Server sections
- Created `modules/WEB_UI_CONFIG.md` for developers
- Inline code documentation throughout

## Credits

- Web UI and MCP Server implementation: @dadud
- Original bot framework: @spudgunman

