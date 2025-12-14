# Deployment Guide: Web UI & MCP Server

This guide explains how to deploy the new Web UI and MCP Server features to your Linux server running meshing-around.

## Prerequisites

- A GitHub account
- Git installed on both your development machine and Linux server
- SSH access to your Linux server

## Step 1: Push Changes to Your GitHub Fork

### 1.1 Check Current Git Status

In Cursor (or your terminal), check if you have a git repository:

```bash
git status
```

If you see "not a git repository", you need to initialize it:

```bash
git init
git remote add origin https://github.com/YOUR_USERNAME/meshing-around.git
```

### 1.2 Fork the Original Repository (if not already done)

1. Go to https://github.com/SpudGunMan/meshing-around
2. Click the "Fork" button in the top right
3. This creates your own copy at `https://github.com/YOUR_USERNAME/meshing-around`

### 1.3 Configure Git Remote (if needed)

If you already have a fork, set up your remotes:

```bash
# Check current remotes
git remote -v

# If you need to add your fork as origin
git remote set-url origin https://github.com/YOUR_USERNAME/meshing-around.git

# Add the original repo as upstream (to pull updates later)
git remote add upstream https://github.com/SpudGunMan/meshing-around.git
```

### 1.4 Commit and Push Your Changes

```bash
# Stage all changes
git add .

# Commit with a descriptive message
git commit -m "Add Web UI and MCP Server modules for dashboard and configuration"

# Push to your fork
git push origin main
```

If you're on a different branch:

```bash
git push origin YOUR_BRANCH_NAME
```

### 1.5 Push from Cursor (Alternative)

Cursor has built-in Git support:

1. Click the Source Control icon (left sidebar) or press `Ctrl+Shift+G`
2. Stage your changes (click the `+` next to files)
3. Enter a commit message
4. Click the checkmark to commit
5. Click the `...` menu and select "Push" or use the sync button

## Step 2: Update Your Linux Server

### 2.1 SSH into Your Server

```bash
ssh user@your-server-ip
```

### 2.2 Navigate to Your meshing-around Directory

```bash
cd /opt/meshing-around
# or wherever you installed it
cd ~/meshing-around
```

### 2.3 Configure Git Remotes (First Time Only)

If this is the first time setting up your fork:

```bash
# Check current remote
git remote -v

# If it points to the original repo, update it
git remote set-url origin https://github.com/YOUR_USERNAME/meshing-around.git

# Add upstream for pulling updates from original repo
git remote add upstream https://github.com/SpudGunMan/meshing-around.git
```

### 2.4 Pull Your Changes

```bash
# Stop the bot service first (if running as a service)
sudo systemctl stop mesh_bot

# Pull your changes
git pull origin main

# If you're on a different branch
git pull origin YOUR_BRANCH_NAME
```

### 2.5 Restart the Bot

```bash
# If running as a service
sudo systemctl start mesh_bot
sudo systemctl status mesh_bot

# Or if running manually
python3 mesh_bot.py
```

## Step 3: Syncing with Upstream (Original Repo)

To keep your fork updated with the original SpudGunMan repository:

### 3.1 Fetch Updates from Upstream

```bash
# Fetch latest changes from original repo
git fetch upstream

# Merge upstream changes into your local branch
git merge upstream/main

# Or use rebase to keep a cleaner history
git rebase upstream/main
```

### 3.2 Push Updated Fork to GitHub

```bash
git push origin main
```

### 3.3 Update Server from Your Fork

```bash
# On your server
sudo systemctl stop mesh_bot
git pull origin main
sudo systemctl start mesh_bot
```

## Step 4: Automated Update Script

You can create a simple update script on your server:

```bash
#!/bin/bash
# update_from_fork.sh

cd /opt/meshing-around
sudo systemctl stop mesh_bot
git pull origin main
sudo systemctl start mesh_bot
echo "Update complete!"
```

Make it executable:

```bash
chmod +x update_from_fork.sh
```

Then run:

```bash
./update_from_fork.sh
```

## Step 5: Verify Installation

After updating, verify the new features are working:

1. **Check Web UI**: Open `http://YOUR_SERVER_IP:8420` in a browser
2. **Check MCP API**: Test `http://YOUR_SERVER_IP:8421/api/nodes`
3. **Check Logs**: 
   ```bash
   sudo journalctl -u mesh_bot -f
   # or
   tail -f logs/mesh_bot.log
   ```

You should see:
```
System: Web UI started on port 8420
```

## Troubleshooting

### Git Authentication Issues

If you get authentication errors when pushing:

1. **Use SSH instead of HTTPS**:
   ```bash
   git remote set-url origin git@github.com:YOUR_USERNAME/meshing-around.git
   ```

2. **Or use a Personal Access Token**:
   - Go to GitHub Settings > Developer settings > Personal access tokens
   - Create a token with `repo` permissions
   - Use it as your password when pushing

### Merge Conflicts

If you get merge conflicts when pulling:

```bash
# See what files have conflicts
git status

# Resolve conflicts manually, then:
git add .
git commit -m "Resolved merge conflicts"
git push origin main
```

### Service Won't Start

Check the service status:

```bash
sudo systemctl status mesh_bot
sudo journalctl -u mesh_bot -n 50
```

Common issues:
- Missing dependencies: `pip install -r requirements.txt`
- Port already in use: Check if port 8420 or 8421 is taken
- Permission issues: Check file permissions

## Quick Reference Commands

```bash
# On your development machine (Cursor/Windows)
git add .
git commit -m "Your commit message"
git push origin main

# On your Linux server
cd /opt/meshing-around
sudo systemctl stop mesh_bot
git pull origin main
sudo systemctl start mesh_bot

# Sync with upstream (original repo)
git fetch upstream
git merge upstream/main
git push origin main
```

## Next Steps

- Access the Web UI at `http://YOUR_SERVER_IP:8420`
- Configure settings through the web interface
- Monitor your mesh network via the dashboard
- Use the MCP API for integrations: `http://YOUR_SERVER_IP:8421/api/`

