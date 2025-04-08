import os
import json
import time
import datetime
import logging
import threading
from flask import Flask, Blueprint, request, render_template, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Import dropbox for type checking
try:
    import dropbox
    DROPBOX_MODULE_AVAILABLE = True
except ImportError:
    DROPBOX_MODULE_AVAILABLE = False

# Import Dropbox sync module (if available)
try:
    import dropbox_sync
    DROPBOX_SYNC_AVAILABLE = True
    
    # Also try to import dropbox_primary module
    try:
        import dropbox_primary
        DROPBOX_PRIMARY_AVAILABLE = True
    except ImportError:
        DROPBOX_PRIMARY_AVAILABLE = False
        
except ImportError:
    DROPBOX_SYNC_AVAILABLE = False
    DROPBOX_PRIMARY_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("webhook-app")

# Load environment variables from .env file if present
load_dotenv()

app = Flask(__name__)
# Set application start time for uptime tracking
app.start_time = time.time()

# Data directory for storing JSON submissions
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Check if auto backup is enabled
ENABLE_AUTO_BACKUP = os.getenv('ENABLE_AUTO_BACKUP', 'False').lower() in ('true', '1', 't')

def get_sender_dirs():
    """Get a list of all sender directories"""
    if not os.path.exists(DATA_DIR):
        return []
    return [d for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d))]

def get_sender_submissions(sender):
    """
    Get a list of all submissions for a sender.
    Checks both local storage and Dropbox to ensure completeness.
    """
    sender = secure_filename(sender)
    submissions = []
    local_ids = set()  # To track IDs we've already seen
    
    # Step 1: Get submissions from local storage first
    sender_dir = os.path.join(DATA_DIR, sender)
    if os.path.exists(sender_dir):
        for filename in os.listdir(sender_dir):
            if filename.endswith('.json'):
                submission_id = filename.replace('.json', '')
                local_ids.add(submission_id)  # Track this ID
                
                file_path = os.path.join(sender_dir, filename)
                try:
                    with open(file_path, 'r') as f:
                        try:
                            metadata = json.load(f)
                            submissions.append({
                                'id': submission_id,
                                'title': metadata.get('_meta', {}).get('title', 'Untitled'),
                                'timestamp': metadata.get('_meta', {}).get('timestamp', 'Unknown'),
                                'size': os.path.getsize(file_path),
                                'from': 'local'
                            })
                        except json.JSONDecodeError:
                            # Handle corrupted JSON files
                            submissions.append({
                                'id': submission_id,
                                'title': 'Corrupted Data',
                                'timestamp': 'Unknown',
                                'size': os.path.getsize(file_path),
                                'from': 'local',
                                'corrupted': True
                            })
                except Exception as e:
                    logger.warning(f"Error processing local file {file_path}: {str(e)}")
    
    # Step 2: Check Dropbox for any additional files (if Dropbox is available)
    if DROPBOX_SYNC_AVAILABLE:
        try:
            # Try to import needed modules
            import dropbox_sync
            
            # Get Dropbox client
            dbx = dropbox_sync.get_dropbox_client()
            
            # Construct Dropbox sender path
            dropbox_sender_path = f"{dropbox_sync.DROPBOX_BACKUP_FOLDER}/{sender}"
            
            try:
                # List files in this folder
                folder_content = dropbox_sync.list_dropbox_files(dbx, dropbox_sender_path)
                
                # Process each file
                for file in folder_content:
                    # Check if the file is a FileMetadata object without directly using the dropbox module
                    if hasattr(file, 'name') and getattr(file, 'is_downloadable', True) and file.name.endswith('.json'):
                        
                        submission_id = file.name.replace('.json', '')
                        
                        # Skip if we already have this from local storage
                        if submission_id in local_ids:
                            continue
                        
                        # This file exists in Dropbox but not locally
                        try:
                            # Download the file from Dropbox
                            dropbox_file_path = f"{dropbox_sender_path}/{file.name}"
                            metadata, response = dbx.files_download(dropbox_file_path)
                            file_content = response.content
                            
                            # Try to parse as JSON
                            try:
                                data = json.loads(file_content.decode('utf-8'))
                                
                                # Add to our list
                                submissions.append({
                                    'id': submission_id,
                                    'title': data.get('_meta', {}).get('title', 'Untitled'),
                                    'timestamp': data.get('_meta', {}).get('timestamp', 'Unknown'),
                                    'size': len(file_content),
                                    'from': 'dropbox'
                                })
                                
                                # Save locally for future access
                                try:
                                    # Ensure the local directory exists
                                    local_file_path = os.path.join(DATA_DIR, sender, file.name)
                                    os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
                                    
                                    # Save to local file
                                    with open(local_file_path, 'wb') as f:
                                        f.write(file_content)
                                        
                                    logger.info(f"Downloaded submission from Dropbox to local: {submission_id}")
                                except Exception as save_e:
                                    logger.warning(f"Could not save Dropbox file to local: {str(save_e)}")
                                    
                            except json.JSONDecodeError:
                                # Handle corrupted JSON files
                                submissions.append({
                                    'id': submission_id,
                                    'title': 'Corrupted Data',
                                    'timestamp': file.server_modified.isoformat(),
                                    'size': len(file_content),
                                    'from': 'dropbox',
                                    'corrupted': True
                                })
                        except Exception as download_e:
                            logger.warning(f"Error downloading file from Dropbox: {str(download_e)}")
                
            except Exception as list_e:
                logger.warning(f"Error listing files in Dropbox: {str(list_e)}")
                
        except Exception as e:
            logger.warning(f"Error checking Dropbox for submissions: {str(e)}")
    
    # Sort by timestamp (newest first)
    submissions.sort(key=lambda x: x['timestamp'], reverse=True)
    return submissions

