#!/usr/bin/env python3
"""
Scheduled Backup Script for Webhook Data Viewer

This script is designed to be run as a scheduled task (e.g., via cron) to
periodically backup all webhook data to Dropbox.

Example cron entry (daily at 2 AM):
0 2 * * * cd /path/to/app && python scheduled_backup.py >> backup_cron.log 2>&1

Usage:
  python scheduled_backup.py
"""

import os
import sys
import time
import logging
from pathlib import Path

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("scheduled-backup")

def main():
    """Run the scheduled backup process"""
    logger.info("Starting scheduled backup...")
    
    # Check if the dropbox_sync module is available
    try:
        import dropbox_sync
    except ImportError:
        logger.error("dropbox_sync module not found. Please check your installation.")
        return 1
    
    # Make sure we're in the correct directory
    script_dir = Path(__file__).parent.absolute()
    os.chdir(script_dir)
    
    # Run the backup
    try:
        start_time = time.time()
        backed_up_count = dropbox_sync.run_scheduled_backup()
        
        if backed_up_count > 0:
            elapsed_time = time.time() - start_time
            logger.info(f"Backup completed successfully. Backed up {backed_up_count} files in {elapsed_time:.2f} seconds.")
            return 0
        else:
            logger.warning("No files were backed up. Check if there's data to backup or if there were errors.")
            return 0  # Still return 0 as this might be normal (no new data)
    
    except Exception as e:
        logger.error(f"Backup failed with error: {str(e)}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
