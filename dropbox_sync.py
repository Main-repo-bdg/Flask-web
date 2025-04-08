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

def refresh_access_token(debug=False):
    """
    Refresh the Dropbox access token using the refresh token.
    Returns the new access token if successful, None otherwise.
    
    Args:
        debug (bool): If True, prints additional debug information
    """
    logger.info("Refreshing Dropbox access token...")
    
    if debug:
        logger.info(f"Using app key: {DROPBOX_APP_KEY[:5]}... and refresh token: {DROPBOX_REFRESH_TOKEN[:5]}...")
    
    if not DROPBOX_REFRESH_TOKEN or DROPBOX_REFRESH_TOKEN == "YOUR_REFRESH_TOKEN":
        logger.error("No valid refresh token provided. Check your .env file.")
        raise ValueError("Invalid refresh token. Set DROPBOX_REFRESH_TOKEN in your .env file.")
    
    try:
        # Prepare the token refresh request
        url = "https://api.dropboxapi.com/oauth2/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": DROPBOX_REFRESH_TOKEN,
            "client_id": DROPBOX_APP_KEY,
            "client_secret": DROPBOX_APP_SECRET
        }
        
        # Make the request with detailed logging
        logger.info(f"Making token refresh request to {url}")
        response = requests.post(url, data=data)
        
        # Log the response details
        if debug or response.status_code != 200:
            logger.info(f"Token refresh response status: {response.status_code}")
            logger.info(f"Token refresh response headers: {response.headers}")
            # Don't log the full response body as it may contain sensitive info
            
        response.raise_for_status()  # Raise an exception for 4XX/5XX responses
        
        # Extract the new access token
        result = response.json()
        new_token = result.get("access_token")
        expires_in = result.get("expires_in", "unknown")
        
        if new_token:
            logger.info(f"Successfully refreshed access token. Expires in {expires_in} seconds.")
            
            # Update the access token in .env file if possible
            try:
                if os.path.exists('.env'):
                    with open('.env', 'r') as f:
                        env_content = f.read()
                    
                    # Check if DROPBOX_ACCESS_TOKEN exists in .env
                    if 'DROPBOX_ACCESS_TOKEN=' in env_content:
                        # Replace existing token
                        import re
                        new_env = re.sub(
                            r'DROPBOX_ACCESS_TOKEN=.*',
                            f'DROPBOX_ACCESS_TOKEN={new_token}',
                            env_content
                        )
                    else:
                        # Add token if not exists
                        new_env = env_content + f'\nDROPBOX_ACCESS_TOKEN={new_token}\n'
                    
                    with open('.env', 'w') as f:
                        f.write(new_env)
                    
                    logger.info("Updated access token in .env file")
            except Exception as e:
                logger.warning(f"Could not update .env file with new token: {str(e)}")
            
            return new_token
        else:
            logger.error("No access token in refresh response")
            if debug:
                safe_result = {k: v for k, v in result.items() if k != "access_token"}
                logger.error(f"Response content: {safe_result}")
            return None
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error refreshing token: {str(e)}")
        if debug and hasattr(e, 'response') and e.response:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response content: {e.response.text}")
        return None

