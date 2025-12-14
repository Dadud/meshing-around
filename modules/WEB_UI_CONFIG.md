# Adding Configuration Options to the Web UI

This guide explains how to add configuration options for your module to the Web UI's configuration interface.

## Overview

The Web UI automatically displays all configuration options from `config.ini` in a user-friendly interface. To make your module's options appear correctly, you need to:

1. Add your configuration section to `config.template`
2. Add user-friendly labels and descriptions to the Web UI
3. (Optional) Group your settings logically

## Step 1: Add Configuration to config.template

First, ensure your module's configuration section exists in `config.template`:

```ini
[myModule]
enabled = True
setting1 = value1
setting2 = value2
```

## Step 2: Add User-Friendly Labels

The Web UI uses a `configLabels` object in `modules/web_ui.py` to provide user-friendly names and descriptions. Find the `configLabels` object (around line 1935) and add your module:

```javascript
'myModule': {
    'enabled': { label: 'Enable My Module', desc: 'Turn the My Module feature on or off' },
    'setting1': { label: 'Setting One', desc: 'Description of what setting1 does' },
    'setting2': { label: 'Setting Two', desc: 'Description of what setting2 does' }
}
```

### Label Guidelines

- **Labels**: Use clear, concise names (e.g., "Enable Feature" not "enabled")
- **Descriptions**: Explain what the setting does and when to use it
- **Boolean values**: Automatically become checkboxes
- **Password/API keys**: Automatically become password fields if the key contains "password", "key", "token", or "api"
- **Numbers**: Automatically become number inputs if the key contains "port", "channel", "interval", "timeout", "radius", or "altitude"

## Step 3: Group Your Settings (Optional)

To group your module's settings with related features, add it to the `configGroups` object (around line 2033):

```javascript
const configGroups = {
    'My Feature Category': ['myModule', 'relatedModule'],
    // ... other groups
};
```

### Existing Groups

- **Web Interface**: `web_ui`, `mcp_server`
- **Radio Interfaces**: `interface`, `interface2`, etc.
- **Basic Bot Settings**: `general`
- **Messaging**: `messagingSettings`, `StoreForward`
- **Bulletin Board System**: `bbs`
- **Location & Weather**: `location`
- **Alerts & Monitoring**: `sentry`, `emergencyHandler`
- **Games & Entertainment**: `games`
- **Information Sources**: `rss`, `wikipedia`, `news`
- **AI & Language**: `ollama`, `OpenWebUI`
- **Advanced Features**: `repeater`, `scheduler`, `checklist`, `inventory`, `qrz`
- **Radio Monitoring**: `radioMon`, `fileMon`
- **Email & Communication**: `smtp`
- **Logging & Debugging**: `logging`

## Step 4: Handle Special Cases

### Boolean Values

Boolean values are automatically detected and displayed as checkboxes. The Web UI handles conversion between `True`/`False` strings and actual booleans.

### Multi-line Values

If a value contains `\n` or is longer than 100 characters, it automatically becomes a textarea.

### Sensitive Information

Fields containing "password", "key", "token", or "api" in their name automatically become password fields (masked input).

### Number Fields

Fields containing "port", "channel", "interval", "timeout", "radius", or "altitude" automatically become number inputs.

## Example: Complete Module Configuration

Here's a complete example for a hypothetical "Weather Alerts" module:

### 1. config.template

```ini
[weatherAlerts]
enabled = True
alert_threshold = 50
api_key = 
notification_channel = 2
```

### 2. Web UI configLabels (in web_ui.py)

```javascript
'weatherAlerts': {
    'enabled': { label: 'Enable Weather Alerts', desc: 'Turn on automatic weather alert notifications' },
    'alert_threshold': { label: 'Alert Threshold (mph)', desc: 'Wind speed threshold in miles per hour to trigger alerts' },
    'api_key': { label: 'Weather API Key', desc: 'API key for weather service (automatically masked)' },
    'notification_channel': { label: 'Notification Channel', desc: 'Channel number to send weather alerts to' }
}
```

### 3. Web UI configGroups (in web_ui.py)

```javascript
const configGroups = {
    'Alerts & Monitoring': ['sentry', 'emergencyHandler', 'weatherAlerts'],
    // ... other groups
};
```

## Testing Your Configuration

1. **Start the bot** with your module enabled
2. **Access the Web UI** at `http://your-server:8420`
3. **Navigate to the Config tab**
4. **Find your module** in the appropriate group (or "Other" if not grouped)
5. **Verify**:
   - Labels are user-friendly
   - Descriptions are clear
   - Input types are correct (checkbox, number, password, etc.)
   - Changes save correctly

## Advanced: Custom Input Types

If you need a custom input type not automatically detected, you can modify the `loadConfig()` function in `web_ui.py` to add special handling for your specific keys.

## Best Practices

1. **Clear Labels**: Use descriptive labels that users will understand
2. **Helpful Descriptions**: Explain what each setting does and provide context
3. **Logical Grouping**: Group related settings together
4. **Consistent Naming**: Follow existing naming conventions
5. **Default Values**: Ensure defaults in `config.template` are sensible
6. **Validation**: Consider adding validation in your module code

## Troubleshooting

### Settings Not Appearing

- Check that your section exists in `config.template`
- Verify the section name matches exactly (case-sensitive)
- Ensure the bot has read the config file

### Wrong Input Type

- Check if your key name matches the automatic detection patterns
- For booleans, ensure values are `True`/`False` (not `true`/`false` or `1`/`0`)

### Settings Not Saving

- Check that `write_config()` is being called correctly
- Verify file permissions on `config.ini`
- Check the browser console for JavaScript errors

## Need Help?

- Check existing modules in `configLabels` for examples
- Review the `loadConfig()` function in `web_ui.py` to understand the rendering logic
- Test with a simple boolean setting first, then add more complex options

