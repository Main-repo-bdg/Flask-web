# Webhook Data Viewer

A Flask web application that acts as a webhook receiver, storing and displaying JSON data in a human-readable format.

## Features

- **Webhook Endpoint**: Receive and store JSON data
- **Data Organization**: Organize submissions by sender with timestamps and titles
- **Human-Friendly Display**: View JSON data in a formatted, readable way
- **Tab Navigation**: Switch between different views and data representations
- **Simple File System**: Browse data organized like a file system
- **Dropbox Storage**: Uses Dropbox as the primary storage for data
- **Copy Buttons**: Easily copy JSON data, API endpoints, and examples
- **Keep-Alive Service**: Prevents Render free tier instances from shutting down due to inactivity

## Installation

### Local Development

1. Clone this repository
2. Create and activate a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Run the application:
   ```
   python app.py
   ```
5. Visit `http://localhost:5000` in your browser

### Deployment to Render

This application is designed to be deployed to Render's free tier:

1. Fork or push this repository to GitHub
2. Create a new Web Service on Render
3. Connect your GitHub repository
4. Use the following settings:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Environment Variables**:
     - `RENDER=true` - Enables Render-specific features
     - `KEEP_ALIVE_ENABLED=true` - Enables the keep-alive service
     - `KEEP_ALIVE_INTERVAL_MINUTES=10` - Sets ping interval (1-14 minutes)

## Usage

### Sending Data to the Webhook

Send JSON data to the webhook endpoint with a POST request:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "sender": "example-user",
    "title": "Example Submission",
    "data": {
      "key1": "value1",
      "key2": "value2"
    }
  }' \
  https://your-app-url.onrender.com/api/webhook
```

The webhook accepts any valid JSON data. Including a `sender` and `title` field is recommended for better organization.

### Browsing Data

1. Visit the application's home page
2. Browse data by sender
3. View individual submissions in either formatted or raw view
4. Use the tab navigation to switch between different perspectives

### Dropbox Integration

The application uses Dropbox as its primary storage location, with these features:

1. All webhook data is saved to Dropbox first, then synced locally
2. Manual sync controls are available in the Dropbox Sync tab
3. You can specify sync direction (to Dropbox, from Dropbox, or both)
4. Force sync and verification options are available

### Keep-Alive Service

To prevent Render free tier instances from shutting down after 15 minutes of inactivity:

1. The application includes a built-in keep-alive service
2. A background thread sends periodic requests to keep the application active
3. View the status at `/keep-alive/status` 
4. Configure via environment variables:
   - `KEEP_ALIVE_ENABLED=true` - Enable the service
   - `KEEP_ALIVE_INTERVAL_MINUTES=10` - Set ping interval (1-14 minutes)

## API Documentation

The following API endpoints are available:

- `POST /api/webhook` - Submit new data
- `GET /api/data` - List all senders
- `GET /api/data/<sender>` - List all submissions for a sender
- `GET /api/data/<sender>/<submission_id>` - Get a specific submission
- `POST /api/dropbox/sync` - Trigger a manual Dropbox sync
- `GET /api/dropbox/sync/status` - View Dropbox sync status
- `GET /health` - Health check endpoint
- `GET /keep-alive/status` - View keep-alive service status

## License

This project is available as open source under the terms of the MIT License.
