# Meshing Around - Meshtastic Bot Framework

A comprehensive, feature-rich Python bot framework designed to enhance your [Meshtastic](https://meshtastic.org/docs/introduction/) mesh network experience. This bot provides powerful tools for network testing, messaging, games, monitoring, and automation—all via text-based message delivery over your mesh network.

![Example Use](etc/pong-bot.jpg "Example Use")

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture Overview](#architecture-overview)
- [Installation](#installation)
- [Configuration Guide](#configuration-guide)
- [Core Features](#core-features)
- [Module System](#module-system)
- [Multi-Interface Support](#multi-interface-support)
- [Web UI Dashboard](#web-ui-dashboard)
- [MCP Server API](#mcp-server-api)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Recognition](#recognition)

---

## Quick Start

### TLDR Installation

1. **Clone the repository:**
   ```sh
   git clone https://github.com/spudgunman/meshing-around
   cd meshing-around
   ```

2. **Run automated installer:**
   ```sh
   bash install.sh
   ```
   See [INSTALL.md](INSTALL.md) for detailed installation instructions.

3. **Configure the bot:**
   ```sh
   cp config.template config.ini
   nano config.ini  # Edit with your settings
   ```

4. **Start the bot:**
   ```sh
   python3 mesh_bot.py
   # Or if using systemd service:
   sudo systemctl start mesh_bot
   ```

### Quick Links

- [Installation Guide](INSTALL.md) - Detailed setup instructions
- [Module Configuration](modules/README.md) - Complete module documentation
- [Games Documentation](modules/games/README.md) - Game commands and rules
- [Docker Setup](script/docker/README.md) - Docker installation guide

---

## Architecture Overview

### System Design

The bot is built on an event-driven architecture using Python's `asyncio` and the Meshtastic Python library's pubsub system. Here's how it works:

1. **Message Reception**: The bot subscribes to Meshtastic's pubsub events (`mesh.rx.portnum`) to receive all incoming packets
2. **Packet Processing**: Each packet is processed by `onReceive()` which extracts message data, routing information, and metadata
3. **Command Detection**: Messages are checked against a `trap_list` of keywords/commands via `messageTrap()`
4. **Command Routing**: Detected commands are routed to handler functions via a command dictionary in `auto_response()`
5. **Response Generation**: Handlers generate responses which are sent back via `send_message()` with automatic chunking for long messages

### Core Components

- **`mesh_bot.py`**: Main entry point, command handlers, and message routing logic
- **`modules/system.py`**: Interface management, packet handling, telemetry collection, and watchdog functions
- **`modules/settings.py`**: Configuration file parsing and global settings management
- **`modules/log.py`**: Logging infrastructure with colored output and file rotation
- **`modules/web_ui.py`**: Web-based dashboard and configuration interface
- **`modules/mcp_server.py`**: RESTful API server for programmatic data access

### Data Flow

```
Meshtastic Device → Interface (Serial/TCP/BLE) → PubSub Event → onReceive() 
→ messageTrap() → auto_response() → Command Handler → send_message() → Interface → Mesh Network
```

### In-Memory Data Structures

The bot maintains several global data structures that are shared across modules:

- **`interface.nodes`**: Node database from each Meshtastic interface (node info, positions, user data)
- **`localTelemetryData`**: RF telemetry (SNR, RSSI, packet counts, errors)
- **`positionMetadata`**: GPS position history and metadata for all nodes
- **`meshLeaderboard`**: Competitive metrics (lowest battery, coldest temp, etc.)
- **`bbs_messages`**: Bulletin Board System public messages
- **`bbs_dm`**: Store-and-forward direct messages
- **`msg_history`**: Message history for the `messages` command
- **`cmdHistory`**: Command execution history
- **`seenNodes`**: Recently seen nodes with timestamps
- **`bbs_ban_list`**: Banned node IDs
- **`bbs_admin_list`**: Admin node IDs with elevated permissions

---

## Installation

### System Requirements

- **Python**: 3.8 or later (Python 3.13+ supported in Docker)
- **Operating System**: Linux (Raspberry Pi, Debian/Ubuntu recommended), Windows (via Docker), macOS
- **Hardware**: Any Meshtastic-compatible device (T-Beam, T-Echo, Heltec, etc.)
- **Firmware**: Latest Meshtastic firmware recommended (2.6+ for full feature support)

### Installation Methods

#### 1. Automated Installation (Recommended)

The `install.sh` script automates the entire setup process:

```sh
bash install.sh
```

**What it does:**
- Checks for Python and pip, installs if missing
- Creates project directory (optionally moves to `/opt/meshing-around`)
- Sets up user permissions for serial/Bluetooth access
- Creates Python virtual environment (optional)
- Installs all dependencies from `requirements.txt`
- Configures systemd service files
- Sets up log and data directories with proper permissions
- Offers to install optional components (emoji fonts, Ollama LLM)
- Can enable and start the bot as a systemd service

**Uninstall:**
```sh
bash install.sh --nope
```

#### 2. Manual Installation

```sh
# Clone repository
git clone https://github.com/spudgunman/meshing-around
cd meshing-around

# Install dependencies
pip install -r requirements.txt

# Copy and edit configuration
cp config.template config.ini
nano config.ini

# Run the bot
python3 mesh_bot.py
```

#### 3. Docker Installation

See [script/docker/README.md](script/docker/README.md) for complete Docker setup instructions. Docker is recommended for:
- Windows users
- Isolated environments
- OpenWebUI integration
- Easy deployment and updates

### Post-Installation

1. **Configure your interface**: Edit `config.ini` and set your device port/hostname
2. **Set your location**: Update `latitudeValue` and `longitudeValue` for location-based features
3. **Enable desired modules**: Configure modules in `config.ini` (see [Configuration Guide](#configuration-guide))
4. **Test the connection**: Run `python3 mesh_bot.py` and verify it connects to your device
5. **Set up as service** (optional): Use systemd service for automatic startup

---

## Configuration Guide

### Configuration File Structure

The bot uses `config.ini` (INI format) for all configuration. A template is provided as `config.template`. The configuration is organized into logical sections:

#### Core Sections

- **`[general]`**: Basic bot behavior, response settings, logging, LLM configuration
- **`[interface]`**: Primary radio interface (required)
- **`[interface2]` through `[interface9]`**: Additional interfaces (optional)
- **`[sentry]`**: Proximity alert system configuration
- **`[bbs]`**: Bulletin Board System settings
- **`[web_ui]`**: Web dashboard configuration
- **`[mcp_server]`**: MCP API server configuration
- **`[games]`**: Game module enable/disable flags
- **`[scheduler]`**: Automated message scheduling
- **`[fileMon]`**: File monitoring for alerts
- **`[emergencyHandler]`**: Emergency keyword detection
- **`[smtp]`**: Email/SMS integration
- **`[checklist]`**: Check-in/check-out system
- **`[inventory]`**: Inventory and POS system
- **`[qrz]`**: QRZ.com integration
- **`[messagingSettings]`**: Message chunking and delays

### Essential Configuration

#### 1. Interface Configuration

**Single Interface (Serial):**
```ini
[interface]
type = serial
port = /dev/ttyACM0
```

**Single Interface (TCP - for meshtasticd or remote nodes):**
```ini
[interface]
type = tcp
hostname = 192.168.1.100:4403
```

**Single Interface (BLE):**
```ini
[interface]
type = ble
mac = AA:BB:CC:DD:EE:FF
```

**Multiple Interfaces:**
```ini
[interface]
type = serial
port = /dev/ttyACM0

[interface2]
enabled = True
type = tcp
hostname = 192.168.1.100:4403

[interface3]
enabled = True
type = serial
port = /dev/ttyUSB0
```

#### 2. Basic Bot Settings

```ini
[general]
# Response behavior
respond_by_dm_only = True          # Only respond to DMs (recommended)
defaultChannel = 0                 # Public channel number
ignoreDefaultChannel = False       # Ignore messages on default channel
explicitCmd = True                 # Require explicit commands (not just keywords)

# Location (required for location-based features)
latitudeValue = 45.5152
longitudeValue = -122.6784

# Logging
LogMessagesToFile = False         # Log all messages to file
SyslogToFile = True               # Log system messages
sysloglevel = DEBUG               # DEBUG, INFO, WARNING, ERROR, CRITICAL
LogBackupCount = 32               # Days of logs to keep

# Welcome message
welcome_message = Welcome to the mesh bot! Send 'cmd' for commands.
```

#### 3. Module Enable/Disable

Most modules can be enabled/disabled via configuration:

```ini
[general]
# Feature toggles
ping_enabled = True               # Enable ping/pong responses
motdEnabled = True                 # Message of the day
whoami = True                      # Who am I command
spaceWeather = True                # Solar conditions, moon phases
wikipedia = False                  # Wikipedia search
ollama = False                     # LLM/AI integration
location_enabled = True             # Location-based features

[sentry]
SentryEnabled = False              # Proximity alerts

[bbs]
enabled = True                     # Bulletin Board System

[games]
dopeWars = True
lemonade = True
blackjack = True
videoPoker = True
```

### Advanced Configuration

#### Message Chunking

Long messages are automatically split to fit within Meshtastic's packet size limits:

```ini
[messagingSettings]
MESSAGE_CHUNK_SIZE = 160          # Characters per chunk
splitDelay = 0                     # Delay between chunks (seconds)
responseDelay = 0.7                # Delay before sending response
```

#### Store and Forward

Enable message storage for offline nodes:

```ini
[general]
StoreForward = True                # Enable store-and-forward
StoreLimit = 3                     # Max messages to store per node
reverseSF = False                  # Send oldest first (False) or newest first (True)
```

#### Anti-Spam Protection

Prevents the bot from flooding channels:

```ini
[general]
antiSpam = True                    # Enable anti-spam (recommended)
```

When enabled, the bot will:
- Only respond on non-default channels
- Throttle responses to prevent flooding
- Ignore rapid repeated commands

#### LLM/AI Configuration

```ini
[general]
ollama = True                      # Enable Ollama integration
ollamaHostName = http://localhost:11434
ollamaModel = gemma3:270m          # Model to use
rawLLMQuery = True                 # Send raw queries (no system prompt)
llmReplyToNonCommands = True       # Reply to non-command DMs with AI
llmUseWikiContext = False          # Use Wikipedia for RAG context
useOpenWebUI = False               # Use OpenWebUI instead of direct Ollama
openWebUIURL = http://localhost:3000
openWebUIAPIKey =                  # API key if required
```

### Configuration via Web UI

The Web UI provides a user-friendly interface for editing configuration. See [Web UI Dashboard](#web-ui-dashboard) section.

---

## Core Features

### Message Handling

#### Command Detection

The bot uses a two-stage command detection system:

1. **Trap List**: `messageTrap()` checks if a message contains any keyword from `trap_list` (built from enabled modules)
2. **Command Dictionary**: `auto_response()` matches the first detected command to a handler function

Commands can be:
- **Explicit**: Must be the first word (`ping`, `cmd`, `bbslist`)
- **Keyword-based**: Detected anywhere in message (configurable)
- **DM-only**: Some commands only work in direct messages (games, admin functions)

#### Response Modes

- **DM-only mode** (`respond_by_dm_only = True`): Bot only responds to direct messages
- **Channel mode** (`respond_by_dm_only = False`): Bot responds on channels (use with caution to avoid spam)

#### Message Chunking

Messages longer than `MESSAGE_CHUNK_SIZE` (default 160 characters) are automatically split into multiple packets. The bot:
- Splits at word boundaries when possible
- Adds chunk indicators (e.g., "1/3", "2/3", "3/3")
- Sends chunks with configurable delay between them

### Network Testing

#### Ping Command

The `ping` command is the primary network testing tool:

```
ping                    # Basic ping, returns SNR/RSSI/hop count
ping 10                 # Auto-ping 10 times (DM only)
ping @username          # Ping specific user (triggers BBS DM joke if enabled)
ping stop               # Stop auto-ping
ping ?                  # Help (DM only)
```

**Response format:**
```
🏓PONG [RF]
SNR: 12.5, RSSI: -80, Hops: 2
```

- `[RF]` = Received via direct radio
- `[GW]` = Received via gateway (internet/MQTT)
- `[F]` = Received via mesh/flood route

#### Test Command

Tests radio buffer limits by sending incrementally sized data:

```
test 4                  # Send data up to maxBuffer limit (DM only)
```

### Multi-Interface Support

The bot can simultaneously monitor up to 9 Meshtastic interfaces:

- **Interface Types**: Serial (USB), TCP (network), BLE (Bluetooth)
- **Independent Channels**: Each interface can use different channels
- **Cross-Interface Messaging**: Send messages between interfaces
- **Unified Node Database**: All interfaces share the same node information

**Configuration Example:**
```ini
[interface]
type = serial
port = /dev/ttyACM0

[interface2]
enabled = True
type = tcp
hostname = 192.168.1.100:4403

[interface3]
enabled = True
type = serial
port = /dev/ttyUSB0
```

### Bulletin Board System (BBS)

A store-and-forward messaging system for the mesh network:

**Commands:**
- `bbslist` - List all public messages
- `bbspost $subject #message` - Post a public message
- `bbspost @nodeNumber #message` - Send DM to specific node
- `bbspost @shortName #message` - Send DM using short name
- `bbsread #` - Read message by number
- `bbsdelete #` - Delete message (author or admin only)
- `bbsinfo` - Get BBS statistics
- `bbshelp` - Show help

**Features:**
- Public message board accessible to all nodes
- Direct message store-and-forward
- Message threading and replies
- Admin controls for moderation
- BBS linking between multiple bots
- Message persistence (survives bot restarts)

**Configuration:**
```ini
[bbs]
enabled = True
bbs_admin_list = 2813308004,4258675309    # Admin node IDs
bbs_ban_list =                            # Banned node IDs
bbs_link_enabled = False                   # Link with other bots
bbslink_whitelist =                        # Allowed linked bots
```

### Location-Based Features

#### Map Command

Log GPS locations with descriptions:

```
map Survey point 1
map Radio site - good coverage
```

Locations are saved to `data/map.csv` for analysis.

#### Proximity Alerts (Sentry)

Get notified when nodes enter/exit a configured area:

```ini
[sentry]
SentryEnabled = True
SentryRadius = 100                        # Meters
SentryInterface = 1
SentryChannel = 2
sentryWatchList = 2813308004              # Nodes to watch
sentryIgnoreList =                        # Nodes to ignore
SentryHoldoff = 9                         # Alert holdoff (20s * 9 = 3 minutes)
```

**Use Cases:**
- Geofencing for campsites or events
- Asset tracking
- "King of the hill" games
- Automated actions (trigger scripts, send emails)

#### High Altitude Alerts

Detect nodes at high altitude (balloons, aircraft):

```ini
[sentry]
highFlyingAlert = True
highFlyingAlertAltitude = 2000           # Meters
highFlyingAlertInterface = 1
highFlyingAlertChannel = 2
highFlyingIgnoreList =                    # Nodes to ignore
highflyOpenskynetwork = True              # Check OpenSky Network for aircraft
```

### Weather and Environmental Data

#### Weather Commands

- `wx` - Current weather (NOAA or Open-Meteo)
- `wxc` - Weather conditions (Open-Meteo worldwide)
- `mwx` - Marine weather
- `river` - River flow data
- `tide` - Tide information

#### Earthquake Data

- `earthquake` - Recent earthquakes (USGS)

#### Solar Conditions

- `solar` - Solar conditions and space weather
- `hfcond` - HF band conditions
- `sun` - Sun position and info
- `moon` - Moon phase and position

### Emergency Alerts

#### EAS (Emergency Alert System)

Receive emergency alerts from various sources:

```ini
[general]
enableUSAlerts = True                     # FEMA iPAWS alerts
enableNOAAAlerts = True                   # NOAA alerts
enableUSGSAlerts = True                   # USGS volcano alerts
enableDEalerts = False                    # NINA alerts (Germany)
```

**Commands:**
- `ea` or `ealert` - Get recent emergency alerts

### File Monitoring

Monitor a text file for changes and broadcast to mesh:

```ini
[fileMon]
enabled = True
file_path = alert.txt
broadcastCh = 2
```

When `alert.txt` changes, the new content is broadcast to the configured channel. Useful for:
- External system integration
- Automated announcements
- Triggering surveys or games

### Scheduler

Automate messages on a schedule:

```ini
[scheduler]
enabled = True
```

Configure scheduled tasks in `etc/custom_scheduler.template`. Supports:
- Weather updates
- Net reminders
- MOTD updates
- Custom messages

### Games

All games are played via direct message. See [modules/games/README.md](modules/games/README.md) for complete documentation.

**Available Games:**
- DopeWars - Drug dealing simulation
- Lemonade Stand - Business simulation
- BlackJack - Card game
- Video Poker - Poker game
- Mastermind - Code breaking
- Golf Sim - Golf simulation
- Hangman - Word guessing
- Ham Test - ARRL exam practice
- Tic-Tac-Toe - Classic game
- Battleship - Naval combat
- Quiz - Group quiz system

**Commands:**
- `games` - List available games
- `blackjack` - Start blackjack (DM only)
- `q: join` - Join group quiz
- `q: start` - Start quiz (admin only)

### Inventory and POS System

Complete inventory management and point-of-sale system:

**Commands:**
- `itemlist` - List all items
- `itemadd $name #price #quantity` - Add item
- `itemsell $name #quantity` - Sell item
- `itemloan $name #quantity @node` - Loan item
- `itemreturn $name` - Return loaned item
- `cartadd $name #quantity` - Add to cart
- `cartbuy` - Purchase cart contents
- `itemstats` - Sales statistics

**Configuration:**
```ini
[inventory]
enabled = True
inventory_db = data/inventory.db
disable_penny = False                    # Allow penny transactions
```

### Checklist System

Check-in/check-out system for people and equipment:

**Commands:**
- `checkin $description` - Check in
- `checkout $description` - Check out
- `checklist` - View checklist
- `approvecl #` - Approve check-in (admin)
- `denycl #` - Deny check-in (admin)

**Configuration:**
```ini
[checklist]
enabled = True
checklist_db = data/checklist.db
```

---

## Module System

The bot uses a modular architecture where features are implemented as separate Python modules in the `modules/` directory. Modules can be enabled/disabled via configuration.

### Core Modules

- **`system.py`**: Interface management, packet handling, telemetry, watchdog
- **`settings.py`**: Configuration parsing and global settings
- **`log.py`**: Logging infrastructure
- **`bbstools.py`**: Bulletin Board System implementation
- **`scheduler.py`**: Message scheduling system

### Feature Modules

- **`locationdata.py`**: Location services, weather, geolocation
- **`space.py`**: Solar conditions, satellite passes
- **`llm.py`**: LLM/AI integration (Ollama, OpenWebUI)
- **`wiki.py`**: Wikipedia/Kiwix search
- **`rss.py`**: RSS feed parsing
- **`radio.py`**: Radio monitoring (Hamlib, WSJT-X, JS8Call, VOX, TTS)
- **`smtp.py`**: Email/SMS integration
- **`inventory.py`**: Inventory and POS system
- **`checklist.py`**: Check-in/check-out system
- **`qrz.py`**: QRZ.com integration
- **`dxspot.py`**: DX cluster spotting
- **`survey.py`**: Survey system
- **`globalalert.py`**: Emergency alerts (international)
- **`filemon.py`**: File monitoring
- **`web_ui.py`**: Web dashboard
- **`mcp_server.py`**: MCP API server

### Game Modules

All games are in `modules/games/`. See [modules/games/README.md](modules/games/README.md).

### Adding New Modules

See [modules/adding_more.md](modules/adding_more.md) for developer documentation on creating new modules.

---

## Multi-Interface Support

The bot supports up to 9 simultaneous Meshtastic interfaces, allowing you to:
- Monitor multiple mesh networks
- Bridge between networks
- Use different channels per interface
- Aggregate telemetry from all interfaces

### Interface Types

1. **Serial (USB)**: Direct connection to Meshtastic device
   ```ini
   [interface]
   type = serial
   port = /dev/ttyACM0
   ```

2. **TCP (Network)**: Connect to meshtasticd or remote node
   ```ini
   [interface2]
   type = tcp
   hostname = 192.168.1.100:4403
   ```

3. **BLE (Bluetooth)**: Bluetooth Low Energy connection
   ```ini
   [interface3]
   type = ble
   mac = AA:BB:CC:DD:EE:FF
   ```
   **Note**: Only one BLE interface is allowed.

### Interface Management

- **Automatic Reconnection**: Watchdog monitors interfaces and automatically reconnects on failure
- **Independent Channels**: Each interface can use different channels
- **Unified Node Database**: All interfaces share node information
- **Cross-Interface Messaging**: Send messages between interfaces

### Watchdog System

The watchdog (`watchdog()`) runs every 20 seconds and:
- Checks interface connectivity
- Monitors telemetry
- Handles sentry/proximity alerts
- Manages multi-ping requests
- Performs memory cleanup
- Attempts reconnection on failure

---

## Web UI Dashboard

A comprehensive web-based dashboard for monitoring and configuring the bot.

### Access

By default, the Web UI runs on `http://0.0.0.0:8420`. Access it from any device on your network:
- Local: `http://localhost:8420`
- Network: `http://your-bot-ip:8420`

### Features

#### Dashboard Tab
- Real-time node list with status
- RF telemetry overview
- Recent activity feed
- System health indicators

#### Node Map Tab
- Interactive map (OpenStreetMap or Google Maps)
- Node locations with position trails
- Click nodes for details
- Configurable map provider

#### BBS Tab
- Browse public BBS messages
- View pending direct messages
- Post new messages
- Delete messages (admin)

#### RF Telemetry Tab
- Packet statistics per interface
- TX/RX counts
- Error rates
- SNR/RSSI metrics
- Channel utilization

#### Configuration Tab
- Edit all bot settings
- User-friendly labels and descriptions
- Grouped by category
- Collapsible sections
- Automatic backup on save
- Real-time validation

#### Activity Feed Tab
- Recent commands executed
- Message history
- Node join/leave events
- System events

#### Node Details Tab
- Detailed information per node
- Position history
- Device metrics
- Message statistics

#### Statistics Tab
- Charts and graphs
- Network growth over time
- Message volume
- Node activity patterns

#### System Health Tab
- CPU and memory usage
- Interface status
- Error logs
- Performance metrics

#### Network Graph Tab
- Visual network topology
- Node connections
- Routing paths
- Signal strength visualization

#### Alert Center Tab
- Active alerts
- Alert history
- Alert configuration

#### Export/Download Tab
- Export node data (CSV/JSON)
- Download logs
- Backup configuration

#### Message Composer Tab
- Send messages to nodes
- Broadcast to channels
- Message templates

#### Node Management Tab
- Ban/unban nodes
- Admin management
- Node information editing

#### Position History Tab
- Node movement trails
- Position timeline
- Geographic analysis

### Configuration

```ini
[web_ui]
enabled = True
host = 0.0.0.0                      # Listen on all interfaces
port = 8420
# Optional: Google Maps API key for map provider
google_maps_api_key = 
```

**Disable Web UI:**
```ini
[web_ui]
enabled = False
```

### Data Access

The Web UI directly accesses the bot's in-memory data structures (not via MCP API), ensuring real-time data without polling delays.

---

## MCP Server API

A RESTful API server providing read-only access to bot telemetry and node data.

### Access

By default, the MCP Server runs on `http://0.0.0.0:8421`.

### Endpoints

#### `/api` or `/`
Returns API information and available endpoints.

#### `/api/nodes`
Get all nodes from all interfaces.
```json
{
  "interface_1": {
    "interfaceNumber": 1,
    "nodeCount": 5,
    "nodes": [...]
  }
}
```

#### `/api/nodes/<interface>`
Get nodes from specific interface (1-9).

#### `/api/telemetry`
Get RF telemetry from all interfaces.
```json
{
  "interface_1": {
    "tx": 1234,
    "rx": 5678,
    "errors": 0,
    "snr": 12.5,
    "rssi": -80
  }
}
```

#### `/api/telemetry/<interface>`
Get telemetry from specific interface.

#### `/api/position`
Get position metadata for all nodes.

#### `/api/leaderboard`
Get mesh leaderboard data (extreme metrics).

### CORS

The API has CORS enabled, allowing access from web applications and other services.

### Configuration

```ini
[mcp_server]
enabled = True
host = 0.0.0.0                      # Listen on all interfaces
port = 8421
```

**Disable MCP Server:**
```ini
[mcp_server]
enabled = False
```

---

## Troubleshooting

### Bot Won't Start

1. **Check interface connection:**
   ```sh
   ls -l /dev/ttyACM*  # List serial devices
   ```

2. **Check permissions:**
   ```sh
   sudo usermod -a -G dialout $USER  # Add user to dialout group
   sudo usermod -a -G bluetooth $USER  # Add user to bluetooth group (for BLE)
   ```

3. **Check logs:**
   ```sh
   tail -f logs/mesh_bot.log
   ```

4. **Verify configuration:**
   ```sh
   python3 -c "import configparser; c = configparser.ConfigParser(); c.read('config.ini'); print(c.sections())"
   ```

### Interface Disconnection

The watchdog automatically attempts to reconnect. If reconnection fails:
- Check physical connection
- Verify device is powered
- Check for other processes using the device: `lsof /dev/ttyACM0`
- Review logs for error messages

### Messages Not Received

1. **Check channel configuration:** Verify `defaultChannel` matches your device
2. **Check DM mode:** If `respond_by_dm_only = True`, bot only responds to DMs
3. **Check anti-spam:** Bot may be throttling responses
4. **Verify command is in trap_list:** Check logs for "Bot detected Commands"

### Web UI Not Accessible

1. **Check if enabled:**
   ```ini
   [web_ui]
   enabled = True
   ```

2. **Check firewall:**
   ```sh
   sudo ufw allow 8420/tcp
   ```

3. **Check if running:** Look for "Web UI started" in logs
4. **Try different port:** Change `port` in `[web_ui]` section

### Performance Issues

1. **Reduce logging level:**
   ```ini
   [general]
   sysloglevel = INFO  # Instead of DEBUG
   ```

2. **Disable unused modules:** Turn off features you don't use
3. **Check system resources:**
   ```sh
   top
   htop
   ```

4. **Review watchdog frequency:** Watchdog runs every 20 seconds by default

### Common Configuration Errors

- **Missing required sections:** Copy from `config.template`
- **Invalid interface type:** Must be `serial`, `tcp`, or `ble`
- **Port already in use:** Change port numbers for web_ui or mcp_server
- **Invalid node IDs:** Node IDs must be numeric

---

## Development

### Project Structure

```
meshing-around/
├── mesh_bot.py              # Main entry point
├── pong_bot.py              # Minimal bot example
├── config.template          # Configuration template
├── requirements.txt         # Python dependencies
├── install.sh              # Installation script
├── launch.sh               # Launch script (venv)
├── modules/                # Feature modules
│   ├── system.py           # Core system functions
│   ├── settings.py         # Configuration management
│   ├── log.py              # Logging
│   ├── web_ui.py           # Web dashboard
│   ├── mcp_server.py       # API server
│   └── games/              # Game modules
├── script/                 # Utility scripts
│   ├── addFav.py          # Add favorite nodes
│   └── docker/            # Docker configuration
├── data/                   # Data files
│   ├── bbsdb.pkl          # BBS database
│   └── survey/            # Survey definitions
├── logs/                   # Log files
└── etc/                    # Additional files
```

### Adding New Commands

1. **Add command to trap_list** in `modules/system.py`:
   ```python
   trap_list_mycommand = ("mycommand",)
   trap_list = trap_list + trap_list_mycommand
   ```

2. **Add handler function** in `mesh_bot.py`:
   ```python
   def handle_mycommand(message, message_from_id, deviceID, isDM):
       return "Response message"
   ```

3. **Add to command dictionary** in `auto_response()`:
   ```python
   "mycommand": lambda: handle_mycommand(message, message_from_id, deviceID, isDM),
   ```

### Testing

```sh
# Run with debug logging
python3 mesh_bot.py

# Test specific module
python3 -c "from modules import bbstools; print(bbstools.bbs_help())"
```

### Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

---

## Recognition

I used ideas and snippets from other responder bots and want to call them out!

### Inspiration and Code Snippets
- [MeshLink](https://github.com/Murturtle/MeshLink)
- [Meshtastic Python Examples](https://github.com/pdxlocations/meshtastic-Python-Examples)
- [Meshtastic Matrix Relay](https://github.com/geoffwhittington/meshtastic-matrix-relay)

### Games Ported From
- [Lemonade Stand](https://github.com/tigerpointe/Lemonade-Stand/)
- [Drug Wars](https://github.com/Reconfirefly/drugwars)
- [BlackJack](https://github.com/Himan10/BlackJack)
- [Video Poker Terminal Game](https://github.com/devtronvarma/Video-Poker-Terminal-Game)
- [Python Mastermind](https://github.com/pwdkramer/pythonMastermind/)
- [Golf](https://github.com/danfriedman30/pythongame)
- ARRL Question Pool Data from https://github.com/russolsen/ham_radio_question_pool

### Special Thanks
For testing and feature ideas on Discord and GitHub, if its stable its thanks to you all.
- **PiDiBi, Cisien, bitflip, nagu, Nestpebble, NomDeTom, Iris, Josh, GlockTuber, FJRPiolt, dj505, Woof, propstg, snydermesh, trs2982, F0X, Malice, mesb1, Hailo1999**
- **xdep**: For the reporting html. 📊
- **mrpatrick1991**: For OG Docker configurations. 💻
- **A-c0rN**: Assistance with iPAWS and 🚨
- **Mike O'Connell/skrrt**: For [eas_alert_parser](etc/eas_alert_parser.py) enhanced by **sheer.cold**
- **dadud**: For vibe coding the Web UI dashboard and MCP Server API, and idea on [etc/icad_tone.py](etc/icad_tone.py) 🎨
- **WH6GXZ nurse dude**: Volcano Alerts 🌋
- **mikecarper**: hamtest, leading to quiz etc.. 📋
- **c.merphy360**: high altitude alerts. 🚀
- **G7KSE**: DX Spotting idea. 📻
- **Growing List of GitHub Contributers**
- **Meshtastic Discord Community**: For putting up with 🥔

### Tools
- **Node Backup Management**: [Node Slurper](https://github.com/SpudGunMan/node-slurper)

---

Meshtastic® is a registered trademark of Meshtastic LLC. Meshtastic software components are released under various licenses, see GitHub for details. No warranty is provided - use at your own risk.