def get_submission_data(sender, submission_id):
    """
    Get the data for a specific submission.
    Checks local storage first, then Dropbox if not found locally.
    """
    sender = secure_filename(sender)
    file_path = os.path.join(DATA_DIR, sender, f"{submission_id}.json")
    
    # First, try to get from local storage
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                # Remove metadata from the returned data
                if '_meta' in data:
                    data_without_meta = {k: v for k, v in data.items() if k != '_meta'}
                    return data_without_meta
                return data
        except json.JSONDecodeError:
            logger.warning(f"Corrupted local JSON file: {file_path}")
            # Don't return error yet - try Dropbox first
    
    # If not found locally or corrupted, try Dropbox if available
    if DROPBOX_SYNC_AVAILABLE:
        try:
            # Try to import the needed modules
            import dropbox_sync
            import dropbox_primary
            import io
            
            logger.info(f"File not found locally, checking Dropbox: {sender}/{submission_id}")
            
            # Get the Dropbox client
            dbx = dropbox_sync.get_dropbox_client()
            
            # Construct the Dropbox path
            dropbox_sender_path = f"{dropbox_sync.DROPBOX_BACKUP_FOLDER}/{sender}"
            dropbox_file_path = f"{dropbox_sender_path}/{submission_id}.json"
            
            # Try to download the file from Dropbox
            try:
                metadata, response = dbx.files_download(dropbox_file_path)
                file_content = response.content
                
                # Parse the JSON data
                data = json.loads(file_content.decode('utf-8'))
                
                # Save a local copy for future access
                try:
                    # Ensure the local directory exists
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    
                    # Save to local file
                    with open(file_path, 'wb') as f:
                        f.write(file_content)
                    
                    logger.info(f"Downloaded and saved file from Dropbox to local: {file_path}")
                except Exception as save_e:
                    logger.warning(f"Could not save Dropbox file to local storage: {str(save_e)}")
                
                # Remove metadata from the returned data
                if '_meta' in data:
                    data_without_meta = {k: v for k, v in data.items() if k != '_meta'}
                    return data_without_meta
                return data
                
            except Exception as download_e:
                logger.warning(f"File not found in Dropbox: {str(download_e)}")
                
        except Exception as e:
            logger.warning(f"Error checking Dropbox for file: {str(e)}")
    
    # If we got here, the file was not found locally or in Dropbox
    return None

@app.route('/')
def index():
    """Home page showing all senders"""
    senders = get_sender_dirs()
    return render_template('index.html', senders=senders)

@app.route('/sender/<sender>')
def view_sender(sender):
    """Page showing all submissions for a specific sender"""
    sender = secure_filename(sender)
    submissions = get_sender_submissions(sender)
    return render_template('sender.html', sender=sender, submissions=submissions)

@app.route('/submission/<sender>/<submission_id>')
def view_submission(sender, submission_id):
    """Page showing a specific submission"""
    sender = secure_filename(sender)
    data = get_submission_data(sender, submission_id)
    if data is None:
        return redirect(url_for('index'))
    
    submissions = get_sender_submissions(sender)
    submission_meta = next((s for s in submissions if s['id'] == submission_id), None)
    
    return render_template('submission.html', 
                          sender=sender, 
                          submission_id=submission_id,
                          submission_meta=submission_meta,
                          data=data)

