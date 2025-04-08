# Dropbox Integration for Webhook Data Viewer

This integration allows you to automatically back up your webhook data to Dropbox, ensuring that you never lose any important data.

## Features

- **Automatic Backup**: Each new webhook submission is automatically backed up to Dropbox
- **Scheduled Backups**: Run periodic backups to ensure all data is synced
- **Automatic Token Refresh**: Uses refresh token to maintain Dropbox access
- **Data Restoration**: Easily restore data from Dropbox if needed
- **Folder Structure**: Maintains the same organization in Dropbox as in your local data

## Setup Instructions

### 1. Install Required Packages

The necessary packages are already in the requirements.txt file. Install them with:

```bash
pip install -r requirements.txt
```

### 2. Set Up Environment Variables

1. Copy the template file to create your .env file:

```bash
cp .env.template .env
```

2. The .env file already contains the necessary Dropbox credentials. You don't need to modify them.

### 3. Enable Auto Backup

Auto backup is enabled by default in the .env template. If you want to disable it, set:

```
ENABLE_AUTO_BACKUP=False
```

### 4. Set Up Scheduled Backups (Optional)

For extra protection, set up a scheduled task to run full backups periodically:

#### Using Cron (Linux/Mac)

Example to run daily at 2 AM:

```bash
# Open crontab
crontab -e

# Add this line (adjust the path to your application)
0 2 * * * cd /path/to/webhook-app && python scheduled_backup.py >> backup_cron.log 2>&1
```

#### Using Task Scheduler (Windows)

1. Open Task Scheduler
2. Create a new Basic Task
3. Set the trigger (e.g., daily at 2 AM)
4. Set the action to start a program:
   - Program: `python`
   - Arguments: `scheduled_backup.py`
   - Start in: `C:\path\to\webhook-app`

## Usage

### Manual Backup

To manually back up all data:

```bash
python dropbox_sync.py --backup
```

### Test Connection

To test your Dropbox connection:

```bash
python dropbox_sync.py --test-connection
```

### Restore Data

To restore all data from Dropbox:

```bash
python dropbox_sync.py --restore
```

To restore data for a specific sender:

```bash
python dropbox_sync.py --restore-sender example-user
```

## Checking Your Backup

Once set up, your webhook data will be backed up to Dropbox in a folder called "WebhookBackup" (or the custom path you configured in .env). The folder structure will mirror your local data:

```
WebhookBackup/
├── sender1/
│   ├── 20250408123456.json
│   └── 20250408123789.json
├── sender2/
    └── 20250407080123.json
```

## Troubleshooting

### Checking Logs

Check these log files for information about backup operations:

- `dropbox_sync.log` - Contains logs from the Dropbox sync utility
- `app.log` - Contains logs from the Flask application, including auto-backup

### Common Issues

1. **Token Refresh Failures**: If you see token refresh errors, verify your Dropbox API credentials in .env

2. **Permissions Issues**: Make sure the application has write access to the data directory

3. **Connection Issues**: If you're having connection problems, check your internet connection and Dropbox status

## Security Note

The .env file contains sensitive credentials. Make sure it's:

- Not committed to version control
- Has restricted file permissions
- Only accessible to authorized users

If you believe your tokens have been compromised, revoke them in your Dropbox developer dashboard and generate new ones.
