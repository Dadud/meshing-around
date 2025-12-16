# INSTALL.md

## Table of Contents

- [Manual Install](#manual-install)
- [Docker Installation](#docker-installation)
- [Requirements](#requirements)
- [install.sh](#installsh)
  - [Purpose](#purpose)
  - [Usage](#usage)
  - [What it does](#what-it-does)
  - [When to use](#when-to-use)
  - [Note](#note)
- [update.sh](#updatesh)
  - [Purpose](#purpose-1)
  - [Usage](#usage-1)
  - [What it does](#what-it-does-1)
  - [When to use](#when-to-use-1)
  - [Note](#note-1)
- [launch.sh](#launchsh)
  - [Purpose](#purpose-2)
  - [How to Use](#how-to-use)
  - [What it does](#what-it-does-2)
  - [Note](#note-2)

---

## Manual Install

### Step 1: Pre-Flight Checks (Recommended)

Before installing, run the pre-flight checks to ensure your system is ready:

```sh
python3 script/check_requirements.py
```

This will verify:
- Python version (3.8+)
- Required tools (pip, git)
- Disk space
- Write permissions
- Network connectivity
- Serial port access

### Step 2: Install Dependencies

Install all required dependencies using pip:

```sh
pip install -r requirements.txt
```

Or if using a virtual environment (recommended):

```sh
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Step 3: Configure the Bot

**Option A - Interactive Configuration Wizard (Recommended):**

```sh
python3 script/config_wizard.py
```

The wizard will:
- Detect available serial ports
- Guide you through interface setup (Serial/TCP/BLE)
- **Auto-detect Docker environment and suggest meshtasticd connection** ← NEW
- **Test TCP connection to meshtasticd** ← NEW
- Auto-detect your location
- Configure Web UI and MCP Server
- **Set up auto-start on boot (Linux/systemd)** ← NEW
- Save configuration to `config.ini`

**Note for Docker users**: The wizard automatically detects Docker environments and defaults to `meshtasticd:4403` for TCP connections. Make sure both containers are on the same Docker network.

**Option B - Manual Configuration:**

```sh
cp config.template config.ini
nano config.ini  # Edit with your settings
```

### Step 4: Verify Installation

After installation, verify everything is set up correctly:

```sh
python3 script/verify_install.py
```

This checks:
- Configuration file validity
- All dependencies installed
- Required directories exist
- Main files present
- Modules can be imported

---

## Docker Installation

See [script/docker/README.md](script/docker/README.md) for Docker-based setup instructions.  
Docker is recommended for Windows or if you want an isolated environment.

---

## Requirements

- **Python 3.8 or later** (Python 3.13+ supported in Docker)
- All dependencies are listed in `requirements.txt` and can be installed with:
  ```sh
  pip install -r requirements.txt
  ```
- To enable emoji in the Debian/Ubuntu console:
  ```sh
  sudo apt-get install fonts-noto-color-emoji
  ```
- For Ollama LLM support, see the prompts during `install.sh` or visit [https://ollama.com](https://ollama.com).

---

## install.sh

### Purpose

`install.sh` automates installation, configuration, and service setup for the Meshing Around Bot project. It is designed for Linux systems (Debian/Ubuntu/Raspberry Pi and embedded devices).

### Usage

Run from the project root directory:

```sh
bash install.sh
```

To uninstall:

```sh
bash install.sh --nope
```

### What it does

- Checks for existing installations and permissions.
- Optionally moves the project to `/opt/meshing-around`.
- Installs Python and pip if missing (unless on embedded systems).
- Adds the current user (or a dedicated `meshbot` user) to necessary groups for serial and Bluetooth access.
- Copies and configures systemd service files for running the bot as a service.
- Sets up configuration files, updating latitude/longitude automatically.
- Offers to create and activate a Python virtual environment, or install dependencies system-wide.
- Installs optional components (emoji fonts, Ollama LLM) if desired.
- Sets permissions for log and data directories.
- Optionally installs and enables the bot as a systemd service.
- Provides post-installation notes and commands in `install_notes.txt`.
- Offers to reboot the system to complete setup.

### When to use

- For first-time installation of the Meshing Around Bot.
- When migrating to a new device or environment.
- After cloning or updating the repository to set up dependencies and services.

### Note

- You may be prompted for input during installation (e.g., for embedded mode, virtual environment, or optional features).
- Review and edit the script if you have custom requirements or are running on a non-standard system.

---

## update.sh

### Purpose

`update.sh` is an update and maintenance script for the Meshing Around Bot project. It automates the process of safely updating your codebase, backing up data, and merging configuration changes.

### Usage

Run from the project root directory:

```sh
bash update.sh
```
Or, after making it executable:
```sh
chmod +x update.sh
./update.sh
```

### What it does

- Stops running Mesh Bot services to prevent conflicts during update.
- Fetches and pulls the latest changes from the GitHub repository (using `git pull --rebase`).
- Handles git conflicts, offering to reset to the latest remote version if needed.
- Copies a custom scheduler template if not already present.
- Backs up the `data/` directory (and `custom_scheduler.py` if present) to a compressed archive.
- Merges your existing configuration with new defaults using `script/configMerge.py`, and logs the process.
- Restarts services if they were stopped for the update.
- Provides status messages and logs for troubleshooting.

### When to use

- To update your Mesh Bot installation to the latest version.
- Before making significant changes or troubleshooting, as it creates a backup of your data.

### Note

- Review `ini_merge_log.txt` and `config_new.ini` after running for any configuration changes or errors.
- You may be prompted if git conflicts are detected.

---

## launch.sh

### Purpose

`launch.sh` is a convenience script for starting the Mesh Bot, Pong Bot, or generating reports within the Python virtual environment. It ensures the correct environment is activated and the appropriate script is run.

### How to Use

From your project root, run one of the following commands:

- Launch Mesh Bot:  
  ```sh
  bash launch.sh mesh
  ```
- Launch Pong Bot:  
  ```sh
  bash launch.sh pong
  ```
- Generate HTML report:  
  ```sh
  bash launch.sh html
  ```
- Generate HTML5 report:  
  ```sh
  bash launch.sh html5
  ```
- Add a favorite (calls `script/addFav.py`):  
  ```sh
  bash launch.sh add
  ```

### What it does

- Ensures you are in the project directory.
- Copies `config.template` to `config.ini` if no config exists.
- Activates the Python virtual environment (`venv`).
- Runs the selected Python script based on your argument.
- Deactivates the virtual environment when done.

### Note

- The script requires a Python virtual environment (`venv`) to be present in the project directory.
- If `venv` is missing, the script will exit with an error message.
- Always provide an argument (`mesh`, `pong`, `html`, `html5`, or `add`) to specify what you want to launch.

## Troubleshooting

### Permissions Issues

If you encounter errors related to file or directory permissions (e.g., "Permission denied" or services failing to start):

- Ensure you are running installation scripts with sufficient privileges (use `sudo` if needed).
- The `logs`, `data`, and `config.ini` files must be owned by the user running the bot (often `meshbot` or your current user).
- You can manually reset permissions using the provided script:

  ```sh
  sudo bash etc/set-permissions.sh meshbot
  ```

- If you moved the project directory, re-run the permissions script to update ownership.

- For systemd service issues, check logs with:
  ```sh
  sudo journalctl -u mesh_bot.service
  ```

If problems persist, double-check that the user specified in your service files matches the owner of the project files and directories.