@app.route('/api/webhook', methods=['POST'])
def webhook():
    """
    Endpoint for receiving webhook data.
    First saves data to Dropbox, then syncs to local storage.
    """
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.json
    
    # Check for debug mode and sync options in the request
    debug_mode = data.get('debug_dropbox', False)
    verify_upload = data.get('verify_upload', True)
    max_retries = int(data.get('max_retries', 3))
    sync_to_local = data.get('sync_to_local', True)  # Whether to sync to local storage
    
    # Extract sender from data or use IP address
    sender = data.get('sender', request.remote_addr)
    sender = secure_filename(sender)
    
    # Add IP address to the metadata
    data_to_store = data.copy()
    if '_meta' not in data_to_store:
        data_to_store['_meta'] = {}
    
    data_to_store['_meta']['ip'] = request.remote_addr
    
    # Prepare the response skeleton
    response = {
        "success": False,
        "error": None,
        "dropbox_primary": True,  # Flag indicating we're using Dropbox as primary storage
        "url": None  # Will be filled later
    }
    
    # Check if Dropbox modules are available and enabled
    if not DROPBOX_SYNC_AVAILABLE:
        error_msg = "Dropbox sync module is not available"
        logger.error(error_msg)
        response["error"] = error_msg
        response["fix_instructions"] = "Install required packages: pip install -r requirements.txt"
        return jsonify(response), 500
    
    # Check if the dropbox_primary module is available
    if not DROPBOX_PRIMARY_AVAILABLE:
        error_msg = "Dropbox primary storage module is not available"
        logger.error(error_msg)
        response["error"] = error_msg
        response["fix_instructions"] = "Ensure dropbox_primary.py is in the application directory"
        return jsonify(response), 500
    
    # Log the start of the process
    logger.info(f"Processing webhook data for sender {sender} with Dropbox as primary storage")
    
    # Save data to Dropbox first, then sync to local if requested
    try:
        # Use the new dropbox_primary module to save data directly to Dropbox
        # and optionally sync back to local storage
        result = dropbox_primary.save_webhook_data(
            data=data_to_store,
            sender=sender,
            debug=debug_mode,
            sync_to_local=sync_to_local,
            verify=verify_upload
        )
        
        # Extract the submission ID and update our response
        submission_id = result['submission_id']
        
        # Update the response with appropriate information
        response["success"] = result['success']
        response["id"] = submission_id
        response["dropbox_result"] = result['dropbox']
        
        # Add local storage information if applicable
        if sync_to_local and result.get('local'):
            response["local_storage"] = result['local']
            
            # Only generate a URL if we have local storage
            if result['local'].get('success'):
                local_path = result['local'].get('local_path')
                response["url"] = url_for('view_submission', sender=sender, submission_id=submission_id, _external=True)
                response["file_saved_locally"] = os.path.exists(local_path) if local_path else False
        
        # If there was an error in the overall process, include it
        if result.get('error'):
            response["error"] = result['error']
        
        # Log detailed diagnostics if in debug mode
        if debug_mode:
            logger.info(f"Dropbox save details: {json.dumps(result.get('dropbox', {}).get('details', {}))}")
        
        # Update sync statistics if possible
        if result['success'] and DROPBOX_SYNC_AVAILABLE:
            try:
                import sync_worker
                status = sync_worker.get_sync_status()
                status["files_synced"] = status.get("files_synced", 0) + 1
                sync_worker.update_sync_status(status)
            except (ImportError, Exception) as e:
                if debug_mode:
                    logger.debug(f"Could not update sync statistics: {str(e)}")
                
    except Exception as e:
        error_msg = f"Error processing webhook data with Dropbox primary storage: {str(e)}"
        logger.error(error_msg)
        response["error"] = error_msg
        response["details"] = {"exception": str(e)}
        
        # Try to save locally as a fallback if Dropbox fails completely
        try:
            # Create directory for this sender if needed
            sender_dir = os.path.join(DATA_DIR, sender)
            if not os.path.exists(sender_dir):
                os.makedirs(sender_dir)
                
            # Generate a unique ID for this submission
            fallback_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S_fallback')
            
            # Save the data to a local file as fallback
            file_path = os.path.join(sender_dir, f"{fallback_id}.json")
            with open(file_path, 'w') as f:
                json.dump(data_to_store, f, indent=2)
                
            logger.info(f"Saved fallback copy to local storage: {file_path}")
            response["fallback_id"] = fallback_id
            response["fallback_saved"] = True
            response["url"] = url_for('view_submission', sender=sender, submission_id=fallback_id, _external=True)
            
            # Queue for later sync to Dropbox
            try:
                import sync_worker
                logger.info(f"Queuing fallback file for later sync to Dropbox: {sender}/{fallback_id}")
                
                # Record the fallback file in sync status
                status = sync_worker.get_sync_status()
                if "pending_sync" not in status:
                    status["pending_sync"] = []
                
                status["pending_sync"].append({
                    "sender": sender,
                    "submission_id": fallback_id,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "is_fallback": True,
                    "error": error_msg
                })
                
                sync_worker.update_sync_status(status)
                response["queued_for_sync"] = True
            except ImportError:
                logger.debug("sync_worker not available for fallback queuing")
                
        except Exception as fallback_error:
            logger.error(f"Fallback storage also failed: {str(fallback_error)}")
            response["fallback_error"] = str(fallback_error)
    
    # Check if HTML format is requested (rare for webhook but possible)
    best_format = request.accept_mimetypes.best_match(['application/json', 'text/html'])
    if best_format == 'text/html' or request.args.get('format') == 'html':
        return render_template('webhook_result.html', 
                              result=response, 
                              sender=sender,
                              submission_id=response.get("id", response.get("fallback_id")))
    
    # Otherwise return JSON (common for webhooks)
    return jsonify(response)

@app.route('/api/data')
def list_senders_api():
    """API endpoint to list all senders"""
    senders = get_sender_dirs()
    data = {"senders": senders}
    
    # Check if HTML format is requested
    best_format = request.accept_mimetypes.best_match(['application/json', 'text/html'])
    if best_format == 'text/html' or request.args.get('format') == 'html':
        return render_template('api_view.html', 
                              data=data, 
                              endpoint="senders")
    # Otherwise return JSON
    return jsonify(data)

@app.route('/api/data/<sender>')
def list_submissions_api(sender):
    """API endpoint to list all submissions for a sender"""
    sender = secure_filename(sender)
    submissions = get_sender_submissions(sender)
    data = {"sender": sender, "submissions": submissions}
    
    # Check if HTML format is requested
    best_format = request.accept_mimetypes.best_match(['application/json', 'text/html'])
    if best_format == 'text/html' or request.args.get('format') == 'html':
        return render_template('api_view.html', 
                              data=data, 
                              sender=sender,
                              endpoint="sender_submissions")
    # Otherwise return JSON
    return jsonify(data)

@app.route('/api/data/<sender>/<submission_id>')
def get_submission_api(sender, submission_id):
    """API endpoint to get a specific submission"""
    sender = secure_filename(sender)
    data = get_submission_data(sender, submission_id)
    if data is None:
        return jsonify({"error": "Submission not found"}), 404
    
    # Check if the client is requesting HTML (browser) or JSON (API)
    best_format = request.accept_mimetypes.best_match(['application/json', 'text/html'])
    if best_format == 'text/html' or request.args.get('format') == 'html':
        # If HTML is requested, display with nice UI
        return render_template('api_view.html', 
                              data=data, 
                              sender=sender, 
                              submission_id=submission_id,
                              endpoint="submission")
    # Otherwise return JSON
    return jsonify(data)

