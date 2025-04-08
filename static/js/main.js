// Main JavaScript file for the Webhook Data Viewer

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Add animation to alerts
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        alert.addEventListener('click', function() {
            this.style.opacity = '0';
            setTimeout(() => {
                this.style.display = 'none';
            }, 500);
        });
    });

    // Add timestamp formatting
    const timestamps = document.querySelectorAll('.timestamp');
    timestamps.forEach(element => {
        const timestamp = element.textContent.trim();
        try {
            const date = new Date(timestamp);
            if (!isNaN(date)) {
                element.textContent = date.toLocaleString();
                element.title = timestamp;
            }
        } catch (e) {
            // Keep original format if parsing fails
        }
    });
});

// Function to copy text to clipboard
function copyToClipboard(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
    
    // Show copied notification
    const notification = document.createElement('div');
    notification.textContent = 'Copied!';
    notification.style.position = 'fixed';
    notification.style.bottom = '20px';
    notification.style.right = '20px';
    notification.style.padding = '10px 20px';
    notification.style.backgroundColor = '#212529';
    notification.style.color = 'white';
    notification.style.borderRadius = '4px';
    notification.style.zIndex = '1000';
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transition = 'opacity 0.5s';
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 500);
    }, 2000);
}
