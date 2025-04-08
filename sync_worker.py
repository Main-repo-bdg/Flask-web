#!/usr/bin/env python3
"""
Synchronization Worker for Webhook Data Viewer

This script provides background synchronization capabilities to ensure
all data is properly backed up to Dropbox and can be restored if needed.

It can be run:
1. As a scheduled task (via cron)
2. On-demand through the API
3. As a background service

Usage:
  python sync_worker.py [--direction=both|to_dropbox|from_dropbox] [--verify] [--force]
"""

import os
import sys
import time
import logging
import json
import argparse
import datetime
import hashlib
import threading
from pathlib import Path

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("sync_worker.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("sync-worker")

# Constants
SYNC_LOCK_FILE = ".sync_in_progress"
SYNC_STATUS_FILE = "sync_status.json"

def get_sync_status():
    """Get the current synchronization status"""
    if os.path.exists(SYNC_STATUS_FILE):
        try:
            with open(SYNC_STATUS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading sync status file: {str(e)}")
    
    # Default status if file doesn't exist or can't be read
    return {
        "last_sync": None,
        "last_successful_sync": None,
        "total_syncs": 0,
        "successful_syncs": 0,
        "files_synced": 0,
        "last_errors": [],
        "in_progress": False,
        "history": []
    }

def update_sync_status(status, start_time=None, end_time=None, success=None, 
                       errors=None, files_synced=None, in_progress=None):
    """Update the synchronization status file"""
    try:
        # Make a copy to avoid modifying the input dict
        updated_status = status.copy()
        
        if start_time is not None:
            updated_status["last_sync"] = start_time.isoformat()
        
        if end_time is not None:
            updated_status["last_sync_duration"] = (end_time - datetime.datetime.fromisoformat(updated_status["last_sync"])).total_seconds()
        
        if success is not None:
            updated_status["total_syncs"] += 1
            if success:
                updated_status["successful_syncs"] += 1
                updated_status["last_successful_sync"] = datetime.datetime.now().isoformat()
        
        if errors is not None:
            updated_status["last_errors"] = errors
        
        if files_synced is not None:
            updated_status["files_synced"] = files_synced
        
        if in_progress is not None:
            updated_status["in_progress"] = in_progress
        
        # Add to history
        if end_time is not None:
            history_entry = {
                "start_time": updated_status["last_sync"],
                "end_time": end_time.isoformat(),
                "duration": updated_status["last_sync_duration"],
                "success": success,
                "files_synced": files_synced,
                "errors": errors if errors else []
            }
            
            # Keep last 10 entries in history
            updated_status["history"] = [history_entry] + updated_status.get("history", [])[:9]
        
        # Write the updated status
        with open(SYNC_STATUS_FILE, 'w') as f:
            json.dump(updated_status, f, indent=2)
        
        return updated_status
    except Exception as e:
        logger.error(f"Error updating sync status file: {str(e)}")
        return status

def acquire_sync_lock():
    """Acquire a lock for synchronization to prevent concurrent syncs"""
    try:
        if os.path.exists(SYNC_LOCK_FILE):
            # Check if the lock is stale (older than 1 hour)
            mtime = os.path.getmtime(SYNC_LOCK_FILE)
            if time.time() - mtime > 3600:  # 1 hour
                logger.warning("Found stale sync lock file, removing it")
                os.remove(SYNC_LOCK_FILE)
            else:
                logger.warning("Sync already in progress, cannot acquire lock")
                return False
        
        # Create the lock file
        with open(SYNC_LOCK_FILE, 'w') as f:
            f.write(f"{os.getpid()} {datetime.datetime.now().isoformat()}")
        
        return True
    except Exception as e:
        logger.error(f"Error acquiring sync lock: {str(e)}")
        return False

def release_sync_lock():
    """Release the synchronization lock"""
    try:
        if os.path.exists(SYNC_LOCK_FILE):
            os.remove(SYNC_LOCK_FILE)
        return True
    except Exception as e:
        logger.error(f"Error releasing sync lock: {str(e)}")
        return False

def sync_to_dropbox(verify=True, force=False, debug=False):
    """
    Synchronize data from local storage to Dropbox
    
    Args:
        verify (bool): Whether to verify the uploaded files
        force (bool): Whether to force sync even for already synced files
        debug (bool): Enable debug logging
        
    Returns:
        dict: Synchronization results
    """
    try:
        import dropbox_sync
    except ImportError:
        logger.error("dropbox_sync module not found. Please check your installation.")
        return {
            "success": False,
            "error": "dropbox_sync module not found",
            "files_synced": 0,
            "files_failed": 0,
            "errors": ["Import error: dropbox_sync module not found"]
        }
    
    # Ensure we're in the right directory (app root)
    script_dir = Path(__file__).parent.absolute()
    os.chdir(script_dir)
    
    # Make sure the data directory exists
    data_dir = dropbox_sync.DATA_DIR
    if not os.path.exists(data_dir):
        logger.warning(f"Data directory {data_dir} does not exist. Nothing to sync.")
        return {
            "success": True,
            "files_synced": 0,
            "files_failed": 0,
            "errors": []
        }
    
    logger.info(f"Starting sync to Dropbox (verify={verify}, force={force}, debug={debug})")
    
    # Initialize result tracking
    result = {
        "success": False,
        "files_synced": 0,
        "files_failed": 0,
        "errors": [],
        "details": {}
    }
    
    try:
        # Get Dropbox client
        try:
            dbx = dropbox_sync.get_dropbox_client(debug=debug)
            logger.info("Successfully connected to Dropbox")
        except Exception as e:
            error_msg = f"Failed to connect to Dropbox: {str(e)}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            return result
        
        # Ensure folder structure exists
        try:
            folders_created = dropbox_sync.ensure_dropbox_folders(dbx, debug=debug)
            if not folders_created:
                error_msg = "Failed to create/verify Dropbox folder structure"
                logger.error(error_msg)
                result["errors"].append(error_msg)
                return result
        except Exception as e:
            error_msg = f"Error ensuring folder structure: {str(e)}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            return result
        
        # Process all sender directories
        senders = [d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))]
        logger.info(f"Found {len(senders)} sender directories to process")
        
        for sender in senders:
            sender_path = os.path.join(data_dir, sender)
            
            # Create sender folder in Dropbox if needed
            dropbox_sender_path = f"{dropbox_sync.DROPBOX_BACKUP_FOLDER}/{sender}"
            try:
                sender_folder_created = dropbox_sync.create_dropbox_path(dbx, dropbox_sender_path, debug=debug)
                if not sender_folder_created:
                    error_msg = f"Failed to create sender folder in Dropbox: {dropbox_sender_path}"
                    logger.error(error_msg)
                    result["errors"].append(error_msg)
                    continue
            except Exception as e:
                error_msg = f"Error creating sender folder {sender}: {str(e)}"
                logger.error(error_msg)
                result["errors"].append(error_msg)
                continue
            
            # Process JSON files in this sender directory
            json_files = [f for f in os.listdir(sender_path) if f.endswith('.json')]
            logger.info(f"Found {len(json_files)} JSON files for sender {sender}")
            
            for json_file in json_files:
                local_file_path = os.path.join(sender_path, json_file)
                submission_id = json_file.replace('.json', '')
                
                # Check if the file has already been synced (unless force=True)
                needs_sync = True
                if not force:
                    try:
                        with open(local_file_path, 'r') as f:
                            file_data = json.load(f)
                            
                        if '_sync' in file_data and 'dropbox' in file_data['_sync']:
                            sync_info = file_data['_sync']['dropbox']
                            
                            # Check if it's been verified and not too old (< 1 day)
                            if sync_info.get('verified', False):
                                sync_time = datetime.datetime.fromisoformat(sync_info['timestamp'])
                                now = datetime.datetime.now()
                                if (now - sync_time).total_seconds() < 86400:  # 24 hours
                                    logger.info(f"Skipping already synced file: {json_file}")
                                    needs_sync = False
                    except Exception as e:
                        logger.warning(f"Error checking sync status for {json_file}: {str(e)}")
                
                if needs_sync:
                    logger.info(f"Syncing file: {json_file}")
                    
                    # Use the enhanced backup function with retry and verification
                    backup_result = dropbox_sync.backup_specific_file(
                        sender, 
                        submission_id, 
                        debug=debug,
                        verify_upload=verify,
                        max_retries=3
                    )
                    
                    if backup_result['success']:
                        logger.info(f"Successfully synced {json_file} to Dropbox")
                        result["files_synced"] += 1
                    else:
                        error_msg = f"Failed to sync {json_file}: {backup_result.get('error', 'Unknown error')}"
                        logger.error(error_msg)
                        result["errors"].append(error_msg)
                        result["files_failed"] += 1
        
        # Set overall success status
        if result["files_failed"] == 0:
            result["success"] = True
        elif result["files_synced"] > 0:
            result["success"] = True  # Partial success
            
        logger.info(f"Sync to Dropbox completed: {result['files_synced']} synced, {result['files_failed']} failed")
        return result
        
    except Exception as e:
        error_msg = f"Unexpected error during sync to Dropbox: {str(e)}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
        return result