@app.route('/api/dropbox/sync', methods=['GET', 'POST'])
def sync_data():
    """
    Trigger a manual synchronization with Dropbox.
    This endpoint allows you to run an immediate sync job.
    
    Query parameters:
    - direction: "both", "to_dropbox", or "from_dropbox" (default: "both")
    - force: "true" or "false" - whether to force sync all files (default: false)
    - verify: "true" or "false" - whether to verify uploads/downloads (default: true)
    - format: "html" or "json" - response format (default based on Accept header)
    """
    try:
        # Import the sync worker
        import sync_worker
    except ImportError:
        error = {"error": "Sync worker module not available"}
        return jsonify(error), 500
    
    # Get sync parameters
    direction = request.args.get('direction', 'both')
    if direction not in ['both', 'to_dropbox', 'from_dropbox']:
        direction = 'both'
        
    force = request.args.get('force', 'false').lower() in ['true', '1', 't', 'yes']
    verify = request.args.get('verify', 'true').lower() in ['true', '1', 't', 'yes']
    
    # Handle different sync directions
    logger.info(f"Manual sync triggered: direction={direction}, force={force}, verify={verify}")
    
    # Run the sync in a separate thread to not block the response
    def run_sync_job():
        try:
            sync_worker.run_sync(
                direction=direction,
                force=force,
                verify=verify,
                debug=True  # Always use debug for manual syncs
            )
        except Exception as e:
            logger.error(f"Error in sync thread: {str(e)}")
    
    # Start the sync thread
    sync_thread = threading.Thread(target=run_sync_job)
    sync_thread.daemon = True
    sync_thread.start()
    
    # Prepare response based on what was requested
    result = {
        "success": True,
        "message": f"Sync job started with direction={direction}, force={force}, verify={verify}",
        "details": {
            "direction": direction,
            "force": force,
            "verify": verify
        }
    }
    
    # Check current sync status
    try:
        status = sync_worker.get_sync_status()
        result["current_status"] = status
    except Exception as e:
        logger.error(f"Error getting sync status: {str(e)}")
        result["current_status"] = {"error": str(e)}
    
    # Check if HTML format is requested
    best_format = request.accept_mimetypes.best_match(['application/json', 'text/html'])
    if best_format == 'text/html' or request.args.get('format') == 'html':
        return render_template('sync_started.html', result=result)
    
    # Otherwise return JSON
    return jsonify(result)

@app.route('/api/dropbox/sync/status', methods=['GET'])
def get_sync_status():
    """
    Get the current status of Dropbox synchronization.
    Shows sync history, statistics, and current state.
    """
    try:
        # Import the sync worker
        import sync_worker
    except ImportError:
        error = {"error": "Sync worker module not available"}
        return jsonify(error), 500
    
    # Get current sync status
    try:
        status = sync_worker.get_sync_status()
    except Exception as e:
        logger.error(f"Error getting sync status: {str(e)}")
        status = {"error": str(e)}
    
    # Check if HTML format is requested
    best_format = request.accept_mimetypes.best_match(['application/json', 'text/html'])
    if best_format == 'text/html' or request.args.get('format') == 'html':
        return render_template('api_view.html', 
                              data=status, 
                              endpoint="sync_status")
    
    # Otherwise return JSON
    return jsonify(status)

