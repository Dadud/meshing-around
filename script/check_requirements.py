#!/usr/bin/env python3
"""
Pre-flight checks for Meshing Around installation.
Validates system requirements before installation begins.
"""

import sys
import os
import platform
import subprocess
import shutil
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

def check_python_version():
    """Check if Python version is 3.8 or later."""
    version = sys.version_info
    if version.major == 3 and version.minor >= 8:
        print_success(f"Python {version.major}.{version.minor}.{version.micro} (required: 3.8+)")
        return True
    else:
        print_error(f"Python {version.major}.{version.minor}.{version.micro} (required: 3.8+)")
        return False

def check_pip():
    """Check if pip is available."""
    if shutil.which('pip') or shutil.which('pip3'):
        print_success("pip is available")
        return True
    else:
        print_error("pip is not installed")
        print_info("Install with: python3 -m ensurepip --upgrade")
        return False

def check_git():
    """Check if git is available."""
    if shutil.which('git'):
        try:
            result = subprocess.run(['git', '--version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print_success(f"Git is available: {result.stdout.strip()}")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    print_warning("Git is not available (optional, but recommended for updates)")
    return True  # Git is optional

def check_disk_space(path='.', required_mb=500):
    """Check if there's enough disk space."""
    try:
        if platform.system() == 'Windows':
            import shutil
            total, used, free = shutil.disk_usage(path)
        else:
            stat = os.statvfs(path)
            free = stat.f_bavail * stat.f_frsize
        
        free_mb = free / (1024 * 1024)
        if free_mb >= required_mb:
            print_success(f"Disk space: {free_mb:.0f} MB free (required: {required_mb} MB)")
            return True
        else:
            print_error(f"Disk space: {free_mb:.0f} MB free (required: {required_mb} MB)")
            return False
    except Exception as e:
        print_warning(f"Could not check disk space: {e}")
        return True  # Don't fail on this

def check_write_permissions(path='.'):
    """Check if we have write permissions."""
    try:
        test_file = os.path.join(path, '.write_test')
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        print_success(f"Write permissions: OK for {os.path.abspath(path)}")
        return True
    except PermissionError:
        print_error(f"Write permissions: No write access to {os.path.abspath(path)}")
        return False
    except Exception as e:
        print_warning(f"Could not check write permissions: {e}")
        return True

def check_network_connectivity():
    """Check if we can reach the internet (for location detection)."""
    import socket
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        print_success("Network connectivity: OK")
        return True
    except OSError:
        print_warning("Network connectivity: No internet connection (location auto-detection will fail)")
        return True  # Don't fail, just warn

def check_serial_access():
    """Check if we can access serial ports (Linux/Mac)."""
    if platform.system() == 'Windows':
        print_info("Serial port check: Skipped on Windows (COM ports available)")
        return True
    
    # Check if user is in dialout group (Linux)
    if platform.system() == 'Linux':
        try:
            import grp
            groups = [g.gr_name for g in grp.getgrall() if os.getlogin() in g.gr_mem]
            groups.append(grp.getgrgid(os.getgid()).gr_name)
            
            if 'dialout' in groups or 'tty' in groups:
                print_success("Serial port access: User in dialout/tty group")
                return True
            else:
                print_warning("Serial port access: User not in dialout/tty group")
                print_info("Add user to group with: sudo usermod -a -G dialout $USER")
                return True  # Don't fail, just warn
        except Exception:
            print_warning("Could not check serial port groups")
            return True
    
    return True

def check_existing_installation():
    """Check if there's an existing installation."""
    config_file = Path('config.ini')
    if config_file.exists():
        print_warning("Existing config.ini found")
        print_info("Backup existing config before installing: cp config.ini config.ini.backup")
        return False  # Fail to prevent overwriting
    return True

def check_venv_module():
    """Check if venv module is available."""
    try:
        import venv
        print_success("Python venv module: Available")
        return True
    except ImportError:
        print_warning("Python venv module: Not available")
        print_info("Install with: sudo apt-get install python3-venv (Debian/Ubuntu)")
        return True  # Optional, just warn

def check_requirements_file():
    """Check if requirements.txt exists."""
    req_file = Path('requirements.txt')
    if req_file.exists():
        print_success("requirements.txt: Found")
        return True
    else:
        print_error("requirements.txt: Not found")
        return False

def main():
    """Run all pre-flight checks."""
    print(f"{Colors.BOLD}Pre-Flight Checks for Meshing Around Installation{Colors.RESET}\n")
    
    checks = [
        ("Python Version", check_python_version),
        ("pip", check_pip),
        ("Git", check_git),
        ("Disk Space", check_disk_space),
        ("Write Permissions", check_write_permissions),
        ("Network Connectivity", check_network_connectivity),
        ("Serial Port Access", check_serial_access),
        ("Existing Installation", check_existing_installation),
        ("Python venv Module", check_venv_module),
        ("Requirements File", check_requirements_file),
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
        if not result and name in ["Python Version", "pip", "Write Permissions", "Requirements File"]
    ]
    
    if critical_failures:
        print_error(f"Critical checks failed: {', '.join(critical_failures)}")
        print_info("Please fix the issues above before proceeding with installation.")
        return 1
    elif passed == total:
        print_success(f"All checks passed ({passed}/{total})")
        return 0
    else:
        print_warning(f"Some optional checks failed ({passed}/{total} passed)")
        print_info("You can proceed, but some features may not work.")
        return 0

if __name__ == '__main__':
    sys.exit(main())

