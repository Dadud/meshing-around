#!/usr/bin/env python3
"""
Post-installation verification script.
Verifies that the installation completed successfully.
"""

import sys
import os
import importlib
import configparser
from pathlib import Path

# Color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_success(message):
    print(f"{Colors.GREEN}✓{Colors.RESET} {message}")

def print_error(message):
    print(f"{Colors.RED}✗{Colors.RESET} {message}")

def print_warning(message):
    print(f"{Colors.YELLOW}⚠{Colors.RESET} {message}")

def print_info(message):
    print(f"{Colors.BLUE}ℹ{Colors.RESET} {message}")

def check_config_file():
    """Check if config.ini exists and is valid."""
    config_file = Path('config.ini')
    if not config_file.exists():
        print_error("config.ini: Not found")
        return False
    
    try:
        config = configparser.ConfigParser()
        config.read(config_file)
        
        # Check for required sections
        required_sections = ['general', 'interface']
        missing_sections = [s for s in required_sections if s not in config.sections()]
        
        if missing_sections:
            print_error(f"config.ini: Missing sections: {', '.join(missing_sections)}")
            return False
        
        # Check interface configuration
        if 'type' not in config['interface']:
            print_error("config.ini: [interface] section missing 'type'")
            return False
        
        print_success("config.ini: Valid")
        return True
    except Exception as e:
        print_error(f"config.ini: Invalid format - {e}")
        return False

def check_dependencies():
    """Check if all required dependencies are installed."""
    req_file = Path('requirements.txt')
    if not req_file.exists():
        print_error("requirements.txt: Not found")
        return False
    
    required_packages = []
    with open(req_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                # Extract package name (before any version specifiers)
                pkg_name = line.split('>=')[0].split('==')[0].split('<=')[0].split('>')[0].split('<')[0].strip()
                if pkg_name:
                    required_packages.append(pkg_name)
    
    missing_packages = []
    for pkg in required_packages:
        try:
            # Try importing the package
            importlib.import_module(pkg.replace('-', '_'))
        except ImportError:
            missing_packages.append(pkg)
    
    if missing_packages:
        print_error(f"Missing packages: {', '.join(missing_packages)}")
        print_info("Install with: pip install -r requirements.txt")
        return False
    
    print_success(f"All dependencies installed ({len(required_packages)} packages)")
    return True

def check_directories():
    """Check if required directories exist."""
    required_dirs = ['data', 'logs', 'modules']
    missing_dirs = []
    
    for dir_name in required_dirs:
        dir_path = Path(dir_name)
        if not dir_path.exists():
            missing_dirs.append(dir_name)
        elif not dir_path.is_dir():
            print_error(f"{dir_name}: Exists but is not a directory")
            return False
    
    if missing_dirs:
        print_error(f"Missing directories: {', '.join(missing_dirs)}")
        return False
    
    print_success("Required directories exist")
    return True

def check_main_files():
    """Check if main Python files exist."""
    required_files = ['mesh_bot.py', 'modules/system.py', 'modules/settings.py']
    missing_files = []
    
    for file_name in required_files:
        if not Path(file_name).exists():
            missing_files.append(file_name)
    
    if missing_files:
        print_error(f"Missing files: {', '.join(missing_files)}")
        return False
    
    print_success("Main files present")
    return True

def check_venv():
    """Check if virtual environment exists (if expected)."""
    venv_path = Path('venv')
    if venv_path.exists():
        if (venv_path / 'bin' / 'activate').exists() or (venv_path / 'Scripts' / 'activate').exists():
            print_success("Virtual environment: Found")
            return True
        else:
            print_warning("Virtual environment: Incomplete")
            return True  # Don't fail
    else:
        print_info("Virtual environment: Not found (using system Python)")
        return True  # Optional

def check_imports():
    """Check if main modules can be imported."""
    try:
        # Try importing key modules
        import meshtastic
        print_success("meshtastic: Can be imported")
    except ImportError as e:
        print_error(f"meshtastic: Cannot be imported - {e}")
        return False
    
    try:
        sys.path.insert(0, str(Path.cwd()))
        from modules import settings
        print_success("modules.settings: Can be imported")
    except ImportError as e:
        print_error(f"modules.settings: Cannot be imported - {e}")
        return False
    
    return True

def check_config_values():
    """Check if configuration has reasonable values."""
    try:
        config = configparser.ConfigParser()
        config.read('config.ini')
        
        # Check interface type
        if 'interface' in config.sections():
            interface_type = config['interface'].get('type', '').lower()
            if interface_type not in ['serial', 'tcp', 'ble']:
                print_warning(f"Interface type '{interface_type}' may be invalid")
            else:
                print_success(f"Interface type: {interface_type}")
        
        # Check location values
        if 'general' in config.sections():
            lat = config['general'].get('latitudeValue', '')
            lon = config['general'].get('longitudeValue', '')
            if lat and lon:
                try:
                    float(lat)
                    float(lon)
                    print_success("Location values: Valid")
                except ValueError:
                    print_warning("Location values: Invalid format")
        
        return True
    except Exception as e:
        print_warning(f"Could not validate config values: {e}")
        return True  # Don't fail

def main():
    """Run all verification checks."""
    print(f"{Colors.BOLD}Post-Installation Verification{Colors.RESET}\n")
    
    checks = [
        ("Configuration File", check_config_file),
        ("Dependencies", check_dependencies),
        ("Directories", check_directories),
        ("Main Files", check_main_files),
        ("Virtual Environment", check_venv),
        ("Module Imports", check_imports),
        ("Configuration Values", check_config_values),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print_error(f"{name}: Check failed with error: {e}")
            results.append((name, False))
    
    print(f"\n{Colors.BOLD}Summary:{Colors.RESET}")
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    critical_failures = [
        name for name, result in results 
        if not result and name in ["Configuration File", "Dependencies", "Directories", "Main Files", "Module Imports"]
    ]
    
    if critical_failures:
        print_error(f"Critical checks failed: {', '.join(critical_failures)}")
        print_info("Please review the installation and fix the issues above.")
        return 1
    elif passed == total:
        print_success(f"All checks passed ({passed}/{total})")
        print_info("Installation appears to be successful!")
        return 0
    else:
        print_warning(f"Some checks failed ({passed}/{total} passed)")
        print_info("Installation may be incomplete. Review warnings above.")
        return 0

if __name__ == '__main__':
    sys.exit(main())