@app.route('/api/dropbox/test', methods=['GET'])
def test_dropbox_connection():
    """
    Test the Dropbox connection and folder creation functionality.
    This endpoint is useful for diagnosing Dropbox integration issues.
    """
    if not DROPBOX_SYNC_AVAILABLE:
        return jsonify({
            "success": False,
            "error": "Dropbox sync module is not available. Check if the required packages are installed.",
            "auto_backup_enabled": ENABLE_AUTO_BACKUP
        }), 500
    
    debug = request.args.get('debug', 'false').lower() == 'true'
    test_folder = request.args.get('folder', None)
    
    result = {
        "success": False,
        "auto_backup_enabled": ENABLE_AUTO_BACKUP,
        "details": {},
        "diagnostics": []
    }
    
    try:
        # Step 1: Check environment variables
        result["diagnostics"].append("Checking environment variables...")
        
        app_key = os.getenv("DROPBOX_APP_KEY")
        app_secret = os.getenv("DROPBOX_APP_SECRET")
        refresh_token = os.getenv("DROPBOX_REFRESH_TOKEN")
        
        if not app_key or not app_secret or not refresh_token:
            missing = []
            if not app_key: missing.append("DROPBOX_APP_KEY")
            if not app_secret: missing.append("DROPBOX_APP_SECRET")
            if not refresh_token: missing.append("DROPBOX_REFRESH_TOKEN")
            
            result["diagnostics"].append(f"Missing environment variables: {', '.join(missing)}")
            result["error"] = "Missing required Dropbox credentials. Check your .env file."
            return jsonify(result), 400
            
        result["diagnostics"].append("Environment variables found.")
        result["details"]["env_vars_present"] = True
        
        # Step 2: Get Dropbox client
        result["diagnostics"].append("Attempting to get Dropbox client...")
        try:
            dbx = dropbox_sync.get_dropbox_client(debug=debug)
            result["diagnostics"].append("Successfully obtained Dropbox client.")
            result["details"]["client_connected"] = True
            
            # Get account info
            account = dbx.users_get_current_account()
            result["details"]["account_name"] = account.name.display_name
            result["details"]["account_email"] = account.email
            result["diagnostics"].append(f"Connected as: {account.name.display_name} ({account.email})")
        except Exception as e:
            result["diagnostics"].append(f"Failed to connect to Dropbox: {str(e)}")
            result["error"] = f"Connection error: {str(e)}"
            return jsonify(result), 500
            
        # Step 3: Test folder creation
        result["diagnostics"].append("Testing folder creation...")
        
        # If a specific test folder was requested, use that
        if test_folder:
            test_path = f"{dropbox_sync.DROPBOX_BACKUP_FOLDER}/{test_folder}"
            result["diagnostics"].append(f"Creating test folder: {test_path}")
            
            try:
                success = dropbox_sync.create_dropbox_path(dbx, test_path, debug=debug)
                if success:
                    result["diagnostics"].append(f"Successfully created folder: {test_path}")
                    result["details"]["test_folder_created"] = True
                    result["details"]["test_folder_path"] = test_path
                else:
                    result["diagnostics"].append(f"Failed to create folder: {test_path}")
                    result["details"]["test_folder_created"] = False
                    result["error"] = "Failed to create test folder"
                    return jsonify(result), 500
            except Exception as e:
                result["diagnostics"].append(f"Error creating test folder: {str(e)}")
                result["error"] = f"Folder creation error: {str(e)}"
                return jsonify(result), 500
        
        # Otherwise, just ensure the main folders exist
        else:
            result["diagnostics"].append(f"Ensuring main backup folder structure...")
            try:
                folders_created = dropbox_sync.ensure_dropbox_folders(dbx, debug=debug)
                if folders_created:
                    result["diagnostics"].append(f"Successfully created/verified main folder structure")
                    result["details"]["folders_created"] = True
                else:
                    result["diagnostics"].append(f"Failed to create/verify main folder structure")
                    result["details"]["folders_created"] = False
                    result["error"] = "Failed to create main folders"
                    return jsonify(result), 500
            except Exception as e:
                result["diagnostics"].append(f"Error ensuring folders: {str(e)}")
                result["error"] = f"Folder structure error: {str(e)}"
                return jsonify(result), 500
        
        # Step 4: List the contents of the backup folder
        result["diagnostics"].append(f"Listing contents of backup folder...")
        try:
            folder_content = dropbox_sync.list_dropbox_files(dbx, dropbox_sync.DROPBOX_BACKUP_FOLDER)
            folders = [f.name for f in folder_content if isinstance(f, dropbox.files.FolderMetadata)]
            files = [f.name for f in folder_content if isinstance(f, dropbox.files.FileMetadata)]
            
            result["details"]["backup_folder_contents"] = {
                "folders": folders,
                "files": files,
                "total_items": len(folder_content)
            }
            
            result["diagnostics"].append(f"Found {len(folders)} folders and {len(files)} files in backup folder")
        except Exception as e:
            result["diagnostics"].append(f"Error listing backup folder: {str(e)}")
            # This is just diagnostic info, so continue even if it fails
        
        # All tests passed
        result["success"] = True
        result["diagnostics"].append("All tests passed. Dropbox integration is working properly.")
        
        return jsonify(result)
        
    except Exception as e:
        result["diagnostics"].append(f"Unexpected error: {str(e)}")
        result["error"] = f"Test failed: {str(e)}"
        return jsonify(result), 500

# Health check endpoint for the keep-alive service
@app.route('/health')
def health_check():
    """Health check endpoint for the keep-alive service"""
    # Check if this is a keep-alive request
    is_keep_alive = request.headers.get('X-Keep-Alive') in ('true', 'test')
    
    # Basic health check - could be expanded to check database, Dropbox connection, etc.
    status = {
        "status": "healthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "version": "1.0.0",
        "uptime": int(time.time() - app.start_time) if hasattr(app, 'start_time') else 0,
        "environment": {
            "python_version": os.environ.get("PYTHON_VERSION", "Unknown"),
            "flask_version": getattr(Flask, "__version__", "Unknown"),
            "render": os.environ.get("RENDER", "Not set"),
            "port": os.environ.get("PORT", "5000")
        }
    }
    
    # Only log non-keep-alive requests to avoid flooding the logs
    if not is_keep_alive:
        logger.info(f"Health check requested from {request.remote_addr}")
    
    return jsonify(status)

# Keep-alive status endpoint
@app.route('/keep-alive/status')
def keep_alive_status():
    """Endpoint to view the keep-alive service status"""
    try:
        import keep_alive
        status = keep_alive.get_keep_alive_status()
        return render_template('keep_alive_status.html', status=status)
    except ImportError:
        return jsonify({"error": "Keep-alive service is not available"}), 404

@app.route('/api/keep-alive/test', methods=['GET', 'POST'])
def test_keep_alive():
    """
    Test endpoint to manually verify the keep-alive service.
    This runs the initialization process again and returns detailed results.
    """
    try:
        # Import the keep_alive module
        try:
            import keep_alive
            has_module = True
        except ImportError:
            has_module = False
        
        # Get current status if available
        current_status = None
        if has_module:
            try:
                current_status = keep_alive.get_keep_alive_status()
            except:
                pass
        
        # Run the initialization process to ensure it's running
        # Force environment variables for testing
        os.environ['KEEP_ALIVE_ENABLED'] = 'true'
        os.environ['FORCE_KEEP_ALIVE'] = 'true'
        
        # Make sure we have a test URL
        if not os.environ.get('APP_URL') and not os.environ.get('RENDER_EXTERNAL_URL'):
            hostname = request.host.split(':')[0]
            port = request.host.split(':')[1] if ':' in request.host else '5000'
            test_url = f"http://{hostname}:{port}"
            os.environ['APP_URL'] = test_url
        
        # Run the full initialization
        init_result = init_keep_alive_service(app=current_app)
        
        # Prepare comprehensive result
        result = {
            "has_module": has_module,
            "current_status": current_status,
            "init_result": init_result,
            "environment": {
                "KEEP_ALIVE_ENABLED": os.environ.get('KEEP_ALIVE_ENABLED'),
                "FORCE_KEEP_ALIVE": os.environ.get('FORCE_KEEP_ALIVE'),
                "APP_URL": os.environ.get('APP_URL'),
                "RENDER_EXTERNAL_URL": os.environ.get('RENDER_EXTERNAL_URL'),
                "RENDER": os.environ.get('RENDER'),
                "HOST": os.environ.get('HOST'),
                "PORT": os.environ.get('PORT')
            },
            "app_info": {
                "has_keep_alive_init_status": hasattr(current_app, 'keep_alive_init_status'),
                "has_keep_alive_init_started": hasattr(current_app, 'keep_alive_init_started'),
                "has_keep_alive_init_completed": hasattr(current_app, 'keep_alive_init_completed')
            }
        }
        
        # If we still don't have the module, suggest checks
        if not has_module:
            result["suggestions"] = [
                "Check that keep_alive.py exists in the application directory",
                "Verify keep_alive.py has no syntax errors",
                "Ensure the file has proper permissions",
                "Check for ImportError details in the application logs"
            ]
            
        # If HTML format is requested
        best_format = request.accept_mimetypes.best_match(['application/json', 'text/html'])
        if best_format == 'text/html' or request.args.get('format') == 'html':
            return render_template('keep_alive_test.html', result=result)
            
        return jsonify(result)
        
    except Exception as e:
        error_result = {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }
        return jsonify(error_result), 500

