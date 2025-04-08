"""
Dropbox Sync Utility for Webhook Data Viewer

This script provides functionality to backup and restore data from the 
Webhook Data Viewer application to Dropbox for safe keeping.

Features:
- Automatic token refresh using refresh token
- Backup all webhook data to Dropbox
- Restore data from Dropbox if needed
- Folder structure mirroring for organization
"""

import os
import json
import datetime
import time
import logging
import shutil
from pathlib import Path
import requests
import dropbox
from dropbox.exceptions import ApiError, AuthError
from dropbox.files import WriteMode
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("dropbox_sync.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("dropbox_sync")

# Load environment variables from .env file if present
load_dotenv()

# Dropbox API credentials
DROPBOX_APP_KEY = os.getenv("DROPBOX_APP_KEY", "2bi422xpd3xd962")
DROPBOX_APP_SECRET = os.getenv("DROPBOX_APP_SECRET", "j3yx0b41qdvfu86")
DROPBOX_ACCESS_TOKEN = os.getenv("DROPBOX_ACCESS_TOKEN", "")
DROPBOX_REFRESH_TOKEN = os.getenv("DROPBOX_REFRESH_TOKEN", "RvyL03RE5qAAAAAAAAAAAVMVebvE7jDx8Okd0ploMzr85c6txvCRXpJAt30mxrKF")

# Dropbox folder name for backups
DROPBOX_BACKUP_FOLDER = "/WebhookBackup"

# Local data directory
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

def refresh_access_token():
    """
    Refresh the Dropbox access token using the refresh token.
    Returns the new access token if successful, None otherwise.
    """
    logger.info("Refreshing Dropbox access token...")
    
    try:
        # Prepare the token refresh request
        url = "https://api.dropboxapi.com/oauth2/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": DROPBOX_REFRESH_TOKEN,
            "client_id": DROPBOX_APP_KEY,
            "client_secret": DROPBOX_APP_SECRET
        }
        
        # Make the request
        response = requests.post(url, data=data)
        response.raise_for_status()  # Raise an exception for 4XX/5XX responses
        
        # Extract the new access token
        result = response.json()
        new_token = result.get("access_token")
        
        if new_token:
            logger.info("Successfully refreshed access token")
            return new_token
        else:
            logger.error("No access token in refresh response")
            return None
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error refreshing token: {str(e)}")
        return None

def get_dropbox_client():
    """
    Get a Dropbox client instance with a valid access token.
    First tries the current access token, then refreshes if needed.
    """
    global DROPBOX_ACCESS_TOKEN
    
    # First try with existing token
    if DROPBOX_ACCESS_TOKEN:
        dbx = dropbox.Dropbox(DROPBOX_ACCESS_TOKEN)
        try:
            # Test if the token is valid
            dbx.users_get_current_account()
            return dbx
        except (AuthError, ApiError):
            logger.info("Access token expired, refreshing...")
            # Token expired, need to refresh
            pass
    
    # Refresh the token
    new_token = refresh_access_token()
    if new_token:
        DROPBOX_ACCESS_TOKEN = new_token
        dbx = dropbox.Dropbox(DROPBOX_ACCESS_TOKEN)
        return dbx
    else:
        raise AuthError("Failed to obtain a valid access token")

def ensure_dropbox_folders(dbx):
    """
    Ensure all necessary folders exist in Dropbox.
    Creates the main backup folder and mirrors the local folder structure.
    """
    logger.info(f"Ensuring Dropbox folder structure exists at {DROPBOX_BACKUP_FOLDER}")
    
    try:
        # Create the main backup folder if it doesn't exist
        try:
            dbx.files_get_metadata(DROPBOX_BACKUP_FOLDER)
        except ApiError:
            dbx.files_create_folder_v2(DROPBOX_BACKUP_FOLDER)
            logger.info(f"Created main backup folder: {DROPBOX_BACKUP_FOLDER}")
        
        # Create sender folders if they don't exist
        if os.path.exists(DATA_DIR):
            for sender in os.listdir(DATA_DIR):
                sender_path = os.path.join(DATA_DIR, sender)
                if os.path.isdir(sender_path):
                    dropbox_sender_path = f"{DROPBOX_BACKUP_FOLDER}/{sender}"
                    try:
                        dbx.files_get_metadata(dropbox_sender_path)
                    except ApiError:
                        dbx.files_create_folder_v2(dropbox_sender_path)
                        logger.info(f"Created sender folder: {dropbox_sender_path}")
        
        return True
    except Exception as e:
        logger.error(f"Error ensuring folder structure: {str(e)}")
        return False

