#!/usr/bin/env python3
"""
Interactive configuration wizard for Meshing Around.
Helps users set up config.ini with guided prompts.
"""

import sys
import os
import platform
import subprocess
import shutil
import configparser
import serial.tools.list_ports
from pathlib import Path

# Color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}\n")

def get_serial_ports():
    """Detect available serial ports."""
    ports = []
    try:
        import serial.tools.list_ports
        available_ports = serial.tools.list_ports.comports()
        for port in available_ports:
            ports.append(port.device)
    except ImportError:
        # pyserial not installed, can't detect ports
        pass
    except Exception:
        pass
    return ports

def get_user_input(prompt, default=None, validator=None):
    """Get user input with optional default and validation."""
    if default:
        full_prompt = f"{prompt} [{default}]: "
    else:
        full_prompt = f"{prompt}: "
    
    while True:
        value = input(full_prompt).strip()
        if not value and default:
            value = default
        
        if not value:
            print(f"{Colors.RED}This field is required.{Colors.RESET}")
            continue
        
        if validator:
            try:
                if validator(value):
                    return value
            except Exception as e:
                print(f"{Colors.RED}Invalid input: {e}{Colors.RESET}")
        else:
            return value

def check_meshtasticd_connection(hostname, port=4403):
    """Check if meshtasticd is reachable at the given hostname:port."""
    import socket
    try:
        # Parse hostname:port format
        if ':' in hostname:
            host, port_str = hostname.rsplit(':', 1)
            try:
                port = int(port_str)
            except ValueError:
                pass
        else:
            host = hostname
        
        # For Docker service names (like "meshtasticd"), DNS resolution might fail
        # outside Docker, but that's OK - the connection test is just a hint
        try:
            # Try to resolve the hostname first
            socket.gethostbyname(host)
        except socket.gaierror:
            # If DNS resolution fails (e.g., Docker service name outside Docker),
            # that's OK - user might be configuring for Docker
            if host in ['meshtasticd', 'localhost', '127.0.0.1']:
                # These are common and might not resolve in all contexts
                pass
            else:
                # Unknown hostname that can't be resolved
                return False
        
        # Try to connect to the TCP port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False

def detect_docker_environment():
    """Detect if running in Docker environment."""
    # Check for Docker environment indicators
    docker_indicators = [
        Path('/.dockerenv').exists(),
        os.environ.get('container') == 'docker',
        Path('/proc/self/cgroup').exists() and 'docker' in Path('/proc/self/cgroup').read_text() if Path('/proc/self/cgroup').exists() else False
    ]
    return any(docker_indicators)