# Initialize the keep-alive service
def init_keep_alive_service(app=None):
    """
    Initialize the keep-alive service with the application URL
    
    Args:
        app: Flask application instance (optional)
    
    Returns:
        dict: Status information about the initialization process
    """
    result = {
        "success": False,
        "enabled": False,
        "app_url": None,
        "interval_minutes": None,
        "errors": [],
        "warnings": [],
        "diagnostics": [],
        "environment": {}
    }
    
    # 1. Check if service should be enabled
    keep_alive_enabled = os.environ.get('KEEP_ALIVE_ENABLED', '').lower() in ('true', 'yes', '1', 't')
    render_enabled = os.environ.get('RENDER', '').lower() in ('true', 'yes', '1', 't')
    force_enabled = os.environ.get('FORCE_KEEP_ALIVE', '').lower() in ('true', 'yes', '1', 't')
    
    # Store environment status
    result["environment"] = {
        "KEEP_ALIVE_ENABLED": os.environ.get('KEEP_ALIVE_ENABLED', 'Not set'),
        "RENDER": os.environ.get('RENDER', 'Not set'),
        "FORCE_KEEP_ALIVE": os.environ.get('FORCE_KEEP_ALIVE', 'Not set'),
        "RENDER_EXTERNAL_URL": os.environ.get('RENDER_EXTERNAL_URL', 'Not set'),
        "APP_URL": os.environ.get('APP_URL', 'Not set'),
        "KEEP_ALIVE_INTERVAL_MINUTES": os.environ.get('KEEP_ALIVE_INTERVAL_MINUTES', '10'),
        "KEEP_ALIVE_ENDPOINT": os.environ.get('KEEP_ALIVE_ENDPOINT', '/health')
    }
    
    if not (keep_alive_enabled or render_enabled or force_enabled):
        message = "Keep-alive service not enabled (set KEEP_ALIVE_ENABLED=true to enable)"
        logger.info(message)
        result["diagnostics"].append(message)
        return result
    
    # Service is enabled
    result["enabled"] = True
    logger.info("Keep-alive service is enabled")
    result["diagnostics"].append("Keep-alive service is enabled via environment variables")
    
    # 2. Import keep_alive module
    try:
        import keep_alive
        result["diagnostics"].append("Successfully imported keep_alive module")
    except ImportError as e:
        error_msg = f"Could not import keep_alive module: {str(e)}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
        result["diagnostics"].append("Fix: Make sure keep_alive.py is in your application directory")
        return result
        
    # 3. Get configuration from environment variables
    try:
        interval_mins = int(os.environ.get('KEEP_ALIVE_INTERVAL_MINUTES', 10))
        result["interval_minutes"] = interval_mins
        endpoint = os.environ.get('KEEP_ALIVE_ENDPOINT', '/health')
        result["endpoint"] = endpoint
        
        # Test immediate mode flag
        test_endpoint = os.environ.get('KEEP_ALIVE_TEST_ENDPOINT', '').lower() in ('true', 'yes', '1', 't')
        result["test_endpoint"] = test_endpoint
        
        logger.info(f"Keep-alive configuration: interval={interval_mins}min, endpoint={endpoint}")
        result["diagnostics"].append(f"Configured interval: {interval_mins} minutes, endpoint: {endpoint}")
    except Exception as e:
        warning_msg = f"Error parsing keep-alive configuration: {str(e)}"
        logger.warning(warning_msg)
        result["warnings"].append(warning_msg)
        # Use defaults if there's an error
        interval_mins = 10
        endpoint = '/health'
        result["interval_minutes"] = interval_mins
        result["endpoint"] = endpoint
        
    # 4. Determine application URL using multiple approaches
    app_url = None
    url_source = None
    
    # 4.1 Check environment variables (most reliable for Render)
    if os.environ.get('RENDER_EXTERNAL_URL'):
        app_url = os.environ.get('RENDER_EXTERNAL_URL')
        url_source = "RENDER_EXTERNAL_URL"
        logger.info(f"Using RENDER_EXTERNAL_URL: {app_url}")
        
    # 4.2 Check for manually specified URL
    elif os.environ.get('APP_URL'):
        app_url = os.environ.get('APP_URL')
        url_source = "APP_URL"
        logger.info(f"Using APP_URL from environment: {app_url}")
        
    # 4.3 Try to construct from host/port environment variables
    else:
        # Get host and port from environment or defaults
        host = os.environ.get('HOST', 'localhost')
        port = int(os.environ.get('PORT', 5000))
        protocol = 'https' if render_enabled else 'http'
        
        # Handle special case for localhost
        if host in ('localhost', '0.0.0.0', '127.0.0.1'):
            # For local development
            if render_enabled:
                # On Render, try to get the service name
                service_name = os.environ.get('RENDER_SERVICE_NAME')
                if service_name:
                    app_url = f"https://{service_name}.onrender.com"
                    url_source = "RENDER_SERVICE_NAME"
                    logger.info(f"Constructed Render URL from service name: {app_url}")
                else:
                    # Last resort for Render - get instance URL from request
                    # This won't work at app startup, only in blueprint init
                    if app and hasattr(app, 'config'):
                        # Try to get the server name from app config
                        server_name = app.config.get('SERVER_NAME') 
                        if server_name:
                            app_url = f"https://{server_name}"
                            url_source = "Flask SERVER_NAME"
                            logger.info(f"Using Flask server name: {app_url}")
                        else:
                            # Fallback to best guess for Render
                            app_url = f"https://webhook-data-viewer.onrender.com"
                            url_source = "Fallback Render domain"
                            logger.warning(f"Using fallback Render domain: {app_url}")
                    else:
                        # Complete fallback
                        app_url = "https://webhook-data-viewer.onrender.com"
                        url_source = "Hard-coded fallback"
                        logger.warning(f"Using hard-coded fallback URL: {app_url}")
            else:
                # Local development
                app_url = f"{protocol}://{host}"
                if port != 80 and port != 443:
                    app_url += f":{port}"
                url_source = "Local development"
                logger.info(f"Using local development URL: {app_url}")
        else:
            # Using provided host
            app_url = f"{protocol}://{host}"
            if port != 80 and port != 443:
                app_url += f":{port}"
            url_source = "HOST/PORT variables"
            logger.info(f"Constructed URL from HOST/PORT: {app_url}")
    
    # Store URL information
    result["app_url"] = app_url
    result["url_source"] = url_source
    result["diagnostics"].append(f"Application URL: {app_url} (source: {url_source})")
    
    # 5. Initialize and start the keep-alive service
    if app_url:
        try:
            # Start the service with detailed status reporting
            service_result = keep_alive.init_keep_alive(
                app_url=app_url,
                interval_minutes=interval_mins,
                endpoint=endpoint,
                enabled=True,
                test_endpoint=test_endpoint
            )
            
            # Update our result with the service initialization details
            result.update(service_result)
            
            if service_result.get("success"):
                logger.info(f"Keep-alive service initialized successfully with URL {app_url}")
                result["success"] = True
            else:
                error_msg = f"Failed to start keep-alive service with URL {app_url}"
                if service_result.get("errors"):
                    error_msg += f": {service_result['errors'][0]}"
                logger.error(error_msg)
                result["errors"].append(error_msg)
                
            # Include any warnings from the service initialization
            for warning in service_result.get("warnings", []):
                result["warnings"].append(warning)
                
            # Include any diagnostics from the service initialization
            for diagnostic in service_result.get("diagnostics", []):
                result["diagnostics"].append(diagnostic)
                
            return result
            
        except Exception as e:
            error_msg = f"Exception during keep-alive service initialization: {str(e)}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            import traceback
            tb = traceback.format_exc()
            logger.error(tb)
            result["diagnostics"].append(tb)
            return result
    else:
        error_msg = "Could not determine application URL for keep-alive service"
        logger.error(error_msg)
        result["errors"].append(error_msg)
        result["diagnostics"].append("Fix: Set APP_URL environment variable explicitly")
        return result

