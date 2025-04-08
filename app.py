import os
import json
import datetime
import logging
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
    
    # Extract sender from data or use IP address
    sender = data.get('sender', request.remote_addr)
    sender = secure_filename(sender)
    
    # Create directory for this sender if needed
    sender_dir = os.path.join(DATA_DIR, sender)
    if not os.path.exists(sender_dir):
        os.makedirs(sender_dir)
    
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
    
    # Automatically backup to Dropbox if enabled
    backup_status = None
    if ENABLE_AUTO_BACKUP and DROPBOX_SYNC_AVAILABLE:
        try:
            logger.info(f"Auto-backing up submission {submission_id} to Dropbox")
            backup_success = dropbox_sync.backup_specific_file(sender, submission_id)
            backup_status = "success" if backup_success else "failed"
            if backup_success:
                logger.info(f"Successfully backed up submission {submission_id} to Dropbox")
            else:
                logger.warning(f"Failed to back up submission {submission_id} to Dropbox")
        except Exception as e:
            backup_status = "error"
            logger.error(f"Error backing up to Dropbox: {str(e)}")
    
    response = {
        "success": True,
        "id": submission_id,
        "url": url_for('view_submission', sender=sender, submission_id=submission_id, _external=True)
    }
    
    # Add backup status to response if backup was attempted
    if backup_status:
        response["backup_status"] = backup_status
    
    return jsonify(response)

@app.route('/api/data')
def list_senders_api():
    """API endpoint to list all senders"""
    senders = get_sender_dirs()
    return jsonify({"senders": senders})

@app.route('/api/data/<sender>')
def list_submissions_api(sender):
    """API endpoint to list all submissions for a sender"""
    sender = secure_filename(sender)
    submissions = get_sender_submissions(sender)
    return jsonify({"sender": sender, "submissions": submissions})

@app.route('/api/data/<sender>/<submission_id>')
def get_submission_api(sender, submission_id):
    """API endpoint to get a specific submission"""
    sender = secure_filename(sender)
    data = get_submission_data(sender, submission_id)
    if data is None:
        return jsonify({"error": "Submission not found"}), 404
    return jsonify(data)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