def get_dropbox_client(debug=False):
    """
    Get a Dropbox client instance with a valid access token.
    First tries the current access token, then refreshes if needed.
    
    Args:
        debug (bool): If True, enables verbose debug logging
        
    Returns:
        dropbox.Dropbox: A configured Dropbox client
        
    Raises:
        AuthError: If a valid access token cannot be obtained
        ConnectionError: If connection to Dropbox API fails
    """
    global DROPBOX_ACCESS_TOKEN
    
    if debug:
        logger.info(f"Getting Dropbox client. Current token status: {'Set' if DROPBOX_ACCESS_TOKEN else 'Not set'}")
    
    # First try with existing token if available
    if DROPBOX_ACCESS_TOKEN:
        try:
            if debug:
                logger.info("Attempting to use existing access token")
            
            # Initialize with timeouts and proper app info
            dbx = dropbox.Dropbox(
                DROPBOX_ACCESS_TOKEN,
                app_key=DROPBOX_APP_KEY,
                app_secret=DROPBOX_APP_SECRET,
                timeout=30
            )
            
            # Test if the token is valid
            account_info = dbx.users_get_current_account()
            if debug:
                logger.info(f"Token valid. Connected as: {account_info.name.display_name}")
            return dbx
        
        except AuthError as e:
            logger.info(f"Access token expired or invalid: {str(e)}")
            if debug:
                logger.info("Will attempt to refresh token")
            # Token expired, need to refresh
            pass
        
        except ApiError as e:
            logger.warning(f"Dropbox API error with existing token: {str(e)}")
            if debug:
                logger.info(f"API error details: {e!r}")
            # Try refreshing the token
            pass
            
        except Exception as e:
            logger.warning(f"Unexpected error with existing token: {str(e)}")
            if debug:
                logger.info(f"Will attempt token refresh. Error details: {e!r}")
            # Try refreshing the token
            pass
    
    # Refresh the token
    try:
        if debug:
            logger.info("Requesting new access token")
        
        new_token = refresh_access_token(debug=debug)
        if new_token:
            if debug:
                logger.info("Successfully obtained new access token")
            
            DROPBOX_ACCESS_TOKEN = new_token
            
            # Initialize with timeouts and proper app info
            dbx = dropbox.Dropbox(
                DROPBOX_ACCESS_TOKEN,
                app_key=DROPBOX_APP_KEY,
                app_secret=DROPBOX_APP_SECRET,
                timeout=30
            )
            
            # Verify the new token works
            try:
                account_info = dbx.users_get_current_account()
                if debug:
                    logger.info(f"New token verified. Connected as: {account_info.name.display_name}")
                return dbx
            except Exception as e:
                logger.error(f"New token obtained but failed verification: {str(e)}")
                raise AuthError(f"New token failed verification: {str(e)}")
        else:
            logger.error("Failed to obtain new access token")
            raise AuthError("Failed to obtain a valid access token")
    
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error to Dropbox API: {str(e)}")
        raise ConnectionError(f"Cannot connect to Dropbox: {str(e)}")
    
    except Exception as e:
        logger.error(f"Unexpected error getting Dropbox client: {str(e)}")
        raise

def ensure_dropbox_folders(dbx, debug=False):
    """
    Ensure all necessary folders exist in Dropbox.
    Creates the main backup folder and mirrors the local folder structure.
    
    Args:
        dbx: Dropbox client instance
        debug (bool): If True, enables verbose debug logging
        
    Returns:
        bool: True if all folders were ensured, False if there was an error
    """
    logger.info(f"Ensuring Dropbox folder structure exists at {DROPBOX_BACKUP_FOLDER}")
    result = {
        "main_folder_exists": False,
        "main_folder_created": False,
        "sender_folders_checked": 0,
        "sender_folders_created": 0,
        "errors": []
    }
    
    try:
        # First verify we have a working connection to Dropbox
        if debug:
            logger.info("Verifying Dropbox connection")
        
        try:
            account_info = dbx.users_get_current_account()
            if debug:
                logger.info(f"Connected to Dropbox as: {account_info.name.display_name}")
        except Exception as e:
            error_msg = f"Failed to connect to Dropbox: {str(e)}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            return False
        
        # Now create the main backup folder if it doesn't exist
        if debug:
            logger.info(f"Checking if main folder exists: {DROPBOX_BACKUP_FOLDER}")
            
        try:
            dbx.files_get_metadata(DROPBOX_BACKUP_FOLDER)
            if debug:
                logger.info(f"Main folder already exists: {DROPBOX_BACKUP_FOLDER}")
            result["main_folder_exists"] = True
        except ApiError as e:
            if debug:
                logger.info(f"Main folder doesn't exist, creating: {DROPBOX_BACKUP_FOLDER}")
                
            # Check if the error is actually "not found"
            if isinstance(e.error, dropbox.files.GetMetadataError) and e.error.is_path() and e.error.get_path().is_not_found():
                try:
                    folder_metadata = dbx.files_create_folder_v2(DROPBOX_BACKUP_FOLDER)
                    logger.info(f"Created main backup folder: {folder_metadata.metadata.path_display}")
                    result["main_folder_created"] = True
                except Exception as create_err:
                    error_msg = f"Failed to create main folder: {str(create_err)}"
                    logger.error(error_msg)
                    result["errors"].append(error_msg)
                    return False
            else:
                # If it's another API error, log it and return false
                error_msg = f"API error checking main folder: {str(e)}"
                logger.error(error_msg)
                result["errors"].append(error_msg)
                return False
                
        # Create sender folders if they don't exist
        if os.path.exists(DATA_DIR):
            senders = [d for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d))]
            
            if debug:
                logger.info(f"Found {len(senders)} sender directories to check")
            
            for sender in senders:
                sender_path = os.path.join(DATA_DIR, sender)
                if os.path.isdir(sender_path):
                    result["sender_folders_checked"] += 1
                    dropbox_sender_path = f"{DROPBOX_BACKUP_FOLDER}/{sender}"
                    
                    if debug:
                        logger.info(f"Checking sender folder: {dropbox_sender_path}")
                    
                    try:
                        # Check if folder exists
                        dbx.files_get_metadata(dropbox_sender_path)
                        if debug:
                            logger.info(f"Sender folder exists: {dropbox_sender_path}")
                    except ApiError as e:
                        # Only create if the error is "not found"
                        if isinstance(e.error, dropbox.files.GetMetadataError) and e.error.is_path() and e.error.get_path().is_not_found():
                            try:
                                if debug:
                                    logger.info(f"Creating sender folder: {dropbox_sender_path}")
                                folder_metadata = dbx.files_create_folder_v2(dropbox_sender_path)
                                logger.info(f"Created sender folder: {folder_metadata.metadata.path_display}")
                                result["sender_folders_created"] += 1
                            except Exception as create_err:
                                error_msg = f"Failed to create sender folder {sender}: {str(create_err)}"
                                logger.error(error_msg)
                                result["errors"].append(error_msg)
                                # Continue with other folders instead of failing completely
                        else:
                            # If it's another API error, log it but continue
                            error_msg = f"API error checking sender folder {sender}: {str(e)}"
                            logger.error(error_msg)
                            result["errors"].append(error_msg)
        else:
            if debug:
                logger.info(f"Local data directory does not exist yet: {DATA_DIR}")
        
        # If we got here with no errors in the critical paths, return True
        if not result["errors"] or len(result["errors"]) == 0:
            if debug:
                logger.info("Successfully ensured all folders exist")
            return True
        else:
            logger.warning(f"Completed with some errors: {len(result['errors'])} errors occurred")
            return len(result["errors"]) == 0  # True if no errors
            
    except Exception as e:
        error_msg = f"Unexpected error ensuring folder structure: {str(e)}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
        return False

