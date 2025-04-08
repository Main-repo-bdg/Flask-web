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
    
    // Initialize copy buttons
    initializeCopyButtons();
    
    // Initialize sync controls if present
    initializeSyncControls();
});

// Function to initialize all copy buttons
function initializeCopyButtons() {
    // Find all elements with data-copy-target attribute
    const copyButtons = document.querySelectorAll('[data-copy-target]');
    
    copyButtons.forEach(button => {
        button.addEventListener('click', function() {
            const targetId = this.getAttribute('data-copy-target');
            const targetElement = document.getElementById(targetId);
            
            if (targetElement) {
                // Get text to copy
                let textToCopy;
                
                if (targetElement.tagName === 'PRE' || targetElement.tagName === 'CODE') {
                    textToCopy = targetElement.textContent;
                } else if (targetElement.value !== undefined) {
                    textToCopy = targetElement.value;
                } else {
                    textToCopy = targetElement.textContent;
                }
                
                // Copy the text
                copyToClipboard(textToCopy);
                
                // Update button text/icon temporarily
                const originalHTML = this.innerHTML;
                this.innerHTML = '<i class="fas fa-check me-1"></i>Copied!';
                
                // Reset button after a delay
                setTimeout(() => {
                    this.innerHTML = originalHTML;
                }, 2000);
            }
        });
    });
    
    // Find all code blocks that should have copy buttons but don't yet
    document.querySelectorAll('pre.json-code, pre.code-block').forEach(codeBlock => {
        // Skip if it already has a copy button as a direct child or nearby
        if (codeBlock.querySelector('.copy-btn') || 
            codeBlock.parentElement.querySelector(`.copy-btn[data-copy-target="${codeBlock.id}"]`)) {
            return;
        }
        
        // If the code block doesn't have an ID, create one
        if (!codeBlock.id) {
            codeBlock.id = 'code-block-' + Math.random().toString(36).substr(2, 9);
        }
        
        // Create the copy button
        const copyBtn = document.createElement('button');
        copyBtn.className = 'btn btn-sm btn-outline-secondary copy-btn position-absolute end-0 top-0 m-2';
        copyBtn.innerHTML = '<i class="fas fa-copy me-1"></i>Copy';
        copyBtn.setAttribute('data-copy-target', codeBlock.id);
        copyBtn.setAttribute('type', 'button');
        
        // Check if codeBlock is already in a relative position
        const parent = codeBlock.parentElement;
        if (getComputedStyle(parent).position === 'static') {
            parent.style.position = 'relative';
        }
        
        // Add the button
        parent.appendChild(copyBtn);
        
        // Ensure the button is properly positioned
        if (getComputedStyle(codeBlock).position === 'static') {
            codeBlock.style.paddingRight = '70px'; // Make room for the button
        }
    });
    
    // Add copy buttons to API endpoint paths
    document.querySelectorAll('.api-path').forEach(pathElement => {
        // Skip if it already has a copy button
        if (pathElement.querySelector('.copy-btn')) {
            return;
        }
        
        // If the element doesn't have an ID, create one
        if (!pathElement.id) {
            pathElement.id = 'api-path-' + Math.random().toString(36).substr(2, 9);
        }
        
        // Extract the endpoint path
        let endpointText = pathElement.textContent.trim();
        if (endpointText.includes('Endpoint:')) {
            endpointText = endpointText.split('Endpoint:')[1].trim();
        }
        
        // Create a data attribute with just the endpoint
        pathElement.setAttribute('data-endpoint', endpointText);
        
        // Create the copy button
        const copyBtn = document.createElement('button');
        copyBtn.className = 'btn btn-sm btn-outline-secondary copy-btn float-end';
        copyBtn.innerHTML = '<i class="fas fa-copy me-1"></i>Copy';
        copyBtn.setAttribute('type', 'button');
        
        // Add click handler directly
        copyBtn.addEventListener('click', function() {
            const endpoint = pathElement.getAttribute('data-endpoint');
            copyToClipboard(endpoint);
            
            // Update button text/icon temporarily
            const originalHTML = this.innerHTML;
            this.innerHTML = '<i class="fas fa-check me-1"></i>Copied!';
            
            // Reset button after a delay
            setTimeout(() => {
                this.innerHTML = originalHTML;
            }, 2000);
        });
        
        // Add the button
        pathElement.appendChild(copyBtn);
    });
}