def sync_from_dropbox(verify=True, force=False, debug=False):
    """
    Synchronize data from Dropbox to local storage
    
    Args:
        verify (bool): Whether to verify the downloaded files
        force (bool): Whether to force sync even if local files exist
        debug (bool): Enable debug logging
        
    Returns:
        dict: Synchronization results
    """
    try:
        import dropbox_sync
    except ImportError:
        logger.error("dropbox_sync module not found. Please check your installation.")
        return {
            "success": False,
            "error": "dropbox_sync module not found",
            "files_synced": 0,
            "files_failed": 0,
            "errors": ["Import error: dropbox_sync module not found"]
        }
    
    # Ensure we're in the right directory (app root)
    script_dir = Path(__file__).parent.absolute()
    os.chdir(script_dir)
    
    # Make sure the data directory exists
    data_dir = dropbox_sync.DATA_DIR
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    
    logger.info(f"Starting sync from Dropbox (verify={verify}, force={force}, debug={debug})")
    
    # Initialize result tracking
    result = {
        "success": False,
        "files_synced": 0,
        "files_failed": 0,
        "errors": [],
        "details": {}
    }
    
    try:
        # Get Dropbox client
        try:
            dbx = dropbox_sync.get_dropbox_client(debug=debug)
            logger.info("Successfully connected to Dropbox")
        except Exception as e:
            error_msg = f"Failed to connect to Dropbox: {str(e)}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            return result
        
        # Check if backup folder exists in Dropbox
        try:
            dbx.files_get_metadata(dropbox_sync.DROPBOX_BACKUP_FOLDER)
        except Exception as e:
            error_msg = f"Backup folder {dropbox_sync.DROPBOX_BACKUP_FOLDER} not found in Dropbox"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            return result
        
        # Get all sender folders in Dropbox
        try:
            folder_content = dropbox_sync.list_dropbox_files(dbx, dropbox_sync.DROPBOX_BACKUP_FOLDER)
            sender_folders = [f for f in folder_content if isinstance(f, dropbox.files.FolderMetadata)]
            logger.info(f"Found {len(sender_folders)} sender folders in Dropbox")
        except Exception as e:
            error_msg = f"Error listing folders in Dropbox: {str(e)}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            return result
        
        # Process each sender folder
        for folder in sender_folders:
            sender_name = folder.name
            dropbox_sender_path = f"{dropbox_sync.DROPBOX_BACKUP_FOLDER}/{sender_name}"
            local_sender_path = os.path.join(data_dir, sender_name)
            
            # Ensure local sender directory exists
            if not os.path.exists(local_sender_path):
                os.makedirs(local_sender_path)
                logger.info(f"Created local sender directory: {local_sender_path}")
            
            # Get all files in this sender folder
            try:
                sender_files = dropbox_sync.list_dropbox_files(dbx, dropbox_sender_path)
                json_files = [f for f in sender_files if isinstance(f, dropbox.files.FileMetadata) and f.name.endswith('.json')]
                logger.info(f"Found {len(json_files)} JSON files for sender {sender_name} in Dropbox")
            except Exception as e:
                error_msg = f"Error listing files for sender {sender_name}: {str(e)}"
                logger.error(error_msg)
                result["errors"].append(error_msg)
                continue
            
            # Process each JSON file
            for file in json_files:
                filename = file.name
                dropbox_file_path = f"{dropbox_sender_path}/{filename}"
                local_file_path = os.path.join(local_sender_path, filename)
                
                # Check if we should download this file
                needs_download = force or not os.path.exists(local_file_path)
                
                # If file exists locally, check if Dropbox version is newer
                if not needs_download and not force:
                    try:
                        local_mtime = os.path.getmtime(local_file_path)
                        dropbox_mtime = file.server_modified.timestamp()
                        
                        if dropbox_mtime > local_mtime:
                            logger.info(f"Dropbox version of {filename} is newer than local")
                            needs_download = True
                    except Exception as e:
                        logger.warning(f"Error comparing file times for {filename}: {str(e)}")
                        needs_download = True
                
                if needs_download:
                    logger.info(f"Downloading {filename} from Dropbox")
                    
                    try:
                        # Download the file
                        metadata, response = dbx.files_download(dropbox_file_path)
                        file_content = response.content
                        
                        # Calculate hash for verification
                        dropbox_hash = None
                        if verify:
                            dropbox_hash = hashlib.md5(file_content).hexdigest()
                        
                        # Write to local file
                        with open(local_file_path, 'wb') as f:
                            f.write(file_content)
                        
                        # Verify if requested
                        if verify:
                            try:
                                with open(local_file_path, 'rb') as f:
                                    local_hash = hashlib.md5(f.read()).hexdigest()
                                
                                if local_hash != dropbox_hash:
                                    error_msg = f"Verification failed for {filename} - hash mismatch"
                                    logger.error(error_msg)
                                    result["errors"].append(error_msg)
                                    result["files_failed"] += 1
                                    continue
                            except Exception as e:
                                logger.warning(f"Error verifying downloaded file {filename}: {str(e)}")
                        
                        # Add sync metadata to the file
                        try:
                            with open(local_file_path, 'r') as f:
                                file_data = json.load(f)
                            
                            if '_sync' not in file_data:
                                file_data['_sync'] = {}
                            
                            file_data['_sync']['dropbox_downloaded'] = {
                                'timestamp': datetime.datetime.now().isoformat(),
                                'path': dropbox_file_path,
                                'verified': verify,
                                'server_modified': metadata.server_modified.isoformat()
                            }
                            
                            with open(local_file_path, 'w') as f:
                                json.dump(file_data, f, indent=2)
                        except Exception as e:
                            logger.warning(f"Error adding sync metadata to {filename}: {str(e)}")
                        
                        logger.info(f"Successfully downloaded {filename} from Dropbox")
                        result["files_synced"] += 1
                        
                    except Exception as e:
                        error_msg = f"Error downloading {filename}: {str(e)}"
                        logger.error(error_msg)
                        result["errors"].append(error_msg)
                        result["files_failed"] += 1
        
        # Set overall success status
        if result["files_failed"] == 0:
            result["success"] = True
        elif result["files_synced"] > 0:
            result["success"] = True  # Partial success
            
        logger.info(f"Sync from Dropbox completed: {result['files_synced']} synced, {result['files_failed']} failed")
        return result
        
    except Exception as e:
        error_msg = f"Unexpected error during sync from Dropbox: {str(e)}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
        return result

