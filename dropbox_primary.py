"""
Dropbox Primary Storage Module for Webhook Data Viewer

This module treats Dropbox as the primary storage location for webhook data.
Data is first saved to Dropbox and then optionally synced to local storage.

Features:
- Direct saving of JSON data to Dropbox (no local file needed)
- Maintaining proper folder structure in Dropbox
- Syncing from Dropbox to local storage
- Robust error handling and verification
"""

import os
import json
import datetime
import time
import logging
import hashlib
import io
from pathlib import Path
import dropbox
from dropbox.exceptions import ApiError, AuthError
from dropbox.files import WriteMode

# Import the existing dropbox sync module
import dropbox_sync

# Configure logging
logger = logging.getLogger("dropbox-primary")

# Reuse the constants and settings from dropbox_sync
DROPBOX_APP_KEY = dropbox_sync.DROPBOX_APP_KEY
DROPBOX_APP_SECRET = dropbox_sync.DROPBOX_APP_SECRET 
DROPBOX_REFRESH_TOKEN = dropbox_sync.DROPBOX_REFRESH_TOKEN
DROPBOX_BACKUP_FOLDER = dropbox_sync.DROPBOX_BACKUP_FOLDER
DATA_DIR = dropbox_sync.DATA_DIR

def save_data_to_dropbox(data, sender, submission_id=None, debug=False, max_retries=3, verify=True):
    """
    Save JSON data directly to Dropbox as the primary storage.
    
    Args:
        data (dict): The JSON data to save
        sender (str): The sender identifier (folder name)
        submission_id (str, optional): Custom submission ID. If None, generates one.
        debug (bool): Enable verbose logging
        max_retries (int): Maximum retry attempts for failed uploads
        verify (bool): Whether to verify the uploaded file
        
    Returns:
        dict: Result information including success status, file path, and details
    """
    # Prepare result tracking
    result = {
        'success': False,
        'error': None,
        'details': {},
        'dropbox_path': None,
        'submission_id': None,
        'verified': False,
        'retries': 0
    }
    
    # Generate a submission ID if not provided
    if not submission_id:
        submission_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    
    result['submission_id'] = submission_id
    
    if debug:
        logger.info(f"Saving data directly to Dropbox for sender {sender}, submission {submission_id}")
    
    # Prepare metadata
    if '_meta' not in data:
        data['_meta'] = {
            'timestamp': datetime.datetime.now().isoformat(),
            'title': data.get('title', f"Submission {submission_id}"),
            'direct_to_dropbox': True
        }
    
    # Convert the data to JSON string
    try:
        file_content = json.dumps(data, indent=2).encode('utf-8')
        file_size = len(file_content)
        result['details']['file_size'] = file_size
        
        # Calculate file hash for verification
        if verify:
            file_hash = hashlib.md5(file_content).hexdigest()
            result['details']['file_hash'] = file_hash
            if debug:
                logger.info(f"File hash: {file_hash}")
    except Exception as e:
        error_msg = f"Error preparing JSON data: {str(e)}"
        logger.error(error_msg)
        result['error'] = error_msg
        return result
    
    # Get Dropbox client
    try:
        if debug:
            logger.info("Obtaining Dropbox client")
        
        try:
            dbx = dropbox_sync.get_dropbox_client(debug=debug)
            result['details']['client_obtained'] = True
        except Exception as e:
            error_msg = f"Failed to get Dropbox client: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg
            result['details']['client_error'] = str(e)
            return result
    except Exception as e:
        error_msg = f"Unexpected error getting Dropbox client: {str(e)}"
        logger.error(error_msg)
        result['error'] = error_msg
        return result
    
    # Ensure the proper folder structure exists in Dropbox
    try:
        # Create the path for this sender
        dropbox_sender_path = f"{DROPBOX_BACKUP_FOLDER}/{sender}"
        
        # Use the path creator function from dropbox_sync
        path_created = dropbox_sync.create_dropbox_path(dbx, dropbox_sender_path, debug=debug)
        if not path_created:
            error_msg = f"Failed to create path in Dropbox: {dropbox_sender_path}"
            logger.error(error_msg)
            result['error'] = error_msg
            result['details']['path_creation_failed'] = True
            return result
            
        result['details']['path_created'] = True
    except Exception as e:
        error_msg = f"Error creating Dropbox folder structure: {str(e)}"
        logger.error(error_msg)
        result['error'] = error_msg
        return result
    
    # Set the full Dropbox file path
    dropbox_file_path = f"{dropbox_sender_path}/{submission_id}.json"
    result['dropbox_path'] = dropbox_file_path
    
    # Upload with retries
    retry_count = 0
    upload_success = False
    upload_error = None
    
    while not upload_success and retry_count <= max_retries:
        try:
            if retry_count > 0:
                logger.info(f"Retry attempt {retry_count} of {max_retries}")
                # Wait longer between retries (exponential backoff)
                wait_time = min(2 ** retry_count, 30)  # Max 30 seconds
                time.sleep(wait_time)
            
            if debug:
                logger.info(f"Uploading data to {dropbox_file_path} ({file_size} bytes)")
            
            # Upload the file to Dropbox directly from memory
            upload_result = dbx.files_upload(
                file_content,
                dropbox_file_path,
                mode=WriteMode.overwrite
            )
            
            if debug:
                logger.info(f"Upload successful: {upload_result.path_display}")
            
            upload_success = True
            result['details']['upload_result'] = {
                'path_display': upload_result.path_display,
                'id': upload_result.id
            }
            
        except Exception as e:
            retry_count += 1
            upload_error = str(e)
            logger.warning(f"Upload attempt {retry_count} failed: {upload_error}")
            
            if retry_count > max_retries:
                error_msg = f"Failed to upload to Dropbox after {max_retries} attempts: {upload_error}"
                logger.error(error_msg)
                result['error'] = error_msg
                result['retries'] = retry_count
                return result
    
    result['retries'] = retry_count
    
    # Verify the upload if requested
    if verify and upload_success:
        try:
            if debug:
                logger.info(f"Verifying file upload to {dropbox_file_path}")
            
            # Download the file to verify content
            metadata, response = dbx.files_download(dropbox_file_path)
            dropbox_content = response.content
            
            # Calculate hash for downloaded content
            dropbox_hash = hashlib.md5(dropbox_content).hexdigest()
            result['details']['dropbox_hash'] = dropbox_hash
            
            # Compare file sizes and hashes
            if len(dropbox_content) == file_size and dropbox_hash == file_hash:
                result['verified'] = True
                if debug:
                    logger.info("File verification successful - content matches")
            else:
                if debug:
                    logger.warning("File verification failed - content does not match")
                    logger.warning(f"Original size: {file_size}, Dropbox size: {len(dropbox_content)}")
                    logger.warning(f"Original hash: {file_hash}, Dropbox hash: {dropbox_hash}")
                # We don't fail the operation if verification fails, just report it
                result['details']['verification_failed'] = True
        
        except Exception as e:
            logger.warning(f"Error during file verification: {str(e)}")
            result['details']['verification_error'] = str(e)
    
    # Mark as successful
    result['success'] = upload_success
    
    return result