def create_dropbox_path(dbx, path, debug=False):
    """
    Create a folder path in Dropbox, creating parent folders as needed.
    This is a helper function to ensure that a path exists, creating each folder
    in the path if necessary.
    
    Args:
        dbx: Dropbox client instance
        path (str): The path to create (e.g., "/WebhookBackup/user1/subfolder")
        debug (bool): If True, enables verbose debug logging
        
    Returns:
        bool: True if the path was created/exists, False if there was an error
    """
    if debug:
        logger.info(f"Creating Dropbox path: {path}")
    
    # If it's just the root folder, there's nothing to do
    if path == "" or path == "/":
        return True
    
    # Split the path into components
    # Remove leading/trailing slashes and split by /
    components = [p for p in path.strip('/').split('/') if p]
    
    if not components:
        return True  # Nothing to create
    
    # Start with the root
    current_path = ""
    
    # Create each component of the path
    for i, component in enumerate(components):
        # Build the path incrementally
        if current_path:
            current_path = f"{current_path}/{component}"
        else:
            current_path = f"/{component}"
            
        if debug:
            logger.info(f"Checking component: {current_path}")
        
        try:
            # Check if this component exists
            dbx.files_get_metadata(current_path)
            if debug:
                logger.info(f"Path component exists: {current_path}")
                
        except ApiError as e:
            # Create the folder if it doesn't exist
            if isinstance(e.error, dropbox.files.GetMetadataError) and e.error.is_path() and e.error.get_path().is_not_found():
                try:
                    if debug:
                        logger.info(f"Creating path component: {current_path}")
                    metadata = dbx.files_create_folder_v2(current_path)
                    if debug:
                        logger.info(f"Created folder: {metadata.metadata.path_display}")
                except Exception as create_err:
                    logger.error(f"Failed to create folder {current_path}: {str(create_err)}")
                    return False
            else:
                logger.error(f"API error checking path {current_path}: {str(e)}")
                return False
                
    return True

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

