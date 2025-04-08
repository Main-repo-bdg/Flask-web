# Webhook Data Viewer

A Flask web application that acts as a webhook receiver, storing and displaying JSON data in a human-readable format.

## Features

- **Webhook Endpoint**: Receive and store JSON data
- **Data Organization**: Organize submissions by sender with timestamps and titles
- **Human-Friendly Display**: View JSON data in a formatted, readable way
- **Tab Navigation**: Switch between different views and data representations
- **Simple File System**: Browse data organized like a file system

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
   - **Environment Variables**: None required for basic functionality

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

## API Documentation

The following API endpoints are available:

- `POST /api/webhook` - Submit new data
- `GET /api/data` - List all senders
- `GET /api/data/<sender>` - List all submissions for a sender
- `GET /api/data/<sender>/<submission_id>` - Get a specific submission

## License

This project is available as open source under the terms of the MIT License.
