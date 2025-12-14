# Fork and Deploy Guide: Your Own Repository

This guide shows you how to fork meshing-around to your own GitHub account and push your Web UI changes there.

## Step 1: Fork the Repository on GitHub

1. Go to https://github.com/SpudGunMan/meshing-around
2. Click the **"Fork"** button in the top right corner
3. Choose your GitHub account as the destination
4. Wait for GitHub to create your fork at: `https://github.com/YOUR_USERNAME/meshing-around`

## Step 2: Set Up Your Local Repository

### 2.1 Check Current Git Status

In Cursor, open the terminal (`` Ctrl+` ``) and run:

```bash
git status
```

### 2.2 Configure Git Remotes

You need to set up two remotes:
- **origin**: Your fork (where you push your changes)
- **upstream**: Original repo (to pull updates from SpudGunMan)

```bash
# Check what remotes you currently have
git remote -v

# If you see the original repo, remove it
git remote remove origin

# Add YOUR fork as origin (replace YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/meshing-around.git

# Add the original repo as upstream (to pull updates later)
git remote add upstream https://github.com/SpudGunMan/meshing-around.git

# Verify your remotes are correct
git remote -v
```

You should see:
```
origin    https://github.com/YOUR_USERNAME/meshing-around.git (fetch)
origin    https://github.com/YOUR_USERNAME/meshing-around.git (push)
upstream  https://github.com/SpudGunMan/meshing-around.git (fetch)
upstream  https://github.com/SpudGunMan/meshing-around.git (push)
```

### 2.3 If You Don't Have Git Initialized Yet

If `git status` says "not a git repository":

```bash
# Initialize git
git init

# Add all files
git add .

# Make your first commit
git commit -m "Initial commit with Web UI and MCP Server"

# Add your fork as origin
git remote add origin https://github.com/YOUR_USERNAME/meshing-around.git

# Add upstream
git remote add upstream https://github.com/SpudGunMan/meshing-around.git
```

## Step 3: Push to Your Fork

### 3.1 Commit Your Changes

```bash
# Stage all your changes
git add .

# Commit with a descriptive message
git commit -m "Add Web UI and MCP Server modules for dashboard and configuration"
```

### 3.2 Push to Your Fork

```bash
# Push to your fork (origin)
git push -u origin main
```

If you get an error about the branch not existing on GitHub, you might need to:

```bash
# Check what branch you're on
git branch

# If you're on 'master' instead of 'main'
git branch -M main
git push -u origin main
```

### 3.3 Using Cursor's Git UI

1. Click the **Source Control** icon (left sidebar) or press `Ctrl+Shift+G`
2. You should see your changes listed
3. Click the **+** next to files to stage them (or click **+** next to "Changes" to stage all)
4. Type a commit message: "Add Web UI and MCP Server modules"
5. Click the **checkmark** (✓) to commit
6. Click the **...** menu (three dots) at the top
7. Select **"Push"** or click the sync icon

**Important**: Make sure it says "Push to origin" not "Push to upstream"!

## Step 4: Verify You Pushed to Your Fork

1. Go to `https://github.com/YOUR_USERNAME/meshing-around` in your browser
2. You should see your commit with the message "Add Web UI and MCP Server modules"
3. The files `modules/web_ui.py` and `modules/mcp_server.py` should be there

## Step 5: Set Up Your Linux Server

### 5.1 SSH into Your Server

```bash
ssh user@your-server-ip
```

### 5.2 Navigate to meshing-around Directory

```bash
cd /opt/meshing-around
# or
cd ~/meshing-around
```

### 5.3 Configure Server to Use Your Fork

```bash
# Check current remote
git remote -v

# Change origin to point to YOUR fork
git remote set-url origin https://github.com/YOUR_USERNAME/meshing-around.git

# Add upstream for pulling updates from original repo
git remote add upstream https://github.com/SpudGunMan/meshing-around.git

# Verify
git remote -v
```

### 5.4 Pull Your Changes

```bash
# Stop the bot service
sudo systemctl stop mesh_bot

# Pull from YOUR fork
git pull origin main

# Restart the bot
sudo systemctl start mesh_bot

# Check status
sudo systemctl status mesh_bot
```

## Step 6: Keep Your Fork Updated with Original Repo

To get updates from SpudGunMan's repo while keeping your changes:

### On Your Development Machine (Cursor):

```bash
# Fetch updates from original repo
git fetch upstream

# Merge into your local branch
git merge upstream/main

# Push to YOUR fork
git push origin main
```

### On Your Linux Server:

```bash
# Pull from YOUR fork (which now has the merged updates)
sudo systemctl stop mesh_bot
git pull origin main
sudo systemctl start mesh_bot
```

## Quick Reference

### Your Workflow:

1. **Make changes in Cursor**
2. **Commit**: `git add . && git commit -m "Your message"`
3. **Push to YOUR fork**: `git push origin main`
4. **On server**: `git pull origin main`

### To Get Updates from Original Repo:

1. **Fetch upstream**: `git fetch upstream`
2. **Merge**: `git merge upstream/main`
3. **Push to your fork**: `git push origin main`
4. **On server**: `git pull origin main`

## Troubleshooting

### "Permission denied" when pushing

If you get authentication errors:

**Option 1: Use SSH (Recommended)**
```bash
# Generate SSH key if you don't have one
ssh-keygen -t ed25519 -C "your_email@example.com"

# Add to GitHub: Settings > SSH and GPG keys > New SSH key
# Copy contents of ~/.ssh/id_ed25519.pub

# Change remote to SSH
git remote set-url origin git@github.com:YOUR_USERNAME/meshing-around.git
```

**Option 2: Use Personal Access Token**
1. GitHub Settings > Developer settings > Personal access tokens > Tokens (classic)
2. Generate new token with `repo` permissions
3. Use token as password when pushing

### "Branch 'main' does not exist"

If GitHub created your fork with a different default branch:

```bash
# Check what branch exists on GitHub
git ls-remote --heads origin

# Push to the correct branch (might be 'master')
git push -u origin master
# or rename your local branch
git branch -M master
git push -u origin master
```

### Verify You're Pushing to the Right Place

Always check before pushing:

```bash
git remote -v
```

Should show YOUR username in the URL, not SpudGunMan!

## Summary

- **Your Fork**: `https://github.com/YOUR_USERNAME/meshing-around` ← You push here
- **Original Repo**: `https://github.com/SpudGunMan/meshing-around` ← You pull updates from here
- **Your Server**: Pulls from YOUR fork, not the original

This way, all your changes stay in your own repository, and you can still get updates from the original project!