def two_way_sync(verify=True, force=False, debug=False):
    """
    Perform a two-way synchronization between local storage and Dropbox.
    First syncs from Dropbox to local, then from local to Dropbox.
    
    Args:
        verify (bool): Whether to verify file transfers
        force (bool): Whether to force sync all files
        debug (bool): Enable debug logging
        
    Returns:
        dict: Synchronization results
    """
    logger.info(f"Starting two-way sync (verify={verify}, force={force}, debug={debug})")
    
    # First sync from Dropbox to local
    from_result = sync_from_dropbox(verify=verify, force=force, debug=debug)
    
    # Then sync from local to Dropbox
    to_result = sync_to_dropbox(verify=verify, force=force, debug=debug)
    
    # Combine results
    combined_result = {
        "success": from_result.get("success", False) and to_result.get("success", False),
        "from_dropbox": {
            "files_synced": from_result.get("files_synced", 0),
            "files_failed": from_result.get("files_failed", 0)
        },
        "to_dropbox": {
            "files_synced": to_result.get("files_synced", 0),
            "files_failed": to_result.get("files_failed", 0)
        },
        "total_synced": from_result.get("files_synced", 0) + to_result.get("files_synced", 0),
        "total_failed": from_result.get("files_failed", 0) + to_result.get("files_failed", 0),
        "errors": from_result.get("errors", []) + to_result.get("errors", [])
    }
    
    logger.info(f"Two-way sync completed: {combined_result['total_synced']} files synced, {combined_result['total_failed']} failed")
    return combined_result