def configure_interface(config):
    """Configure the primary interface."""
    print_header("Interface Configuration")
    
    print("What type of interface do you want to use?")
    print("1. Serial (USB connection to Meshtastic device)")
    print("2. TCP (Network connection to meshtasticd or remote node)")
    print("3. BLE (Bluetooth Low Energy)")
    
    choice = get_user_input("Enter choice (1-3)", "1", lambda x: x in ['1', '2', '3'])
    
    if choice == '1':
        config['interface']['type'] = 'serial'
        
        # Detect serial ports
        ports = get_serial_ports()
        if ports:
            print(f"\n{Colors.GREEN}Detected serial ports:{Colors.RESET}")
            for i, port in enumerate(ports, 1):
                print(f"  {i}. {port}")
            
            port_choice = get_user_input(
                f"\nSelect port (1-{len(ports)}) or enter custom path",
                validator=lambda x: True
            )
            
            try:
                port_index = int(port_choice) - 1
                if 0 <= port_index < len(ports):
                    config['interface']['port'] = ports[port_index]
                else:
                    config['interface']['port'] = port_choice
            except ValueError:
                config['interface']['port'] = port_choice
        else:
            config['interface']['port'] = get_user_input(
                "Enter serial port path",
                "/dev/ttyACM0" if os.name != 'nt' else "COM1"
            )
    
    elif choice == '2':
        config['interface']['type'] = 'tcp'
        
        print(f"\n{Colors.BLUE}TCP Interface Configuration{Colors.RESET}")
        print("TCP interface connects to meshtasticd daemon or remote Meshtastic node.")
        print("Common configurations:")
        print("  - Docker: meshtasticd:4403")
        print("  - Local meshtasticd: localhost:4403")
        print("  - Remote node: 192.168.1.100:4403")
        print("  - Default port is 4403 if not specified")
        
        # Detect Docker environment
        is_docker = detect_docker_environment()
        if is_docker:
            default_hostname = "meshtasticd:4403"
            print(f"\n{Colors.GREEN}Docker environment detected{Colors.RESET}")
            print(f"Defaulting to meshtasticd service name")
        else:
            default_hostname = "localhost:4403"
        
        hostname = get_user_input(
            "Enter hostname:port (e.g., meshtasticd:4403 or localhost:4403)",
            default_hostname,
            validator=lambda x: True
        )
        
        # Ensure port is included
        if ':' not in hostname:
            port = get_user_input(
                "Enter port number",
                "4403",
                lambda x: x.isdigit() and 1 <= int(x) <= 65535
            )
            hostname = f"{hostname}:{port}"
        
        config['interface']['hostname'] = hostname
        
        # Test connection if user wants
        test_connection = get_user_input(
            f"\nTest connection to {hostname}? (y/n)",
            "y",
            lambda x: x.lower() in ['y', 'n', 'yes', 'no']
        )
        
        if test_connection.lower() in ['y', 'yes']:
            print(f"{Colors.BLUE}Testing connection...{Colors.RESET}")
            if check_meshtasticd_connection(hostname):
                print(f"{Colors.GREEN}✓ Connection successful!{Colors.RESET}")
            else:
                print(f"{Colors.YELLOW}⚠ Could not connect to {hostname}{Colors.RESET}")
                print(f"{Colors.YELLOW}  This may be normal if:{Colors.RESET}")
                print(f"{Colors.YELLOW}    - meshtasticd is not running yet{Colors.RESET}")
                print(f"{Colors.YELLOW}    - You're configuring for Docker (service names resolve in containers){Colors.RESET}")
                print(f"{Colors.YELLOW}    - meshtasticd is on a different network{Colors.RESET}")
                print(f"{Colors.YELLOW}  Make sure meshtasticd is running and accessible when you start the bot.{Colors.RESET}")
                
                change_hostname = get_user_input(
                    "Change hostname? (y/n)",
                    "n",
                    lambda x: x.lower() in ['y', 'n', 'yes', 'no']
                )
                if change_hostname.lower() in ['y', 'yes']:
                    # Get new hostname
                    new_hostname = get_user_input(
                        "Enter hostname:port",
                        hostname,
                        validator=lambda x: True
                    )
                    if ':' not in new_hostname:
                        port = get_user_input(
                            "Enter port number",
                            "4403",
                            lambda x: x.isdigit() and 1 <= int(x) <= 65535
                        )
                        new_hostname = f"{new_hostname}:{port}"
                    config['interface']['hostname'] = new_hostname
                    hostname = new_hostname
    
    elif choice == '3':
        config['interface']['type'] = 'ble'
        config['interface']['mac'] = get_user_input(
            "Enter BLE MAC address",
            "AA:BB:CC:DD:EE:FF"
        )

