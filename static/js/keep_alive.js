/**
 * Keep-Alive Service JavaScript
 * For monitoring and controlling the keep-alive service
 */

const KeepAliveMonitor = {
    // Configuration
    refreshInterval: 10000, // 10 seconds
    statusEndpoint: '/keep-alive/status',
    healthEndpoint: '/health',
    
    // State
    isPolling: false,
    lastRefreshTime: null,
    
    // Initialize the monitor
    init: function() {
        console.log('Initializing Keep-Alive monitor...');
        
        // Set up refresh button if present
        const refreshBtn = document.getElementById('refreshStatusBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.refreshStatus();
            });
        }
        
        // Set up manual test button if present
        const testPingBtn = document.getElementById('testPingBtn');
        if (testPingBtn) {
            testPingBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.testHealthEndpoint();
            });
        }
        
        // Set up toggle service button if present
        const toggleServiceBtn = document.getElementById('toggleServiceBtn');
        if (toggleServiceBtn) {
            toggleServiceBtn.addEventListener('click', (e) => {
                e.preventDefault();
                const isRunning = toggleServiceBtn.getAttribute('data-running') === 'true';
                this.toggleService(!isRunning); // Toggle to opposite state
            });
        }
        
        // Start automatic refresh if on the status page
        if (document.getElementById('keepAliveStatus')) {
            this.startPolling();
        }
        
        // Update any timestamps on the page
        this.formatTimestamps();
        
        console.log('Keep-Alive monitor initialized');
    },
    
    // Start polling for status updates
    startPolling: function() {
        if (this.isPolling) return;
        
        this.isPolling = true;
        this.poll();
        
        console.log(`Started polling keep-alive status every ${this.refreshInterval/1000} seconds`);
    },
    
    // Stop polling for status updates
    stopPolling: function() {
        this.isPolling = false;
    },
    
    // Poll for status updates
    poll: function() {
        if (!this.isPolling) return;
        
        this.refreshStatus(false); // Quiet refresh
        
        // Schedule next poll
        setTimeout(() => this.poll(), this.refreshInterval);
    },
    
    // Refresh the status display
    refreshStatus: function(showFeedback = true) {
        // If feedback is enabled, show loading indicator
        if (showFeedback) {
            this.showLoadingIndicator();
        }
        
        // Fetch the current status
        fetch(this.statusEndpoint)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                this.updateStatusUI(data);
                this.lastRefreshTime = new Date();
                
                if (showFeedback) {
                    this.showRefreshSuccess();
                }
            })
            .catch(error => {
                console.error('Error refreshing status:', error);
                
                if (showFeedback) {
                    this.showRefreshError(error);
                }
            });
    },
    
    // Test the health endpoint directly
    testHealthEndpoint: function() {
        const testBtn = document.getElementById('testPingBtn');
        if (testBtn) {
            const originalText = testBtn.innerHTML;
            testBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Testing...';
            testBtn.disabled = true;
            
            fetch(this.healthEndpoint, {
                headers: {
                    'X-Keep-Alive': 'test',
                    'Cache-Control': 'no-cache'
                }
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                testBtn.innerHTML = '<i class="fas fa-check"></i> Test Successful';
                testBtn.classList.remove('btn-primary');
                testBtn.classList.add('btn-success');
                
                // Show success notification
                this.showToast('Health endpoint test successful', 'success');
                
                // Reset button after delay
                setTimeout(() => {
                    testBtn.innerHTML = originalText;
                    testBtn.classList.remove('btn-success');
                    testBtn.classList.add('btn-primary');
                    testBtn.disabled = false;
                }, 3000);
                
                // Update ping count if available (refresh status)
                this.refreshStatus(false);
            })
            .catch(error => {
                testBtn.innerHTML = '<i class="fas fa-times"></i> Test Failed';
                testBtn.classList.remove('btn-primary');
                testBtn.classList.add('btn-danger');
                
                // Show error notification
                this.showToast('Health endpoint test failed: ' + error.message, 'danger');
                
                // Reset button after delay
                setTimeout(() => {
                    testBtn.innerHTML = originalText;
                    testBtn.classList.remove('btn-danger');
                    testBtn.classList.add('btn-primary');
                    testBtn.disabled = false;
                }, 3000);
            });
        }
    },
    
    // Toggle the keep-alive service
    toggleService: function(enable) {
        const toggleBtn = document.getElementById('toggleServiceBtn');
        if (!toggleBtn) return;
        
        const originalText = toggleBtn.innerHTML;
        toggleBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> ' + (enable ? 'Starting...' : 'Stopping...');
        toggleBtn.disabled = true;
        
        // In a real implementation, this would call an API endpoint to toggle the service
        // For now, we'll just simulate success and refresh the status
        setTimeout(() => {
            if (enable) {
                this.showToast('Keep-alive service started', 'success');
            } else {
                this.showToast('Keep-alive service stopped', 'warning');
            }
            
            // Update button text based on new state
            toggleBtn.innerHTML = enable ? 
                '<i class="fas fa-stop-circle"></i> Stop Service' : 
                '<i class="fas fa-play-circle"></i> Start Service';
            toggleBtn.setAttribute('data-running', enable.toString());
            toggleBtn.disabled = false;
            
            // Update status display
            this.refreshStatus(false);
        }, 1000);
    },
    
    // Update the UI with the latest status
    updateStatusUI: function(status) {
        // Update service running status
        this.updateRunningStatus(status.running);
        
        // Update ping count
        const pingCountElement = document.getElementById('pingCount');
        if (pingCountElement) {
            pingCountElement.textContent = status.ping_count || 0;
        }
        
        // Update error count
        const errorCountElement = document.getElementById('errorCount');
        if (errorCountElement) {
            errorCountElement.textContent = status.error_count || 0;
        }
        
        // Update last ping time
        const lastPingElement = document.getElementById('lastPingTime');
        if (lastPingElement && status.last_ping_time) {
            // Convert to local date/time string
            try {
                const pingDate = new Date(status.last_ping_time);
                lastPingElement.textContent = pingDate.toLocaleString();
            } catch (e) {
                lastPingElement.textContent = status.last_ping_time;
            }
        }
        
        // Update last error if exists
        const lastErrorElement = document.getElementById('lastErrorInfo');
        if (lastErrorElement) {
            if (status.stats && status.stats.last_error) {
                lastErrorElement.style.display = 'block';
                
                const lastErrorTimeElement = document.getElementById('lastErrorTime');
                if (lastErrorTimeElement) {
                    try {
                        const errorDate = new Date(status.stats.last_error.time);
                        lastErrorTimeElement.textContent = errorDate.toLocaleString();
                    } catch (e) {
                        lastErrorTimeElement.textContent = status.stats.last_error.time;
                    }
                }
                
                const lastErrorMsgElement = document.getElementById('lastErrorMessage');
                if (lastErrorMsgElement) {
                    lastErrorMsgElement.textContent = status.stats.last_error.message;
                }
            } else {
                lastErrorElement.style.display = 'none';
            }
        }
        
        // Update uptime
        const uptimeElement = document.getElementById('uptime');
        if (uptimeElement) {
            uptimeElement.textContent = status.uptime_formatted || 'Not running';
        }
        
        // Check if we're now running but there are no pings
        if (status.running && status.ping_count === 0) {
            // The service is running but hasn't pinged yet. Show a message.
            this.showToast('Keep-alive service is running but hasn\'t sent its first ping yet', 'info');
        }
    },
    
    // Update the running status display
    updateRunningStatus: function(isRunning) {
        // Update header color
        const statusHeader = document.querySelector('.card-header.status-header');
        if (statusHeader) {
            statusHeader.classList.remove('bg-success', 'bg-danger');
            statusHeader.classList.add(isRunning ? 'bg-success' : 'bg-danger');
            
            // Update icon
            const statusIcon = statusHeader.querySelector('i.fas');
            if (statusIcon) {
                statusIcon.className = isRunning ? 
                    'fas fa-heartbeat me-2' : 
                    'fas fa-heart-broken me-2';
            }
        }
        
        // Update status badge
        const statusBadge = document.getElementById('statusBadge');
        if (statusBadge) {
            statusBadge.className = isRunning ? 
                'badge bg-success' : 
                'badge bg-danger';
            statusBadge.textContent = isRunning ? 'Running' : 'Stopped';
        }
        
        // Update toggle button if exists
        const toggleBtn = document.getElementById('toggleServiceBtn');
        if (toggleBtn) {
            toggleBtn.innerHTML = isRunning ? 
                '<i class="fas fa-stop-circle"></i> Stop Service' : 
                '<i class="fas fa-play-circle"></i> Start Service';
            toggleBtn.setAttribute('data-running', isRunning.toString());
        }
    },
    
    // Show a loading indicator during refresh
    showLoadingIndicator: function() {
        const refreshBtn = document.getElementById('refreshStatusBtn');
        if (refreshBtn) {
            refreshBtn.innerHTML = '<i class="fas fa-sync fa-spin"></i> Refreshing...';
            refreshBtn.disabled = true;
        }
    },
    
    // Show success after refresh
    showRefreshSuccess: function() {
        const refreshBtn = document.getElementById('refreshStatusBtn');
        if (refreshBtn) {
            refreshBtn.innerHTML = '<i class="fas fa-check"></i> Refreshed';
            
            // Reset button after a delay
            setTimeout(() => {
                refreshBtn.innerHTML = '<i class="fas fa-sync"></i> Refresh Status';
                refreshBtn.disabled = false;
            }, 1500);
        }
    },
    
    // Show error after refresh failure
    showRefreshError: function(error) {
        const refreshBtn = document.getElementById('refreshStatusBtn');
        if (refreshBtn) {
            refreshBtn.innerHTML = '<i class="fas fa-times"></i> Failed';
            
            // Show error notification
            this.showToast('Failed to refresh status: ' + error.message, 'danger');
            
            // Reset button after a delay
            setTimeout(() => {
                refreshBtn.innerHTML = '<i class="fas fa-sync"></i> Refresh Status';
                refreshBtn.disabled = false;
            }, 1500);
        }
    },
    
    // Format any timestamps on the page
    formatTimestamps: function() {
        document.querySelectorAll('.timestamp').forEach(element => {
            try {
                const timestamp = element.getAttribute('data-time');
                if (timestamp) {
                    const date = new Date(timestamp);
                    element.textContent = date.toLocaleString();
                }
            } catch (e) {
                // Leave original text if formatting fails
            }
        });
    },
    
    // Show a toast notification
    showToast: function(message, type = 'info') {
        // Try to use global showToast if available
        if (typeof window.showToast === 'function') {
            window.showToast(message, type);
            return;
        }
        
        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast-notification bg-${type}`;
        toast.innerHTML = `
            <div class="toast-content">
                <i class="fas ${
                    type === 'success' ? 'fa-check-circle' : 
                    type === 'danger' ? 'fa-times-circle' :
                    type === 'warning' ? 'fa-exclamation-triangle' : 
                    'fa-info-circle'
                } me-2"></i>
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
};

// Initialize when the document is ready
document.addEventListener('DOMContentLoaded', function() {
    KeepAliveMonitor.init();
});