// Function to initialize Dropbox sync controls
function initializeSyncControls() {
    // Find the sync form if present
    const syncForm = document.getElementById('syncForm');
    if (!syncForm) return;
    
    syncForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        // Get form values
        const direction = document.getElementById('syncDirection').value;
        const force = document.getElementById('forceSync').checked;
        const verify = document.getElementById('verifySync').checked;
        
        // Update UI to show syncing state
        const submitBtn = syncForm.querySelector('button[type="submit"]');
        const originalText = submitBtn.innerHTML;
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Syncing...';
        
        // Show sync status
        const statusElement = document.getElementById('syncStatus');
        if (statusElement) {
            statusElement.innerHTML = `
                <div class="alert alert-info">
                    <i class="fas fa-sync fa-spin me-2"></i>
                    <strong>Sync in progress...</strong> This may take a moment.
                </div>
            `;
            statusElement.style.display = 'block';
        }
        
        // Construct the request URL
        let url = '/api/dropbox/sync?format=json';
        url += `&direction=${direction}`;
        url += `&force=${force}`;
        url += `&verify=${verify}`;
        
        // Make the request
        fetch(url, {
            method: 'POST',
            headers: {
                'Accept': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            // Update status element
            if (statusElement) {
                if (data.success) {
                    statusElement.innerHTML = `
                        <div class="alert alert-success">
                            <i class="fas fa-check-circle me-2"></i>
                            <strong>Sync started successfully!</strong>
                            <p class="mb-0 mt-2">The sync job is running in the background.</p>
                            <a href="/api/dropbox/sync/status?format=html" class="btn btn-sm btn-outline-success mt-2">
                                <i class="fas fa-chart-line me-1"></i>View Sync Status
                            </a>
                        </div>
                    `;
                } else {
                    statusElement.innerHTML = `
                        <div class="alert alert-danger">
                            <i class="fas fa-exclamation-circle me-2"></i>
                            <strong>Sync failed to start!</strong>
                            <p class="mb-0 mt-2">${data.error || 'Unknown error'}</p>
                        </div>
                    `;
                }
            }
            
            // Re-enable the button
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        })
        .catch(error => {
            console.error('Error starting sync:', error);
            
            // Update status
            if (statusElement) {
                statusElement.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="fas fa-exclamation-circle me-2"></i>
                        <strong>Error!</strong> Could not connect to the server.
                    </div>
                `;
            }
            
            // Re-enable the button
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        });
    });
    
    // Initialize quick sync buttons
    document.querySelectorAll('.quick-sync-btn').forEach(button => {
        button.addEventListener('click', function() {
            const direction = this.getAttribute('data-direction') || 'both';
            const force = this.getAttribute('data-force') === 'true';
            
            // Update button state
            const originalHTML = this.innerHTML;
            this.disabled = true;
            this.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Syncing...';
            
            // Construct the request URL
            let url = '/api/dropbox/sync?format=json';
            url += `&direction=${direction}`;
            url += `&force=${force}`;
            
            // Make the request
            fetch(url, {
                method: 'POST',
                headers: {
                    'Accept': 'application/json'
                }
            })
            .then(response => response.json())
            .then(data => {
                // Update button
                if (data.success) {
                    this.innerHTML = '<i class="fas fa-check me-1"></i>Started';
                    
                    // Show success toast
                    showToast('Sync job started successfully!', 'success');
                    
                    // Reset button after delay
                    setTimeout(() => {
                        this.disabled = false;
                        this.innerHTML = originalHTML;
                    }, 3000);
                } else {
                    this.innerHTML = '<i class="fas fa-exclamation-triangle me-1"></i>Failed';
                    
                    // Show error toast
                    showToast('Failed to start sync: ' + (data.error || 'Unknown error'), 'danger');
                    
                    // Reset button after delay
                    setTimeout(() => {
                        this.disabled = false;
                        this.innerHTML = originalHTML;
                    }, 3000);
                }
            })
            .catch(error => {
                console.error('Error starting sync:', error);
                
                // Update button
                this.innerHTML = '<i class="fas fa-exclamation-triangle me-1"></i>Error';
                
                // Show error toast
                showToast('Connection error. Please try again.', 'danger');
                
                // Reset button after delay
                setTimeout(() => {
                    this.disabled = false;
                    this.innerHTML = originalHTML;
                }, 3000);
            });
        });
    });
}

// Function to copy text to clipboard
function copyToClipboard(text) {
    // Try to use the modern clipboard API first
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text)
            .then(() => {
                showToast('Copied to clipboard!', 'success');
            })
            .catch(err => {
                console.error('Could not copy text with Clipboard API:', err);
                fallbackCopyToClipboard(text);
            });
    } else {
        fallbackCopyToClipboard(text);
    }
}

// Fallback method for older browsers
function fallbackCopyToClipboard(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';  // Prevent scrolling to bottom
    document.body.appendChild(textarea);
    textarea.select();
    
    try {
        const successful = document.execCommand('copy');
        if (successful) {
            showToast('Copied to clipboard!', 'success');
        } else {
            showToast('Failed to copy text', 'danger');
        }
    } catch (err) {
        console.error('Fallback: Unable to copy', err);
        showToast('Unable to copy text', 'danger');
    }
    
    document.body.removeChild(textarea);
}

// Show toast notification
function showToast(message, type = 'info') {
    // Check if we already have a toast container
    let toastContainer = document.getElementById('toast-container');
    
    if (!toastContainer) {
        // Create toast container
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        toastContainer.className = 'position-fixed bottom-0 end-0 p-3';
        toastContainer.style.zIndex = '5000';
        document.body.appendChild(toastContainer);
    }
    
    // Create a unique ID for this toast
    const toastId = 'toast-' + Date.now();
    
    // Get appropriate icon based on type
    let icon = 'info-circle';
    if (type === 'success') icon = 'check-circle';
    if (type === 'danger') icon = 'exclamation-circle';
    if (type === 'warning') icon = 'exclamation-triangle';
    
    // Create toast HTML
    const toastHTML = `
        <div id="${toastId}" class="toast align-items-center text-white bg-${type} border-0" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">
                    <i class="fas fa-${icon} me-2"></i>${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;
    
    // Add toast to container
    toastContainer.insertAdjacentHTML('beforeend', toastHTML);
    
    // Initialize and show the toast using Bootstrap
    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, {
        autohide: true,
        delay: 3000
    });
    toast.show();
    
    // Remove toast from DOM after it's hidden
    toastElement.addEventListener('hidden.bs.toast', function () {
        this.remove();
    });
}