def configure_general(config):
    """Configure general settings."""
    print_header("General Settings")
    
    # Location
    print("Location is used for weather, solar conditions, and proximity features.")
    use_auto_location = get_user_input(
        "Auto-detect location from IP? (y/n)",
        "y",
        lambda x: x.lower() in ['y', 'n', 'yes', 'no']
    )
    
    if use_auto_location.lower() in ['y', 'yes']:
        try:
            import requests
            response = requests.get('https://ipinfo.io/loc', timeout=5)
            if response.status_code == 200:
                lat, lon = response.text.strip().split(',')
                config['general']['latitudeValue'] = lat.strip()
                config['general']['longitudeValue'] = lon.strip()
                print(f"{Colors.GREEN}Location detected: {lat}, {lon}{Colors.RESET}")
            else:
                raise Exception("API request failed")
        except Exception:
            print(f"{Colors.YELLOW}Could not auto-detect location.{Colors.RESET}")
            config['general']['latitudeValue'] = get_user_input("Enter latitude", "48.50")
            config['general']['longitudeValue'] = get_user_input("Enter longitude", "-123.0")
    else:
        config['general']['latitudeValue'] = get_user_input("Enter latitude", "48.50")
        config['general']['longitudeValue'] = get_user_input("Enter longitude", "-123.0")
    
    # Response mode
    print("\nResponse mode:")
    print("1. DM only (recommended) - Bot only responds to direct messages")
    print("2. Channel mode - Bot responds on channels (can cause spam)")
    
    response_mode = get_user_input("Enter choice (1-2)", "1", lambda x: x in ['1', '2'])
    config['general']['respond_by_dm_only'] = 'True' if response_mode == '1' else 'False'
    
    # Default channel
    config['general']['defaultChannel'] = get_user_input(
        "Default channel number (usually 0)",
        "0",
        lambda x: x.isdigit()
    )

def configure_web_ui(config):
    """Configure Web UI settings."""
    print_header("Web UI Configuration")
    
    enable_web_ui = get_user_input(
        "Enable Web UI dashboard? (y/n)",
        "y",
        lambda x: x.lower() in ['y', 'n', 'yes', 'no']
    )
    
    config['web_ui']['enabled'] = 'True' if enable_web_ui.lower() in ['y', 'yes'] else 'False'
    
    if config['web_ui']['enabled'] == 'True':
        config['web_ui']['port'] = get_user_input(
            "Web UI port",
            "8420",
            lambda x: x.isdigit() and 1024 <= int(x) <= 65535
        )

def configure_mcp_server(config):
    """Configure MCP Server settings."""
    print_header("MCP Server Configuration")
    
    enable_mcp = get_user_input(
        "Enable MCP Server API? (y/n)",
        "y",
        lambda x: x.lower() in ['y', 'n', 'yes', 'no']
    )
    
    config['mcp_server']['enabled'] = 'True' if enable_mcp.lower() in ['y', 'yes'] else 'False'
    
    if config['mcp_server']['enabled'] == 'True':
        config['mcp_server']['port'] = get_user_input(
            "MCP Server port",
            "8421",
            lambda x: x.isdigit() and 1024 <= int(x) <= 65535
        )