# Initialize the keep-alive service when the application starts
# Create a function to initialize services with app context
def initialize_services_with_app(app):
    """Initialize services that depend on the application context"""
    try:
        logger.info("Starting service initialization within app context")
        
        # Create a dictionary to track the initialization process
        init_status = {
            "start_time": datetime.datetime.now().isoformat(),
            "steps_completed": [],
            "errors": [],
            "warnings": []
        }
        
        # STEP 1: Check what environment variables are set
        env_vars = {
            "KEEP_ALIVE_ENABLED": os.environ.get('KEEP_ALIVE_ENABLED', 'Not set'),
            "FORCE_KEEP_ALIVE": os.environ.get('FORCE_KEEP_ALIVE', 'Not set'),
            "APP_URL": os.environ.get('APP_URL', 'Not set'),
            "RENDER_EXTERNAL_URL": os.environ.get('RENDER_EXTERNAL_URL', 'Not set'),
            "RENDER": os.environ.get('RENDER', 'Not set'),
            "HOST": os.environ.get('HOST', 'Not set'),
            "PORT": os.environ.get('PORT', 'Not set')
        }
        
        logger.info(f"Environment variables: {env_vars}")
        init_status["environment"] = env_vars
        init_status["steps_completed"].append("environment_check")
        
        # STEP 2: Create app context for any operations that need it
        with app.app_context():
            init_status["steps_completed"].append("app_context_created")
            
            # STEP 3: Import the keep_alive module
            try:
                import keep_alive
                init_status["steps_completed"].append("keep_alive_imported")
                
                # STEP 4: Check if the service is already running
                if keep_alive.keep_alive_service.running:
                    logger.info("Keep-alive service is already running - skipping initialization")
                    init_status["steps_completed"].append("service_already_running")
                    init_status["already_running"] = True
                else:
                    logger.info("Initializing keep-alive service from app context")
                    init_status["steps_completed"].append("service_initialization_started")
                    
                    # STEP 5: Force environment variables if needed for testing
                    if os.environ.get('FORCE_KEEP_ALIVE') == 'true':
                        logger.info("FORCE_KEEP_ALIVE is true - ensuring service is enabled")
                        os.environ['KEEP_ALIVE_ENABLED'] = 'true'
                        init_status["steps_completed"].append("forced_service_enable")
                    
                    # STEP 6: Initialize the service
                    try:
                        result = init_keep_alive_service(app=app)
                        init_status["keep_alive_result"] = result
                        init_status["steps_completed"].append("service_initialization_completed")
                        
                        # Log detailed results
                        if result.get("success"):
                            logger.info(f"Keep-alive service successfully initialized with {result.get('app_url')}")
                            logger.info(f"Ping interval: {result.get('interval_minutes')} minutes, endpoint: {result.get('endpoint', '/health')}")
                            init_status["success"] = True
                        else:
                            if result.get("errors"):
                                errors = result.get("errors", [])
                                logger.error(f"Keep-alive initialization failed with errors: {', '.join(errors)}")
                                init_status["errors"].extend(errors)
                            if result.get("warnings"):
                                warnings = result.get("warnings", [])
                                logger.warning(f"Keep-alive initialization warnings: {', '.join(warnings)}")
                                init_status["warnings"].extend(warnings)
                            
                        # STEP 7: Verify the service is actually running
                        try:
                            status = keep_alive.get_keep_alive_status()
                            init_status["service_status"] = status
                            init_status["steps_completed"].append("service_status_fetched")
                            
                            if status.get("running"):
                                logger.info("Keep-alive service is confirmed to be running")
                                init_status["success"] = True
                            else:
                                logger.warning("Keep-alive service is not running after initialization")
                                init_status["warnings"].append("Service not running after initialization")
                        except Exception as status_e:
                            logger.error(f"Error fetching service status: {str(status_e)}")
                            init_status["errors"].append(f"Error fetching service status: {str(status_e)}")
                        
                    except Exception as init_e:
                        logger.error(f"Error during keep-alive initialization: {str(init_e)}")
                        logger.error(traceback.format_exc())
                        init_status["errors"].append(f"Error during service initialization: {str(init_e)}")
                
            except ImportError as ie:
                error_msg = f"Could not import keep_alive module: {str(ie)}"
                logger.warning(error_msg)
                logger.warning("Make sure keep_alive.py is in your application directory")
                init_status["errors"].append(error_msg)
                
            except Exception as e:
                error_msg = f"Unexpected error initializing keep-alive service: {str(e)}"
                logger.error(error_msg)
                logger.error(traceback.format_exc())
                init_status["errors"].append(error_msg)
            
        # STEP 8: Finalize status
        init_status["end_time"] = datetime.datetime.now().isoformat()
        init_status["duration_ms"] = (datetime.datetime.fromisoformat(init_status["end_time"]) - 
                                    datetime.datetime.fromisoformat(init_status["start_time"])).total_seconds() * 1000
        
        logger.info(f"Completed service initialization. Steps: {init_status['steps_completed']}")
        
        # If we have the app object, store the status on it
        if app:
            app.keep_alive_init_status = init_status
        
        # Return the status so it can be used by the caller
        return init_status
        
    except Exception as e:
        logger.error(f"Critical error in service initialization: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "critical_error": str(e),
            "traceback": traceback.format_exc()
        }