def backup_file(dbx, local_path, dropbox_path):
    """
    Upload a single file to Dropbox.
    Returns True if successful, False otherwise.
    """
    logger.info(f"Backing up: {local_path} to {dropbox_path}")
    
    try:
        with open(local_path, 'rb') as f:
            file_size = os.path.getsize(local_path)
            
            # For large files, use upload session
            if file_size > 4 * 1024 * 1024:  # 4 MB
                logger.info(f"Using upload session for large file: {local_path}")
                upload_session_start_result = dbx.files_upload_session_start(f.read(4 * 1024 * 1024))
                cursor = dropbox.files.UploadSessionCursor(
                    session_id=upload_session_start_result.session_id,
                    offset=f.tell()
                )
                commit = dropbox.files.CommitInfo(path=dropbox_path, mode=WriteMode.overwrite)
                
                while f.tell() < file_size:
                    if (file_size - f.tell()) <= 4 * 1024 * 1024:  # Last chunk
                        dbx.files_upload_session_finish(
                            f.read(4 * 1024 * 1024),
                            cursor,
                            commit
                        )
                        break
                    else:
                        dbx.files_upload_session_append_v2(
                            f.read(4 * 1024 * 1024),
                            cursor
                        )
                        cursor.offset = f.tell()
            else:
                # For small files, use simple upload
                dbx.files_upload(f.read(), dropbox_path, mode=WriteMode.overwrite)
        
        logger.info(f"Successfully backed up: {local_path}")
        return True
    except Exception as e:
        logger.error(f"Error backing up {local_path}: {str(e)}")
        return False

def backup_all_data():
    """
    Backup all webhook data to Dropbox.
    Returns the number of files successfully backed up.
    """
    if not os.path.exists(DATA_DIR):
        logger.warning(f"Data directory {DATA_DIR} does not exist. Nothing to backup.")
        return 0
    
    try:
        # Get Dropbox client
        dbx = get_dropbox_client()
        
        # Ensure folder structure exists
        if not ensure_dropbox_folders(dbx):
            logger.error("Failed to create Dropbox folder structure")
            return 0
        
        # Track successful backups
        success_count = 0
        
        # Process all sender directories
        for sender in os.listdir(DATA_DIR):
            sender_path = os.path.join(DATA_DIR, sender)
            if os.path.isdir(sender_path):
                # Create sender folder in Dropbox if needed
                dropbox_sender_path = f"{DROPBOX_BACKUP_FOLDER}/{sender}"
                try:
                    dbx.files_get_metadata(dropbox_sender_path)
                except ApiError:
                    dbx.files_create_folder_v2(dropbox_sender_path)
                
                # Process all JSON files in the sender directory
                for filename in os.listdir(sender_path):
                    if filename.endswith('.json'):
                        local_file_path = os.path.join(sender_path, filename)
                        dropbox_file_path = f"{dropbox_sender_path}/{filename}"
                        
                        if backup_file(dbx, local_file_path, dropbox_file_path):
                            success_count += 1
        
        logger.info(f"Backup complete. Successfully backed up {success_count} files.")
        return success_count
    
    except Exception as e:
        logger.error(f"Error during backup: {str(e)}")
        return 0

def backup_specific_file(sender, submission_id):
    """
    Backup a specific webhook submission to Dropbox.
    Returns True if successful, False otherwise.
    """
    local_file_path = os.path.join(DATA_DIR, sender, f"{submission_id}.json")
    if not os.path.exists(local_file_path):
        logger.warning(f"File not found: {local_file_path}")
        return False
    
    try:
        # Get Dropbox client
        dbx = get_dropbox_client()
        
        # Ensure folder structure exists
        if not ensure_dropbox_folders(dbx):
            logger.error("Failed to create Dropbox folder structure")
            return False
        
        # Create sender folder in Dropbox if needed
        dropbox_sender_path = f"{DROPBOX_BACKUP_FOLDER}/{sender}"
        try:
            dbx.files_get_metadata(dropbox_sender_path)
        except ApiError:
            dbx.files_create_folder_v2(dropbox_sender_path)
        
        # Backup the file
        dropbox_file_path = f"{dropbox_sender_path}/{submission_id}.json"
        return backup_file(dbx, local_file_path, dropbox_file_path)
    
    except Exception as e:
        logger.error(f"Error backing up specific file: {str(e)}")
        return False

def restore_file(dbx, dropbox_path, local_path):
    """
    Download a single file from Dropbox.
    Returns True if successful, False otherwise.
    """
    logger.info(f"Restoring: {dropbox_path} to {local_path}")
    
    try:
        # Make sure the directory exists
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        
        # Download the file
        metadata, response = dbx.files_download(dropbox_path)
        with open(local_path, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"Successfully restored: {dropbox_path}")
        return True
    except Exception as e:
        logger.error(f"Error restoring {dropbox_path}: {str(e)}")
        return False

def list_dropbox_files(dbx, folder_path):
    """
    List all files in a Dropbox folder.
    Returns a list of file metadata objects.
    """
    try:
        result = dbx.files_list_folder(folder_path, recursive=False)
        files = result.entries
        
        # Continue fetching if there's more
        while result.has_more:
            result = dbx.files_list_folder_continue(result.cursor)
            files.extend(result.entries)
            
        return files
    except Exception as e:
        logger.error(f"Error listing Dropbox files in {folder_path}: {str(e)}")
        return []

