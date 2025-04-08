import os
import json
import datetime
import logging
import threading
from flask import Flask, request, render_template, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Import Dropbox sync module (if available)
try:
    import dropbox_sync
    DROPBOX_SYNC_AVAILABLE = True
except ImportError:
    DROPBOX_SYNC_AVAILABLE = False

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
    """Get a list of all submissions for a sender"""
    sender_dir = os.path.join(DATA_DIR, secure_filename(sender))
    if not os.path.exists(sender_dir):
        return []
    
    submissions = []
    for filename in os.listdir(sender_dir):
        if filename.endswith('.json'):
            file_path = os.path.join(sender_dir, filename)
            with open(file_path, 'r') as f:
                try:
                    metadata = json.load(f)
                    submissions.append({
                        'id': filename.replace('.json', ''),
                        'title': metadata.get('_meta', {}).get('title', 'Untitled'),
                        'timestamp': metadata.get('_meta', {}).get('timestamp', 'Unknown'),
                        'size': os.path.getsize(file_path)
                    })
                except json.JSONDecodeError:
                    # Handle corrupted JSON files
                    submissions.append({
                        'id': filename.replace('.json', ''),
                        'title': 'Corrupted Data',
                        'timestamp': 'Unknown',
                        'size': os.path.getsize(file_path)
                    })
    
    # Sort by timestamp (newest first)
    submissions.sort(key=lambda x: x['timestamp'], reverse=True)
    return submissions

def get_submission_data(sender, submission_id):
    """Get the data for a specific submission"""
    file_path = os.path.join(DATA_DIR, secure_filename(sender), f"{submission_id}.json")
    if not os.path.exists(file_path):
        return None
    
    with open(file_path, 'r') as f:
        try:
            data = json.load(f)
            # Remove metadata from the returned data
            if '_meta' in data:
                data_without_meta = {k: v for k, v in data.items() if k != '_meta'}
                return data_without_meta
            return data
        except json.JSONDecodeError:
            return {"error": "Corrupted data file"}

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
    """Endpoint for receiving webhook data"""
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.json
    
    # Check for debug mode and sync options in the request
    debug_mode = data.get('debug_dropbox', False)
    verify_upload = data.get('verify_upload', True)
    max_retries = int(data.get('max_retries', 3))
    
    # Extract sender from data or use IP address
    sender = data.get('sender', request.remote_addr)
    sender = secure_filename(sender)
    
    # Create directory for this sender if needed
    sender_dir = os.path.join(DATA_DIR, sender)
    if not os.path.exists(sender_dir):
        os.makedirs(sender_dir)
        logger.info(f"Created local directory: {sender_dir}")
    
    # Generate a unique ID for this submission based on timestamp
    submission_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    
    # Add metadata to the stored data
    data_to_store = data.copy()
    data_to_store['_meta'] = {
        'timestamp': datetime.datetime.now().isoformat(),
        'title': data.get('title', f"Submission {submission_id}"),
        'ip': request.remote_addr
    }
    
    # Save the data to a file
    file_path = os.path.join(sender_dir, f"{submission_id}.json")
    with open(file_path, 'w') as f:
        json.dump(data_to_store, f, indent=2)
    
    logger.info(f"Saved submission {submission_id} for sender {sender}")
    
    # Prepare the response
    response = {
        "success": True,
        "id": submission_id,
        "url": url_for('view_submission', sender=sender, submission_id=submission_id, _external=True),
        "file_saved": os.path.exists(file_path)
    }
    
    # Immediately and reliably backup to Dropbox if enabled
    if ENABLE_AUTO_BACKUP and DROPBOX_SYNC_AVAILABLE:
        try:
            logger.info(f"Auto-backing up submission {submission_id} to Dropbox (debug={debug_mode})")
            
            # Use the enhanced backup function with retries and verification
            backup_result = dropbox_sync.backup_specific_file(
                sender=sender, 
                submission_id=submission_id, 
                debug=debug_mode,
                verify_upload=verify_upload,
                max_retries=max_retries
            )
            
            # Add detailed backup status to response
            response["dropbox_backup"] = backup_result
            
            if backup_result['success']:
                logger.info(f"Successfully backed up submission {submission_id} to Dropbox at path: {backup_result['path']}")
                
                # Add verification info to response if available
                if backup_result.get('verified'):
                    response["dropbox_backup"]["verification"] = "passed"
                    logger.info(f"Verification passed for submission {submission_id}")
                
                # If using the sync_worker module, update sync statistics
                try:
                    import sync_worker
                    status = sync_worker.get_sync_status()
                    status["files_synced"] += 1
                    sync_worker.update_sync_status(status)
                except (ImportError, Exception) as e:
                    logger.debug(f"Could not update sync statistics: {str(e)}")
            else:
                logger.warning(f"Failed to back up submission {submission_id} to Dropbox: {backup_result['error']}")
                
                # If max retries were exceeded, suggest manual sync
                if backup_result.get('retries', 0) >= max_retries:
                    response["dropbox_backup"]["suggestion"] = "Try manual sync later via /api/dropbox/sync"
                
            # Log detailed diagnostics if in debug mode
            if debug_mode and 'details' in backup_result:
                logger.info(f"Dropbox backup details: {json.dumps(backup_result['details'])}")
                
        except Exception as e:
            logger.error(f"Error backing up to Dropbox: {str(e)}")
            response["dropbox_backup"] = {
                'success': False,
                'error': str(e),
                'details': {'exception': str(e)}
            }
            
            # Attempt to queue this file for later sync if sync_worker is available
            try:
                import sync_worker
                logger.info(f"Queuing failed upload for later sync: {sender}/{submission_id}")
                # Record the error in sync status
                status = sync_worker.get_sync_status()
                if "pending_sync" not in status:
                    status["pending_sync"] = []
                status["pending_sync"].append({
                    "sender": sender,
                    "submission_id": submission_id,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "error": str(e)
                })
                sync_worker.update_sync_status(status)
                response["dropbox_backup"]["queued_for_retry"] = True
            except ImportError:
                logger.debug("sync_worker not available for retry queuing")
    else:
        # If Dropbox backup is disabled, note this in the response
        if not ENABLE_AUTO_BACKUP:
            response["dropbox_backup"] = {
                "success": False,
                "error": "Auto-backup to Dropbox is disabled",
                "enable_instructions": "Set ENABLE_AUTO_BACKUP=True in .env file"
            }
        elif not DROPBOX_SYNC_AVAILABLE:
            response["dropbox_backup"] = {
                "success": False,
                "error": "Dropbox sync module is not available",
                "fix_instructions": "Install required packages: pip install -r requirements.txt"
            }
    
    # Check if HTML format is requested (rare for webhook but possible)
    best_format = request.accept_mimetypes.best_match(['application/json', 'text/html'])
    if best_format == 'text/html' or request.args.get('format') == 'html':
        return render_template('webhook_result.html', 
                              result=response, 
                              sender=sender,
                              submission_id=submission_id)
    
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