def configure_autostart():
    """Configure auto-start on system boot (systemd service)."""
    print_header("Auto-Start Configuration")
    
    # Check if systemd is available (Linux only)
    if platform.system() != 'Linux':
        print(f"{Colors.YELLOW}Auto-start is only available on Linux systems with systemd.{Colors.RESET}")
        print(f"{Colors.YELLOW}On Windows, you can use Task Scheduler manually.{Colors.RESET}")
        print(f"{Colors.YELLOW}On macOS, you can use launchd manually.{Colors.RESET}")
        return False
    
    # Check if systemd is available
    if not shutil.which('systemctl'):
        print(f"{Colors.YELLOW}systemctl not found. systemd may not be available.{Colors.RESET}")
        return False
    
    enable_autostart = get_user_input(
        "Enable auto-start on system boot? (y/n)",
        "n",
        lambda x: x.lower() in ['y', 'n', 'yes', 'no']
    )
    
    if enable_autostart.lower() not in ['y', 'yes']:
        return False
    
    print(f"\n{Colors.BLUE}Setting up systemd service for auto-start...{Colors.RESET}")
    
    # Get current directory
    project_path = os.path.abspath('.')
    
    # Check if using virtual environment
    venv_path = Path('venv')
    using_venv = venv_path.exists() and (venv_path / 'bin' / 'activate').exists()
    
    # Determine Python executable and command
    if using_venv:
        python_cmd = str(venv_path / 'bin' / 'python3')
        exec_start = f"{python_cmd} mesh_bot.py"
        print(f"{Colors.GREEN}Detected virtual environment{Colors.RESET}")
    else:
        # Check for launch.sh
        launch_sh = Path('launch.sh')
        if launch_sh.exists():
            exec_start = f"/bin/bash {project_path}/launch.sh mesh"
            print(f"{Colors.GREEN}Using launch.sh script{Colors.RESET}")
        else:
            python_cmd = shutil.which('python3') or shutil.which('python')
            if not python_cmd:
                print(f"{Colors.RED}Python3 not found in PATH{Colors.RESET}")
                return False
            exec_start = f"{python_cmd} mesh_bot.py"
    
    # Get current user (portable method)
    try:
        current_user = os.getlogin()
    except OSError:
        # Fallback for systems where getlogin() doesn't work
        current_user = os.environ.get('USER', os.environ.get('USERNAME', 'pi'))
    
    # Check if meshbot user exists
    try:
        result = subprocess.run(['id', 'meshbot'], capture_output=True, timeout=5)
        if result.returncode == 0:
            service_user = 'meshbot'
            print(f"{Colors.GREEN}Using dedicated meshbot user{Colors.RESET}")
        else:
            service_user = current_user
            print(f"{Colors.YELLOW}Using current user: {current_user}{Colors.RESET}")
            print(f"{Colors.YELLOW}Note: For production, consider creating a dedicated 'meshbot' user{Colors.RESET}")
    except Exception:
        service_user = current_user
        print(f"{Colors.YELLOW}Using current user: {current_user}{Colors.RESET}")
    
    # Read service template
    service_template = Path('etc/mesh_bot.tmp')
    if not service_template.exists():
        print(f"{Colors.RED}Service template not found: {service_template}{Colors.RESET}")
        return False
    
    # Read and modify service file
    with open(service_template, 'r') as f:
        service_content = f.read()
    
    # Replace placeholders
    service_content = service_content.replace('/dir/', project_path + '/')
    service_content = service_content.replace('User=pi', f'User={service_user}')
    service_content = service_content.replace('Group=pi', f'Group={service_user}')
    service_content = service_content.replace('ExecStart=python3 mesh_bot.py', f'ExecStart={exec_start}')
    
    # Write service file
    service_file = Path('etc/mesh_bot.service')
    with open(service_file, 'w') as f:
        f.write(service_content)
    
    print(f"{Colors.GREEN}Service file created: {service_file}{Colors.RESET}")
    
    # Instructions for user
    print(f"\n{Colors.BOLD}To complete auto-start setup, run these commands:{Colors.RESET}")
    print(f"{Colors.BLUE}sudo cp {service_file} /etc/systemd/system/mesh_bot.service{Colors.RESET}")
    print(f"{Colors.BLUE}sudo systemctl daemon-reload{Colors.RESET}")
    print(f"{Colors.BLUE}sudo systemctl enable mesh_bot.service{Colors.RESET}")
    print(f"{Colors.BLUE}sudo systemctl start mesh_bot.service{Colors.RESET}")
    print(f"\n{Colors.BOLD}To check service status:{Colors.RESET}")
    print(f"{Colors.BLUE}sudo systemctl status mesh_bot.service{Colors.RESET}")
    print(f"\n{Colors.BOLD}To view logs:{Colors.RESET}")
    print(f"{Colors.BLUE}sudo journalctl -u mesh_bot.service -f{Colors.RESET}")
    
    # Ask if user wants to run commands now
    run_now = get_user_input(
        "\nDo you want to run these commands now? (requires sudo) (y/n)",
        "n",
        lambda x: x.lower() in ['y', 'n', 'yes', 'no']
    )
    
    if run_now.lower() in ['y', 'yes']:
        try:
            print(f"\n{Colors.BLUE}Copying service file...{Colors.RESET}")
            subprocess.run(['sudo', 'cp', str(service_file), '/etc/systemd/system/mesh_bot.service'], check=True)
            
            print(f"{Colors.BLUE}Reloading systemd...{Colors.RESET}")
            subprocess.run(['sudo', 'systemctl', 'daemon-reload'], check=True)
            
            print(f"{Colors.BLUE}Enabling service...{Colors.RESET}")
            subprocess.run(['sudo', 'systemctl', 'enable', 'mesh_bot.service'], check=True)
            
            print(f"{Colors.GREEN}Auto-start configured successfully!{Colors.RESET}")
            print(f"{Colors.YELLOW}Note: The service will start automatically on next boot.{Colors.RESET}")
            print(f"{Colors.YELLOW}To start it now, run: sudo systemctl start mesh_bot.service{Colors.RESET}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"{Colors.RED}Error running commands: {e}{Colors.RESET}")
            print(f"{Colors.YELLOW}Please run the commands manually (see instructions above){Colors.RESET}")
            return False
        except FileNotFoundError:
            print(f"{Colors.RED}sudo command not found. Please run the commands manually.{Colors.RESET}")
            return False
    else:
        print(f"{Colors.YELLOW}Please run the commands manually to enable auto-start.{Colors.RESET}")
        return False

def main():
    """Run the configuration wizard."""
    print(f"{Colors.BOLD}Meshing Around Configuration Wizard{Colors.RESET}")
    print("This wizard will help you configure your bot.\n")
    
    # Check if config.ini already exists
    config_file = Path('config.ini')
    if config_file.exists():
        overwrite = input(f"{Colors.YELLOW}config.ini already exists. Overwrite? (y/n): {Colors.RESET}").strip().lower()
        if overwrite not in ['y', 'yes']:
            print("Cancelled.")
            return 0
    
    # Load template
    template_file = Path('config.template')
    if not template_file.exists():
        print(f"{Colors.RED}Error: config.template not found!{Colors.RESET}")
        return 1
    
    config = configparser.ConfigParser()
    config.read(template_file)
    
    # Run configuration steps
    try:
        configure_interface(config)
        configure_general(config)
        configure_web_ui(config)
        configure_mcp_server(config)
        configure_autostart()
        
        # Save configuration
        print_header("Saving Configuration")
        with open('config.ini', 'w') as f:
            config.write(f)
        
        print(f"{Colors.GREEN}Configuration saved to config.ini{Colors.RESET}")
        print(f"\n{Colors.BOLD}Next steps:{Colors.RESET}")
        print("1. Review config.ini and adjust any settings as needed")
        
        # Check if TCP interface is configured
        if config.get('interface', {}).get('type', '').lower() == 'tcp':
            hostname = config.get('interface', {}).get('hostname', '')
            print(f"2. Ensure meshtasticd is running and accessible at {hostname}")
            if 'meshtasticd' in hostname.lower():
                print(f"   {Colors.BLUE}Note: If using Docker, ensure meshtasticd container is running{Colors.RESET}")
                print(f"   {Colors.BLUE}     and both containers are on the same Docker network{Colors.RESET}")
        else:
            print("2. Connect your Meshtastic device")
        
        if platform.system() == 'Linux':
            print("3. Run: python3 mesh_bot.py")
            print("   Or if auto-start was configured: sudo systemctl start mesh_bot.service")
        else:
            print("3. Run: python3 mesh_bot.py")
        
        return 0
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Configuration cancelled.{Colors.RESET}")
        return 1
    except Exception as e:
        print(f"{Colors.RED}Error: {e}{Colors.RESET}")
        return 1

if __name__ == '__main__':
    sys.exit(main())

