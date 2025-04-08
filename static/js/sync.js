/**
 * Dropbox Synchronization JavaScript
 * Provides interactive sync functionality for the Webhook Data Viewer
 */

// Main sync controller
const DropboxSync = {
    // Configuration
    endpoints: {
        sync: '/api/dropbox/sync',
        status: '/api/dropbox/sync/status'
    },
    
    // State tracking
    isSyncing: false,
    lastSyncTime: null,
    
    // Status indicators
    indicators: {
        inProgress: '<i class="fas fa-sync fa-spin text-primary"></i>',
        success: '<i class="fas fa-check-circle text-success"></i>',
        error: '<i class="fas fa-exclamation-circle text-danger"></i>',
        warning: '<i class="fas fa-exclamation-triangle text-warning"></i>'
    },
    
    // Initialize the sync functionality
    init: function() {
        // Set up the sync form
        this.setupSyncForm();
        
        // Set up quick sync buttons
        this.setupQuickSyncButtons();
        
        // Update status initially if available
        this.updateSyncStatus();
        
        console.log('Dropbox sync functionality initialized');
    },
    
    // Set up the main sync form
    setupSyncForm: function() {
        const syncForm = document.getElementById('syncForm');
        if (!syncForm) return;
        
        syncForm.addEventListener('submit', (e) => {
            e.preventDefault();
            
            // Get form values
            const direction = document.getElementById('syncDirection').value;
            const forceSync = document.getElementById('forceSync').checked;
            const verifySync = document.getElementById('verifySync').checked;
            
            // Start the sync
            this.startSync(direction, forceSync, verifySync);
        });
    },
    
    // Set up quick sync buttons
    setupQuickSyncButtons: function() {
        const quickSyncButtons = document.querySelectorAll('.quick-sync-btn');
        if (!quickSyncButtons.length) return;
        
        quickSyncButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.preventDefault();
                
                const direction = button.getAttribute('data-direction');
                const verify = true; // Default to verify
                
                // Start quick sync with minimal UI
                this.startSync(direction, false, verify, true);
                
                // Change the button's appearance
                const originalText = button.innerHTML;
                button.innerHTML = '<i class="fas fa-sync fa-spin"></i> Syncing...';
                button.disabled = true;
                
                // Restore button after a timeout
                setTimeout(() => {
                    button.innerHTML = originalText;
                    button.disabled = false;
                }, 3000);
            });
        });
    },
    
    // Start a sync operation
    startSync: function(direction, force, verify, isQuick = false) {
        if (this.isSyncing) {
            showToast('A sync is already in progress', 'warning');
            return;
        }
        
        this.isSyncing = true;
        
        // Update UI to show we're syncing
        const statusElement = document.getElementById('syncStatus');
        if (statusElement) {
            statusElement.style.display = 'block';
            statusElement.innerHTML = this._buildSyncProgressUI(direction, force, verify);
        }
        
        // Construct the URL with parameters
        let url = `${this.endpoints.sync}?direction=${direction}`;
        if (force) url += '&force=true';
        if (verify) url += '&verify=true';
        
        // Make the AJAX request
        fetch(url)
            .then(response => response.json())
            .then(data => {
                this._handleSyncResponse(data, direction, isQuick);
            })
            .catch(error => {
                this._handleSyncError(error, isQuick);
            });
    },
    
    // Handle the sync response
    _handleSyncResponse: function(data, direction, isQuick) {
        if (data.success) {
            // Update UI with success
            this._updateSyncStatusUI({
                status: 'success',
                message: `Sync ${this._getDirectionText(direction)} started successfully`
            });
            
            // Show toast notification
            showToast('Sync started successfully', 'success');
            
            // Poll for status updates
            this._pollSyncStatus();
        } else {
            // Show error in UI
            this._updateSyncStatusUI({
                status: 'error',
                message: data.error || 'Failed to start sync'
            });
            
            // Show toast notification
            showToast(data.error || 'Failed to start sync', 'danger');
            
            this.isSyncing = false;
        }
    },
    
    // Handle sync error
    _handleSyncError: function(error, isQuick) {
        console.error('Sync error:', error);
        
        // Update UI with error
        this._updateSyncStatusUI({
            status: 'error',
            message: error.message || 'Error starting sync'
        });
        
        // Show toast notification
        showToast('Error starting sync: ' + (error.message || 'Unknown error'), 'danger');
        
        this.isSyncing = false;
    },
    
    // Poll for sync status updates
    _pollSyncStatus: function() {
        let pollCount = 0;
        const maxPolls = 10; // Maximum number of polls
        
        const poll = () => {
            if (pollCount > maxPolls || !this.isSyncing) {
                return;
            }
            
            pollCount++;
            
            // Check the sync status
            fetch(this.endpoints.status)
                .then(response => response.json())
                .then(data => {
                    // Update UI with latest status
                    this._updateSyncProgressUI(data);
                    
                    // Check if sync is still running
                    if (data.in_progress) {
                        // Continue polling
                        setTimeout(poll, 2000);
                    } else {
                        // Sync complete
                        this._syncComplete(data);
                    }
                })
                .catch(error => {
                    console.error('Error polling sync status:', error);
                    // Retry a few times on error
                    if (pollCount < maxPolls) {
                        setTimeout(poll, 3000);
                    } else {
                        this._syncComplete({ error: 'Failed to get sync status' });
                    }
                });
        };
        
        // Start polling after a short delay
        setTimeout(poll, 1000);
    },
    
    // Handle sync completion
    _syncComplete: function(statusData) {
        this.isSyncing = false;
        this.lastSyncTime = new Date();
        
        // Update the UI
        const hasErrors = statusData.last_errors && statusData.last_errors.length > 0;
        
        this._updateSyncStatusUI({
            status: hasErrors ? 'warning' : 'success',
            message: hasErrors ? 
                'Sync completed with errors' : 
                'Sync completed successfully',
            details: statusData
        });
        
        // Show toast notification
        showToast(
            hasErrors ? 'Sync completed with errors' : 'Sync completed successfully',
            hasErrors ? 'warning' : 'success'
        );
        
        // Update the overall sync stats
        this.updateSyncStatus();
    },
    
    // Update the sync status UI
    updateSyncStatus: function() {
        fetch(this.endpoints.status)
            .then(response => response.json())
            .then(data => {
                // Update sync stats if they exist on the page
                this._updateSyncStatsUI(data);
            })
            .catch(error => {
                console.error('Error fetching sync status:', error);
            });
    },
    
    // Update the sync progress UI
    _updateSyncProgressUI: function(statusData) {
        const statusElement = document.getElementById('syncStatus');
        if (!statusElement) return;
        
        // If we have files_synced, show progress
        if (statusData.files_synced) {
            const progressElement = document.getElementById('syncProgressBar');
            if (progressElement) {
                // Update progress
                const percent = Math.min(
                    (statusData.files_synced / Math.max(statusData.total_files || 10, 10)) * 100,
                    99.5 // Don't show 100% until we're actually done
                );
                progressElement.style.width = `${percent}%`;
                progressElement.setAttribute('aria-valuenow', percent);
            }
        }
        
        // Update message if available
        if (statusData.current_operation) {
            const messageElement = document.getElementById('syncProgressMessage');
            if (messageElement) {
                messageElement.textContent = statusData.current_operation;
            }
        }
    },
    
    // Update the sync status UI with success/error
    _updateSyncStatusUI: function(statusInfo) {
        const statusElement = document.getElementById('syncStatus');
        if (!statusElement) return;
        
        let icon;
        let statusClass;
        
        // Set icon and class based on status
        switch (statusInfo.status) {
            case 'success':
                icon = this.indicators.success;
                statusClass = 'success';
                break;
            case 'error':
                icon = this.indicators.error;
                statusClass = 'danger';
                break;
            case 'warning':
                icon = this.indicators.warning;
                statusClass = 'warning';
                break;
            default:
                icon = this.indicators.inProgress;
                statusClass = 'primary';
        }
        
        // Create the status message
        let html = `
            <div class="alert alert-${statusClass} d-flex align-items-center">
                <div class="me-3 fs-4">${icon}</div>
                <div>
                    <h5 class="alert-heading mb-1">${statusInfo.message}</h5>
        `;
        
        // Add details if available
        if (statusInfo.details) {
            html += '<ul class="mb-0 small">';
            
            if (statusInfo.details.files_synced) {
                html += `<li>Files synced: ${statusInfo.details.files_synced}</li>`;
            }
            
            if (statusInfo.details.successful_syncs) {
                html += `<li>Successful syncs: ${statusInfo.details.successful_syncs}</li>`;
            }
            
            if (statusInfo.details.last_errors && statusInfo.details.last_errors.length > 0) {
                html += `<li>Errors: ${statusInfo.details.last_errors.length}</li>`;
                // Show the first error
                html += `<li class="text-danger">${statusInfo.details.last_errors[0]}</li>`;
            }
            
            html += '</ul>';
        }
        
        html += `
                </div>
            </div>
        `;
        
        statusElement.innerHTML = html;
    },
    
    // Update the overall sync stats UI
    _updateSyncStatsUI: function(statusData) {
        // Update the last sync time if available
        const lastSyncElement = document.getElementById('lastSyncTime');
        if (lastSyncElement && statusData.last_sync) {
            const lastSyncDate = new Date(statusData.last_sync);
            lastSyncElement.textContent = lastSyncDate.toLocaleString();
        }
        
        // Update sync counts if available
        const syncCountElement = document.getElementById('totalSyncCount');
        if (syncCountElement && statusData.total_syncs) {
            syncCountElement.textContent = statusData.total_syncs;
        }
        
        // Update file counts if available
        const fileCountElement = document.getElementById('totalFileCount');
        if (fileCountElement && statusData.files_synced) {
            fileCountElement.textContent = statusData.files_synced;
        }
    },
    
    // Build the initial sync progress UI
    _buildSyncProgressUI: function(direction, force, verify) {
        return `
            <div class="card border-primary mb-3">
                <div class="card-header bg-primary text-white d-flex align-items-center">
                    <div class="me-2">${this.indicators.inProgress}</div>
                    <div>Sync in Progress: ${this._getDirectionText(direction)}</div>
                </div>
                <div class="card-body">
                    <p class="mb-1" id="syncProgressMessage">Starting synchronization...</p>
                    <div class="progress mb-3">
                        <div id="syncProgressBar" class="progress-bar progress-bar-striped progress-bar-animated" 
                             role="progressbar" style="width: 10%" aria-valuenow="10" aria-valuemin="0" aria-valuemax="100"></div>
                    </div>
                    <div class="small text-muted">
                        <strong>Mode:</strong> ${force ? 'Force sync' : 'Normal'} | 
                        <strong>Verify:</strong> ${verify ? 'Yes' : 'No'}
                    </div>
                </div>
            </div>
        `;
    },
    
    // Get human-readable direction text
    _getDirectionText: function(direction) {
        switch(direction) {
            case 'to_dropbox':
                return 'Local to Dropbox';
            case 'from_dropbox':
                return 'Dropbox to Local';
            case 'both':
                return 'Two-way Sync';
            default:
                return 'Unknown Direction';
        }
    }
};

// Toast notification function
function showToast(message, type = 'info') {
    // Try to use existing showToast function if available
    if (window.showToast) {
        window.showToast(message, type);
        return;
    }
    
    // Create toast element
    const toast = document.createElement('div');
    toast.className = `toast-notification bg-${type}`;
    toast.innerHTML = `
        <div class="toast-content">
            <i class="fas ${type === 'success' ? 'fa-check-circle' : 
                           type === 'danger' ? 'fa-times-circle' :
                           type === 'warning' ? 'fa-exclamation-triangle' : 
                           'fa-info-circle'} me-2"></i>
            ${message}
        </div>
    `;
    
    // Add toast to document
    document.body.appendChild(toast);
    
    // Remove toast after animation
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// Initialize the sync functionality when the document is ready
document.addEventListener('DOMContentLoaded', function() {
    DropboxSync.init();
});