def run_sync(direction="both", verify=True, force=False, debug=False):
    """
    Run a synchronization job with the specified parameters.
    
    Args:
        direction (str): Sync direction - "both", "to_dropbox", or "from_dropbox"
        verify (bool): Whether to verify file transfers
        force (bool): Whether to force sync all files
        debug (bool): Enable debug logging
        
    Returns:
        dict: Synchronization results
    """
    # First try to acquire the lock
    if not acquire_sync_lock():
        return {
            "success": False,
            "error": "Sync already in progress",
            "locked": True
        }
    
    # Get current status
    status = get_sync_status()
    
    try:
        # Mark sync as in progress
        start_time = datetime.datetime.now()
        status = update_sync_status(status, start_time=start_time, in_progress=True)
        
        # Run the appropriate sync based on direction
        if direction == "both":
            result = two_way_sync(verify=verify, force=force, debug=debug)
        elif direction == "to_dropbox":
            result = sync_to_dropbox(verify=verify, force=force, debug=debug)
        elif direction == "from_dropbox":
            result = sync_from_dropbox(verify=verify, force=force, debug=debug)
        else:
            raise ValueError(f"Invalid sync direction: {direction}")
        
        # Update the sync status
        end_time = datetime.datetime.now()
        status = update_sync_status(
            status,
            end_time=end_time,
            success=result["success"],
            errors=result.get("errors", []),
            files_synced=result.get("total_synced", result.get("files_synced", 0)),
            in_progress=False
        )
        
        return result
    
    except Exception as e:
        error_msg = f"Sync failed with error: {str(e)}"
        logger.error(error_msg)
        
        # Update status with error
        end_time = datetime.datetime.now()
        status = update_sync_status(
            status,
            end_time=end_time,
            success=False,
            errors=[error_msg],
            in_progress=False
        )
        
        return {
            "success": False,
            "error": error_msg,
            "files_synced": 0,
            "files_failed": 0
        }
    
    finally:
        # Always release the lock
        release_sync_lock()

def main():
    """Main function when run as a script"""
    parser = argparse.ArgumentParser(description="Synchronize data with Dropbox")
    parser.add_argument("--direction", choices=["both", "to_dropbox", "from_dropbox"], default="both", help="Synchronization direction")
    parser.add_argument("--verify", action="store_true", help="Verify file transfers")
    parser.add_argument("--force", action="store_true", help="Force sync all files")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()
    
    result = run_sync(
        direction=args.direction,
        verify=args.verify,
        force=args.force,
        debug=args.debug
    )
    
    # Print summary to stdout
    success_status = "Successful" if result.get("success", False) else "Failed"
    synced = result.get("total_synced", result.get("files_synced", 0))
    failed = result.get("total_failed", result.get("files_failed", 0))
    
    print(f"Sync {success_status}: {synced} files synced, {failed} files failed")
    
    if failed > 0 and "errors" in result and result["errors"]:
        print("\nErrors:")
        for error in result["errors"][:5]:  # Show first 5 errors
            print(f"- {error}")
        
        if len(result["errors"]) > 5:
            print(f"... and {len(result['errors']) - 5} more errors")
    
    return 0 if result.get("success", False) else 1

if __name__ == "__main__":
    sys.exit(main())