def sync_from_dropbox_to_local(sender, submission_id, debug=False):
    """
    Download a file from Dropbox to local storage.
    
    Args:
        sender (str): The sender identifier
        submission_id (str): The submission ID
        debug (bool): Enable verbose logging
        
    Returns:
        dict: Result including success status and file path
    """
    result = {
        'success': False,
        'error': None,
        'details': {},
        'local_path': None
    }
    
    if debug:
        logger.info(f"Syncing from Dropbox to local storage: {sender}/{submission_id}")
    
    # Construct the Dropbox path
    dropbox_sender_path = f"{DROPBOX_BACKUP_FOLDER}/{sender}"
    dropbox_file_path = f"{dropbox_sender_path}/{submission_id}.json"
    
    # Construct the local path
    local_sender_dir = os.path.join(DATA_DIR, sender)
    local_file_path = os.path.join(local_sender_dir, f"{submission_id}.json")
    result['local_path'] = local_file_path
    
    # Get the Dropbox client
    try:
        dbx = dropbox_sync.get_dropbox_client(debug=debug)
    except Exception as e:
        error_msg = f"Failed to get Dropbox client: {str(e)}"
        logger.error(error_msg)
        result['error'] = error_msg
        return result
    
    # Ensure the local directory exists
    try:
        os.makedirs(local_sender_dir, exist_ok=True)
        if debug:
            logger.info(f"Ensured local directory exists: {local_sender_dir}")
    except Exception as e:
        error_msg = f"Failed to create local directory: {str(e)}"
        logger.error(error_msg)
        result['error'] = error_msg
        return result
    
    # Download the file from Dropbox
    try:
        if debug:
            logger.info(f"Downloading {dropbox_file_path} to {local_file_path}")
        
        metadata, response = dbx.files_download(dropbox_file_path)
        file_content = response.content
        
        # Save to local file
        with open(local_file_path, 'wb') as f:
            f.write(file_content)
        
        if debug:
            logger.info(f"Successfully downloaded file to {local_file_path}")
        
        # Check if the file was saved correctly
        if os.path.exists(local_file_path):
            result['success'] = True
            result['details']['file_size'] = os.path.getsize(local_file_path)
        else:
            error_msg = "File was not saved correctly to local storage"
            logger.error(error_msg)
            result['error'] = error_msg
            return result
            
    except Exception as e:
        error_msg = f"Error downloading file from Dropbox: {str(e)}"
        logger.error(error_msg)
        result['error'] = error_msg
        return result
    
    return result

def save_webhook_data(data, sender, debug=False, sync_to_local=True, verify=True):
    """
    Complete flow for saving webhook data to Dropbox and optionally sync to local.
    
    Args:
        data (dict): The JSON data to save
        sender (str): The sender identifier
        debug (bool): Enable verbose logging
        sync_to_local (bool): Whether to sync the file to local storage
        verify (bool): Whether to verify the uploaded file
        
    Returns:
        dict: Complete result with Dropbox and local storage info
    """
    result = {
        'success': False,
        'error': None,
        'dropbox': None,
        'local': None,
        'submission_id': None
    }
    
    # Step 1: Save to Dropbox
    dropbox_result = save_data_to_dropbox(data, sender, debug=debug, verify=verify)
    result['dropbox'] = dropbox_result
    result['submission_id'] = dropbox_result['submission_id']
    
    # If saving to Dropbox failed, abort the whole operation
    if not dropbox_result['success']:
        result['error'] = f"Failed to save to Dropbox: {dropbox_result.get('error', 'Unknown error')}"
        return result
    
    # Step 2: Sync to local storage if requested
    if sync_to_local:
        local_result = sync_from_dropbox_to_local(
            sender, 
            dropbox_result['submission_id'],
            debug=debug
        )
        result['local'] = local_result
        
        # The overall operation succeeds even if local sync fails
        result['success'] = dropbox_result['success']
        if not local_result['success']:
            result['error'] = f"Saved to Dropbox but failed to sync locally: {local_result.get('error', 'Unknown error')}"
    else:
        # If not syncing to local, we're done with success
        result['success'] = dropbox_result['success']
    
    return result