def backup_specific_file(sender, submission_id, debug=False):
    """
    Backup a specific webhook submission to Dropbox.
    
    Args:
        sender (str): The sender's directory name
        submission_id (str): The submission ID (filename without .json)
        debug (bool): If True, enables verbose debug logging
    
    Returns:
        dict: A dictionary with success status and detailed information
            {
                'success': bool,       # Whether backup was successful
                'error': str or None,  # Error message if any
                'details': dict,       # Additional details about the operation
                'path': str            # Dropbox path where file was saved
            }
    """
    result = {
        'success': False,
        'error': None,
        'details': {},
        'path': None
    }
    
    if debug:
        logger.info(f"Starting backup of submission {submission_id} from sender {sender}")
    
    # Check for the local file
    local_file_path = os.path.join(DATA_DIR, sender, f"{submission_id}.json")
    if not os.path.exists(local_file_path):
        error_msg = f"File not found: {local_file_path}"
        logger.warning(error_msg)
        result['error'] = error_msg
        result['details']['file_exists'] = False
        return result
    
    result['details']['file_exists'] = True
    result['details']['file_size'] = os.path.getsize(local_file_path)
    
    try:
        # Get Dropbox client with debug mode if requested
        if debug:
            logger.info("Obtaining Dropbox client")
        
        try:
            dbx = get_dropbox_client(debug=debug)
            result['details']['client_obtained'] = True
        except Exception as e:
            error_msg = f"Failed to get Dropbox client: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg
            result['details']['client_obtained'] = False
            result['details']['client_error'] = str(e)
            return result
        
        # Ensure folder structure exists
        if debug:
            logger.info("Ensuring Dropbox folder structure")
            
        try:
            folders_created = ensure_dropbox_folders(dbx)
            result['details']['folders_created'] = folders_created
            
            if not folders_created:
                error_msg = "Failed to create Dropbox folder structure"
                logger.error(error_msg)
                result['error'] = error_msg
                return result
        except Exception as e:
            error_msg = f"Error ensuring folder structure: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg
            result['details']['folders_error'] = str(e)
            return result
        
        # Create sender folder in Dropbox if needed
        dropbox_sender_path = f"{DROPBOX_BACKUP_FOLDER}/{sender}"
        if debug:
            logger.info(f"Checking for sender folder: {dropbox_sender_path}")
            
        try:
            try:
                dbx.files_get_metadata(dropbox_sender_path)
                if debug:
                    logger.info(f"Sender folder exists: {dropbox_sender_path}")
                result['details']['sender_folder_exists'] = True
            except ApiError:
                if debug:
                    logger.info(f"Creating sender folder: {dropbox_sender_path}")
                dbx.files_create_folder_v2(dropbox_sender_path)
                result['details']['sender_folder_created'] = True
        except Exception as e:
            error_msg = f"Error managing sender folder: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg
            result['details']['sender_folder_error'] = str(e)
            return result
        
        # Backup the file
        dropbox_file_path = f"{dropbox_sender_path}/{submission_id}.json"
        result['path'] = dropbox_file_path
        
        if debug:
            logger.info(f"Uploading file to: {dropbox_file_path}")
        
        try:
            # First check if the file already exists in Dropbox
            try:
                existing_file = dbx.files_get_metadata(dropbox_file_path)
                if debug:
                    logger.info(f"File already exists in Dropbox: {dropbox_file_path}")
                result['details']['file_existed'] = True
            except ApiError:
                if debug:
                    logger.info(f"File does not exist yet in Dropbox: {dropbox_file_path}")
                result['details']['file_existed'] = False
            
            # Upload the file
            with open(local_file_path, 'rb') as f:
                file_content = f.read()  # Read once and store in memory
                file_size = len(file_content)
                
                if debug:
                    logger.info(f"Uploading {file_size} bytes")
                
                upload_result = dbx.files_upload(
                    file_content, 
                    dropbox_file_path, 
                    mode=WriteMode.overwrite
                )
                
                if debug:
                    logger.info(f"Upload successful: {upload_result.path_display}")
                
                result['success'] = True
                result['details']['upload_complete'] = True
                return result
                
        except Exception as e:
            error_msg = f"Error uploading file: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg
            result['details']['upload_error'] = str(e)
            return result
    
    except Exception as e:
        error_msg = f"Unexpected error backing up file: {str(e)}"
        logger.error(error_msg)
        result['error'] = error_msg
        return result

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