def restore_all_data():
    """
    Restore all webhook data from Dropbox.
    Returns the number of files successfully restored.
    """
    try:
        # Get Dropbox client
        dbx = get_dropbox_client()
        
        # Track successful restores
        success_count = 0
        
        # Check if backup folder exists in Dropbox
        try:
            dbx.files_get_metadata(DROPBOX_BACKUP_FOLDER)
        except ApiError:
            logger.error(f"Backup folder {DROPBOX_BACKUP_FOLDER} not found in Dropbox")
            return 0
        
        # Get all sender folders in the backup folder
        sender_folders = list_dropbox_files(dbx, DROPBOX_BACKUP_FOLDER)
        
        for folder in sender_folders:
            if isinstance(folder, dropbox.files.FolderMetadata):
                sender_name = folder.name
                dropbox_sender_path = f"{DROPBOX_BACKUP_FOLDER}/{sender_name}"
                local_sender_path = os.path.join(DATA_DIR, sender_name)
                
                # Get all files in this sender folder
                sender_files = list_dropbox_files(dbx, dropbox_sender_path)
                
                for file in sender_files:
                    if isinstance(file, dropbox.files.FileMetadata) and file.name.endswith('.json'):
                        dropbox_file_path = f"{dropbox_sender_path}/{file.name}"
                        local_file_path = os.path.join(local_sender_path, file.name)
                        
                        if restore_file(dbx, dropbox_file_path, local_file_path):
                            success_count += 1
        
        logger.info(f"Restore complete. Successfully restored {success_count} files.")
        return success_count
    
    except Exception as e:
        logger.error(f"Error during restore: {str(e)}")
        return 0

def restore_specific_sender(sender):
    """
    Restore all data for a specific sender from Dropbox.
    Returns the number of files successfully restored.
    """
    try:
        # Get Dropbox client
        dbx = get_dropbox_client()
        
        # Check if sender folder exists in Dropbox
        dropbox_sender_path = f"{DROPBOX_BACKUP_FOLDER}/{sender}"
        try:
            dbx.files_get_metadata(dropbox_sender_path)
        except ApiError:
            logger.error(f"Sender folder {dropbox_sender_path} not found in Dropbox")
            return 0
        
        # Track successful restores
        success_count = 0
        
        # Get all files in this sender folder
        sender_files = list_dropbox_files(dbx, dropbox_sender_path)
        
        # Prepare local sender directory
        local_sender_path = os.path.join(DATA_DIR, sender)
        os.makedirs(local_sender_path, exist_ok=True)
        
        for file in sender_files:
            if isinstance(file, dropbox.files.FileMetadata) and file.name.endswith('.json'):
                dropbox_file_path = f"{dropbox_sender_path}/{file.name}"
                local_file_path = os.path.join(local_sender_path, file.name)
                
                if restore_file(dbx, dropbox_file_path, local_file_path):
                    success_count += 1
        
        logger.info(f"Restore complete for sender {sender}. Successfully restored {success_count} files.")
        return success_count
    
    except Exception as e:
        logger.error(f"Error during sender restore: {str(e)}")
        return 0

def run_scheduled_backup():
    """Run a scheduled backup and log the results"""
    try:
        start_time = time.time()
        logger.info("Starting scheduled backup job")
        
        backed_up_count = backup_all_data()
        
        elapsed_time = time.time() - start_time
        logger.info(f"Scheduled backup completed in {elapsed_time:.2f}s, {backed_up_count} files backed up")
        
        return backed_up_count
    except Exception as e:
        logger.error(f"Error during scheduled backup: {str(e)}")
        return 0

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Dropbox Sync Utility for Webhook Data Viewer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--backup", action="store_true", help="Backup all data to Dropbox")
    group.add_argument("--restore", action="store_true", help="Restore all data from Dropbox")
    group.add_argument("--restore-sender", metavar="SENDER", help="Restore data for a specific sender")
    group.add_argument("--backup-file", nargs=2, metavar=("SENDER", "SUBMISSION_ID"), help="Backup a specific file")
    group.add_argument("--schedule", action="store_true", help="Run as a scheduled job")
    group.add_argument("--test-connection", action="store_true", help="Test Dropbox connection")
    
    args = parser.parse_args()
    
    try:
        if args.backup:
            backed_up = backup_all_data()
            print(f"Backup completed: {backed_up} files backed up")
        
        elif args.restore:
            restored = restore_all_data()
            print(f"Restore completed: {restored} files restored")
        
        elif args.restore_sender:
            restored = restore_specific_sender(args.restore_sender)
            print(f"Restore completed for {args.restore_sender}: {restored} files restored")
        
        elif args.backup_file:
            sender, submission_id = args.backup_file
            result = backup_specific_file(sender, submission_id)
            if result:
                print(f"Successfully backed up {sender}/{submission_id}.json")
            else:
                print(f"Failed to back up {sender}/{submission_id}.json")
        
        elif args.schedule:
            run_scheduled_backup()
        
        elif args.test_connection:
            dbx = get_dropbox_client()
            account = dbx.users_get_current_account()
            print(f"Connection successful! Logged in as: {account.name.display_name}")
    
    except Exception as e:
        print(f"Error: {str(e)}")
        logger.error(f"Command-line error: {str(e)}")
        exit(1)
