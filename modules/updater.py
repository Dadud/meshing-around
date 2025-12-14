#!/usr/bin/env python3
"""
Auto-Update Module for Meshing-Around
Handles automatic updates from the correct git repository (original or fork)
"""

import subprocess
import os
import sys
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

def get_git_info() -> Dict[str, Any]:
    """
    Get current git repository information.
    Returns remote URL, branch, and commit info.
    """
    info = {
        "is_git_repo": False,
        "remote_url": None,
        "remote_name": "origin",
        "branch": None,
        "current_commit": None,
        "remote_commit": None,
        "has_updates": False,
        "error": None
    }
    
    try:
        # Check if we're in a git repository
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            info["error"] = "Not a git repository"
            return info
        
        info["is_git_repo"] = True
        repo_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Get current branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            info["branch"] = result.stdout.strip()
        
        # Get current commit
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            info["current_commit"] = result.stdout.strip()[:7]
        
        # Get remote URL
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            info["remote_url"] = result.stdout.strip()
            # Extract repo owner/name from URL
            if "github.com" in info["remote_url"]:
                parts = info["remote_url"].replace(".git", "").split("/")
                if len(parts) >= 2:
                    info["repo_owner"] = parts[-2]
                    info["repo_name"] = parts[-1]
        
        # Check for updates
        if info["branch"]:
            # Fetch latest
            subprocess.run(
                ["git", "fetch", "origin", "--quiet"],
                cwd=repo_path,
                capture_output=True,
                timeout=10
            )
            
            # Compare local vs remote
            result = subprocess.run(
                ["git", "rev-parse", f"origin/{info['branch']}"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                info["remote_commit"] = result.stdout.strip()[:7]
                info["has_updates"] = info["current_commit"] != info["remote_commit"]
        
    except subprocess.TimeoutExpired:
        info["error"] = "Git operation timed out"
    except FileNotFoundError:
        info["error"] = "Git not found - install git to enable updates"
    except Exception as e:
        info["error"] = str(e)
    
    return info


def check_for_updates() -> Dict[str, Any]:
    """
    Check if updates are available from the current remote.
    """
    return get_git_info()


def perform_update(dry_run: bool = False, reset_on_conflict: bool = False) -> Dict[str, Any]:
    """
    Perform an update from the current git remote.
    
    Args:
        dry_run: If True, only check what would be updated without making changes
        reset_on_conflict: If True, reset to remote on conflicts (discards local changes)
    
    Returns:
        Dictionary with update status and messages
    """
    result = {
        "success": False,
        "message": "",
        "output": [],
        "error": None,
        "updated": False,
        "conflicts": False
    }
    
    try:
        repo_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Get current branch
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if branch_result.returncode != 0:
            result["error"] = "Could not determine current branch"
            return result
        
        current_branch = branch_result.stdout.strip()
        
        if dry_run:
            # Just check what would be updated
            result["message"] = f"Dry run: Would update from origin/{current_branch}"
            result["success"] = True
            return result
        
        # Fetch latest changes
        fetch_result = subprocess.run(
            ["git", "fetch", "origin"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if fetch_result.returncode != 0:
            result["error"] = f"Failed to fetch: {fetch_result.stderr}"
            return result
        
        result["output"].append("Fetched latest changes from remote")
        
        # Try to pull with rebase
        pull_result = subprocess.run(
            ["git", "pull", "origin", current_branch, "--rebase"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if pull_result.returncode != 0:
            result["conflicts"] = True
            result["output"].append("Update conflicts detected")
            
            if reset_on_conflict:
                # Reset to remote
                reset_result = subprocess.run(
                    ["git", "reset", "--hard", f"origin/{current_branch}"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if reset_result.returncode == 0:
                    result["output"].append("Reset to remote version (local changes discarded)")
                    result["success"] = True
                    result["updated"] = True
                else:
                    result["error"] = f"Reset failed: {reset_result.stderr}"
            else:
                result["error"] = "Update conflicts - local changes would be overwritten"
                result["message"] = "Update failed due to conflicts. Use reset_on_conflict=True to discard local changes."
        else:
            result["output"].append("Successfully pulled latest changes")
            result["success"] = True
            result["updated"] = True
        
        # Get new commit info
        commit_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        if commit_result.returncode == 0:
            result["new_commit"] = commit_result.stdout.strip()[:7]
        
        # If update was successful, attempt to restart the bot
        if result["success"] and result["updated"]:
            result["restart_required"] = True
            result["restart_message"] = restart_bot()
        
    except subprocess.TimeoutExpired:
        result["error"] = "Update operation timed out"
    except Exception as e:
        result["error"] = str(e)
    
    return result


def restart_bot() -> str:
    """
    Attempt to restart the bot using systemd if available, otherwise provide instructions.
    
    Returns:
        Message about restart status
    """
    try:
        # Check if running as systemd service
        service_name = "mesh_bot"  # Common service name
        check_result = subprocess.run(
            ["systemctl", "is-active", "--quiet", service_name],
            capture_output=True,
            timeout=5
        )
        
        if check_result.returncode == 0:
            # Service is active, restart it
            restart_result = subprocess.run(
                ["sudo", "systemctl", "restart", service_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            if restart_result.returncode == 0:
                return f"Bot restarted via systemd service '{service_name}'"
            else:
                return f"Failed to restart via systemd: {restart_result.stderr.strip()}. You may need to restart manually."
        else:
            # Try other common service names
            for alt_name in ["meshing-around", "meshtastic-bot"]:
                check_alt = subprocess.run(
                    ["systemctl", "is-active", "--quiet", alt_name],
                    capture_output=True,
                    timeout=5
                )
                if check_alt.returncode == 0:
                    restart_result = subprocess.run(
                        ["sudo", "systemctl", "restart", alt_name],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if restart_result.returncode == 0:
                        return f"Bot restarted via systemd service '{alt_name}'"
            
            # Not running as systemd service
            return "Bot is not running as a systemd service. Please restart manually: 'sudo systemctl restart mesh_bot' or restart your bot process."
            
    except FileNotFoundError:
        return "systemctl not found. Please restart the bot manually."
    except subprocess.TimeoutExpired:
        return "Restart check timed out. Please restart the bot manually."
    except Exception as e:
        return f"Could not determine restart method: {str(e)}. Please restart the bot manually."


def get_changelog(limit: int = 20) -> Dict[str, Any]:
    """
    Get recent commit history (changelog).
    
    Args:
        limit: Maximum number of commits to return
    
    Returns:
        Dictionary with changelog data
    """
    result = {
        "success": False,
        "commits": [],
        "error": None
    }
    
    try:
        repo_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Get commit log
        log_result = subprocess.run(
            ["git", "log", f"--max-count={limit}", "--pretty=format:%h|%an|%ad|%s", "--date=short"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if log_result.returncode == 0:
            commits = []
            for line in log_result.stdout.strip().split('\n'):
                if not line:
                    continue
                parts = line.split('|', 3)
                if len(parts) >= 4:
                    commits.append({
                        "hash": parts[0],
                        "author": parts[1],
                        "date": parts[2],
                        "message": parts[3]
                    })
            result["commits"] = commits
            result["success"] = True
        else:
            result["error"] = f"Failed to get changelog: {log_result.stderr}"
            
    except subprocess.TimeoutExpired:
        result["error"] = "Changelog operation timed out"
    except Exception as e:
        result["error"] = str(e)
    
    return result


def get_update_status() -> Dict[str, Any]:
    """
    Get comprehensive update status including git info and update availability.
    """
    git_info = get_git_info()
    
    status = {
        "git_info": git_info,
        "can_update": git_info["is_git_repo"] and git_info.get("branch") is not None,
        "update_available": git_info.get("has_updates", False),
        "timestamp": datetime.now().isoformat()
    }
    
    return status


if __name__ == "__main__":
    # Test the update module
    import json
    print("Checking for updates...")
    status = get_update_status()
    print(json.dumps(status, indent=2, default=str))

