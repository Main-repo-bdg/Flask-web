"""
Keep Alive Module for Webhook Data Viewer

This module provides functionality to keep the Render-hosted application 
active by sending periodic requests, preventing it from spinning down 
due to inactivity on the free tier.

Features:
- Background thread that periodically pings the application
- Configurable interval and endpoint
- Error handling and automatic recovery
- Logging of keep-alive activities
"""

import time
import threading
import logging
import random
import traceback
import requests
import os
import sys
from datetime import datetime

# Configure logging with file and console output
logger = logging.getLogger("keep-alive")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    
    # Create file handler
    file_handler = logging.FileHandler("keep_alive.log")
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    
    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logger.info("Keep-alive logger initialized with file and console output")

class KeepAliveService:
    """
    Service to keep the application alive by sending periodic requests.
    """
    
    def __init__(self, 
                 base_url=None, 
                 interval_minutes=10, 
                 endpoint='/health', 
                 enabled=True,
                 jitter=True):
        """
        Initialize the keep-alive service.
        
        Args:
            base_url (str, optional): The base URL of the application. 
                                     If None, it will use the request's host URL.
            interval_minutes (int): Time between pings in minutes.
            endpoint (str): The endpoint to ping.
            enabled (bool): Whether the service is enabled.
            jitter (bool): Whether to add random jitter to avoid thundering herd.
        """
        self.base_url = base_url
        self.interval_minutes = max(1, min(interval_minutes, 14))  # Between 1 and 14 minutes
        self.endpoint = endpoint
        self.enabled = enabled
        self.jitter = jitter
        
        self.thread = None
        self.stop_event = threading.Event()
        self.last_ping_time = None
        self.ping_count = 0
        self.error_count = 0
        self.running = False
        
        # Stats
        self.start_time = None
        self.stats = {
            'pings': 0,
            'errors': 0,
            'last_ping': None,
            'last_error': None,
            'uptime': 0,
        }
    
    def start(self, app_url=None):
        """
        Start the keep-alive service in a background thread.
        
        Args:
            app_url (str, optional): The URL of the application, can be provided 
                                    at start time instead of init time.
        """
        if self.running:
            logger.warning("Keep-alive service is already running")
            return False
        
        if app_url:
            self.base_url = app_url
            
        if not self.base_url:
            logger.error("No base URL provided for keep-alive service")
            return False
            
        if not self.enabled:
            logger.info("Keep-alive service is disabled")
            return False
        
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._keep_alive_loop, daemon=True)
        self.thread.start()
        self.running = True
        self.start_time = datetime.now()
        
        logger.info(f"Keep-alive service started with interval of {self.interval_minutes} minutes")
        return True
    
    def stop(self):
        """Stop the keep-alive service."""
        if not self.running:
            return
            
        logger.info("Stopping keep-alive service...")
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        self.running = False
        logger.info("Keep-alive service stopped")
    
    def _keep_alive_loop(self):
        """The main loop that runs in a background thread."""
        logger.info(f"Keep-alive loop started, pinging {self.base_url}{self.endpoint} every {self.interval_minutes} minutes")
        
        # First ping immediately
        self._ping()
        
        while not self.stop_event.is_set():
            # Calculate sleep time with jitter if enabled
            sleep_time = self.interval_minutes * 60
            if self.jitter:
                # Add random jitter of ±10% to avoid thundering herd
                jitter_factor = random.uniform(0.9, 1.1)
                sleep_time = sleep_time * jitter_factor
            
            # Sleep in small increments to check for stop event
            for _ in range(int(sleep_time / 5)):
                if self.stop_event.is_set():
                    break
                time.sleep(5)
            
            # Send a ping if not stopped
            if not self.stop_event.is_set():
                self._ping()
    
    def _ping(self):
        """Send a ping to the application."""
        if not self.base_url:
            logger.error("Cannot ping: no base URL configured")
            return False
            
        url = f"{self.base_url.rstrip('/')}{self.endpoint}"
        ping_result = {
            "success": False,
            "timestamp": datetime.now().isoformat(),
            "url": url,
            "response_code": None,
            "error": None,
            "response_time_ms": 0
        }
        
        try:
            logger.debug(f"Pinging {url}...")
            
            # Record start time for response time calculation
            start_time = time.time()
            
            # Make the request with timeout
            response = requests.get(
                url, 
                timeout=10,
                headers={
                    'User-Agent': 'KeepAliveService/1.0',
                    'X-Keep-Alive': 'true',
                    'Cache-Control': 'no-cache, no-store, must-revalidate'
                }
            )
            
            # Calculate response time in milliseconds
            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)
            ping_result["response_time_ms"] = response_time_ms
            
            # Record response code
            ping_result["response_code"] = response.status_code
            
            if response.status_code == 200:
                # Success case
                self.ping_count += 1
                self.last_ping_time = datetime.now()
                self.stats['pings'] += 1
                self.stats['last_ping'] = self.last_ping_time.isoformat()
                self.stats['last_ping_details'] = ping_result
                
                # Record response time stats
                if 'response_times' not in self.stats:
                    self.stats['response_times'] = []
                self.stats['response_times'].append(response_time_ms)
                # Keep only the last 100 response times
                self.stats['response_times'] = self.stats['response_times'][-100:]
                
                # Calculate average response time
                self.stats['avg_response_time_ms'] = sum(self.stats['response_times']) / len(self.stats['response_times'])
                
                ping_result["success"] = True
                logger.info(f"Ping successful: {url} (ping #{self.ping_count}, {response_time_ms}ms)")
                return True
            else:
                # Error case - non-200 response
                self.error_count += 1
                self.stats['errors'] += 1
                
                error_msg = f"Ping failed with status code {response.status_code}: {url}"
                ping_result["error"] = error_msg
                
                try:
                    # Try to get response text for better diagnostics
                    ping_result["response_text"] = response.text[:500]  # Limit to 500 chars
                except:
                    ping_result["response_text"] = "Could not read response text"
                
                self.stats['last_error'] = {
                    'time': datetime.now().isoformat(),
                    'message': error_msg,
                    'details': ping_result
                }
                
                logger.warning(error_msg)
                return False
                
        except Exception as e:
            # Exception case
            self.error_count += 1
            self.stats['errors'] += 1
            
            error_msg = f"Error pinging {url}: {str(e)}"
            ping_result["error"] = error_msg
            ping_result["exception"] = str(e)
            ping_result["exception_type"] = type(e).__name__
            
            self.stats['last_error'] = {
                'time': datetime.now().isoformat(),
                'message': error_msg,
                'details': ping_result,
                'traceback': traceback.format_exc()
            }
            
            logger.error(error_msg)
            return False
    
    def get_status(self):
        """Get the current status of the keep-alive service."""
        if self.start_time:
            uptime_seconds = (datetime.now() - self.start_time).total_seconds()
            self.stats['uptime'] = uptime_seconds
        
        status = {
            'enabled': self.enabled,
            'running': self.running,
            'base_url': self.base_url,
            'interval_minutes': self.interval_minutes,
            'endpoint': self.endpoint,
            'ping_count': self.ping_count,
            'error_count': self.error_count,
            'last_ping_time': self.last_ping_time.isoformat() if self.last_ping_time else None,
            'stats': self.stats,
            'uptime_formatted': self._format_uptime(self.stats['uptime']) if self.running else 'Not running'
        }
        return status
    
    def _format_uptime(self, seconds):
        """Format uptime in seconds to a human-readable string."""
        days, remainder = divmod(int(seconds), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours > 0:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        if seconds > 0 or not parts:
            parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
            
        return ", ".join(parts)

# Create a global instance of the keep-alive service
keep_alive_service = KeepAliveService(enabled=True)

def init_keep_alive(app_url, interval_minutes=10, endpoint='/health', enabled=True, test_endpoint=False):
    """
    Initialize and start the keep-alive service.
    
    Args:
        app_url (str): The URL of the application.
        interval_minutes (int): Time between pings in minutes.
        endpoint (str): The endpoint to ping.
        enabled (bool): Whether the service is enabled.
        test_endpoint (bool): Whether to test the endpoint before starting the service.
        
    Returns:
        dict: Status information about the initialization process
    """
    global keep_alive_service
    
    # Create result dictionary to track what happened
    result = {
        "success": False,
        "enabled": enabled,
        "app_url": app_url,
        "interval_minutes": interval_minutes,
        "endpoint": endpoint,
        "errors": [],
        "warnings": [],
        "diagnostics": []
    }
    
    # Check if service is enabled at all
    if not enabled:
        message = "Keep-alive service not started because it is disabled"
        logger.info(message)
        result["diagnostics"].append(message)
        return result
    
    # Log initialization attempt and parameters
    init_msg = f"Initializing keep-alive service with URL: {app_url}, interval: {interval_minutes}min, endpoint: {endpoint}"
    logger.info(init_msg)
    result["diagnostics"].append(init_msg)
    
    # 1. Validate parameters
    if not app_url:
        error_msg = "Cannot initialize keep-alive service: No application URL provided"
        logger.error(error_msg)
        result["errors"].append(error_msg)
        return result
        
    # 2. Ensure URL has protocol
    if not app_url.startswith(('http://', 'https://')):
        original_url = app_url
        app_url = 'https://' + app_url
        warning_msg = f"Added https:// protocol to URL: {original_url} → {app_url}"
        logger.warning(warning_msg)
        result["warnings"].append(warning_msg)
        result["app_url"] = app_url
    
    # 3. Remove trailing slash from URL if present
    if app_url.endswith('/'):
        app_url = app_url.rstrip('/')
        result["app_url"] = app_url
        result["diagnostics"].append(f"Removed trailing slash from URL: {app_url}")
    
    # 4. Ensure endpoint starts with a slash
    if not endpoint.startswith('/'):
        endpoint = '/' + endpoint
        result["endpoint"] = endpoint
        result["diagnostics"].append(f"Added leading slash to endpoint: {endpoint}")
    
    # 5. Test the endpoint if requested
    if test_endpoint:
        test_url = f"{app_url}{endpoint}"
        logger.info(f"Testing endpoint before starting service: {test_url}")
        result["diagnostics"].append(f"Testing endpoint: {test_url}")
        
        try:
            response = requests.get(
                test_url, 
                timeout=10,
                headers={'User-Agent': 'KeepAliveService/1.0 (Test)',
                         'X-Keep-Alive': 'test'}
            )
            
            if response.status_code == 200:
                logger.info(f"Endpoint test successful: {test_url} returned 200 OK")
                result["diagnostics"].append(f"Endpoint test successful: {test_url}")
            else:
                warning_msg = f"Endpoint test warning: {test_url} returned {response.status_code}"
                logger.warning(warning_msg)
                result["warnings"].append(warning_msg)
                result["diagnostics"].append(f"Response body: {response.text[:100]}")
                
        except Exception as e:
            warning_msg = f"Endpoint test failed: {test_url} - {str(e)}"
            logger.warning(warning_msg)
            result["warnings"].append(warning_msg)
            result["diagnostics"].append(traceback.format_exc())
    
    # 6. Configure the service
    keep_alive_service.base_url = app_url
    keep_alive_service.interval_minutes = interval_minutes
    keep_alive_service.endpoint = endpoint
    keep_alive_service.enabled = enabled
    
    # 7. Restart if already running
    if keep_alive_service.running:
        try:
            keep_alive_service.stop()
            logger.info("Stopped existing keep-alive service before restart")
            result["diagnostics"].append("Stopped existing service before restart")
        except Exception as e:
            warning_msg = f"Error stopping existing keep-alive service: {str(e)}"
            logger.warning(warning_msg)
            result["warnings"].append(warning_msg)
    
    # 8. Start the service
    try:
        logger.info(f"Starting keep-alive service with {app_url}{endpoint} every {interval_minutes} minutes")
        success = keep_alive_service.start()
        
        if success:
            success_msg = f"Keep-alive service started successfully"
            logger.info(success_msg)
            result["success"] = True
            result["diagnostics"].append(success_msg)
            
            # Perform immediate ping to verify
            try:
                keep_alive_service._ping()
                verification_msg = "Immediate ping verification successful"
                logger.info(verification_msg)
                result["diagnostics"].append(verification_msg)
            except Exception as ping_e:
                warning_msg = f"Initial ping verification failed: {str(ping_e)}"
                logger.warning(warning_msg)
                result["warnings"].append(warning_msg)
                
        else:
            error_msg = "Failed to start keep-alive service"
            logger.error(error_msg)
            result["errors"].append(error_msg)
    except Exception as e:
        error_msg = f"Exception starting keep-alive service: {str(e)}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
        result["diagnostics"].append(traceback.format_exc())
    
    # Log final status
    status_msg = "Keep-alive initialization " + ("successful" if result["success"] else "failed")
    if result["warnings"]:
        status_msg += f" with {len(result['warnings'])} warnings"
    if result["errors"]:
        status_msg += f" and {len(result['errors'])} errors"
    
    logger.info(status_msg)
    return result

def get_keep_alive_status():
    """Get the current status of the keep-alive service."""
    global keep_alive_service
    return keep_alive_service.get_status()
