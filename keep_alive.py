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
from datetime import datetime

# Configure logging
logger = logging.getLogger("keep-alive")

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
            return
            
        url = f"{self.base_url.rstrip('/')}{self.endpoint}"
        try:
            logger.debug(f"Pinging {url}...")
            response = requests.get(
                url, 
                timeout=10,
                headers={'User-Agent': 'KeepAliveService/1.0',
                         'X-Keep-Alive': 'true'}
            )
            
            if response.status_code == 200:
                self.ping_count += 1
                self.last_ping_time = datetime.now()
                self.stats['pings'] += 1
                self.stats['last_ping'] = self.last_ping_time.isoformat()
                logger.info(f"Ping successful: {url} (ping #{self.ping_count})")
            else:
                self.error_count += 1
                self.stats['errors'] += 1
                error_msg = f"Ping failed with status code {response.status_code}: {url}"
                self.stats['last_error'] = {
                    'time': datetime.now().isoformat(),
                    'message': error_msg
                }
                logger.warning(error_msg)
                
        except Exception as e:
            self.error_count += 1
            self.stats['errors'] += 1
            error_msg = f"Error pinging {url}: {str(e)}"
            self.stats['last_error'] = {
                'time': datetime.now().isoformat(),
                'message': error_msg,
                'traceback': traceback.format_exc()
            }
            logger.error(error_msg)
    
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

def init_keep_alive(app_url, interval_minutes=10, endpoint='/health', enabled=True):
    """
    Initialize and start the keep-alive service.
    
    Args:
        app_url (str): The URL of the application.
        interval_minutes (int): Time between pings in minutes.
        endpoint (str): The endpoint to ping.
        enabled (bool): Whether the service is enabled.
    """
    global keep_alive_service
    
    # Configure the service
    keep_alive_service.base_url = app_url
    keep_alive_service.interval_minutes = interval_minutes
    keep_alive_service.endpoint = endpoint
    keep_alive_service.enabled = enabled
    
    # Start the service if enabled
    if enabled:
        return keep_alive_service.start()
    return False

def get_keep_alive_status():
    """Get the current status of the keep-alive service."""
    global keep_alive_service
    return keep_alive_service.get_status()