# Use a blueprint event for initialization
# This runs when the application starts without needing before_first_request
# This approach works in Flask 2.3+
init_bp = Blueprint('init_bp', __name__)

@init_bp.record_once
def on_init(state):
    """Run initialization when the blueprint is registered"""
    app = state.app
    
    # Add a initialization message to the logs
    logger.info("Blueprint on_init called - preparing to initialize keep-alive service")
    
    # Mark that this was run to help with debugging
    app.keep_alive_init_started = True
    
    # Wait a short time to ensure the Flask app is fully initialized
    def delayed_init():
        try:
            # Mark that we're in the delayed init
            logger.info("Keep-alive delayed initialization started")
            
            # Wait for the Flask app to fully initialize - using less time to get started more quickly
            time.sleep(3)
            
            # Force environment variables for testing
            if not os.environ.get('KEEP_ALIVE_ENABLED'):
                logger.info("Forcing KEEP_ALIVE_ENABLED=true for testing")
                os.environ['KEEP_ALIVE_ENABLED'] = 'true'
            
            if not os.environ.get('FORCE_KEEP_ALIVE'):
                logger.info("Forcing FORCE_KEEP_ALIVE=true for testing")
                os.environ['FORCE_KEEP_ALIVE'] = 'true'
                
            # Make sure we have a test URL
            if not os.environ.get('APP_URL') and not os.environ.get('RENDER_EXTERNAL_URL'):
                hostname = os.environ.get('HOST', 'localhost')
                port = os.environ.get('PORT', '5000')
                test_url = f"http://{hostname}:{port}"
                logger.info(f"Setting APP_URL={test_url} for testing")
                os.environ['APP_URL'] = test_url
            
            # Then initialize services with the app context
            result = initialize_services_with_app(app)
            logger.info(f"Delayed initialization completed with result: {result}")
            
            # Mark that keep-alive was initialized
            app.keep_alive_init_completed = True
            
        except Exception as e:
            logger.error(f"Error in delayed initialization: {str(e)}")
            logger.error(traceback.format_exc())
    
    # Initialize services in a background thread to not block startup
    init_thread = threading.Thread(target=delayed_init, daemon=True)
    init_thread.start()
    logger.info("Keep-alive service initialization scheduled in background thread")

# Register the initialization blueprint
app.register_blueprint(init_bp)

if __name__ == '__main__':
    # Try to initialize keep-alive service (will be retried if failed)
    init_keep_alive_service()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
