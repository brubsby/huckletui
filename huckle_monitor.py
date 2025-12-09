import os
import sys
import logging
import time
from datetime import datetime, timezone
from huckleberry_api.api import HuckleberryAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
# Silence the huckleberry_api logger
logging.getLogger('huckleberry_api').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

def get_time_ago(timestamp_sec):
    if not timestamp_sec:
        return "never"
    
    now = datetime.now().timestamp()
    diff = int(now - timestamp_sec)
    
    if diff < 60:
        return f"{diff}s ago"
    elif diff < 3600:
        return f"{diff // 60}m ago"
    else:
        return f"{diff // 3600}h {diff % 3600 // 60}m ago"

# Global state to track last seen bottle timestamp
last_seen_bottle_timestamp = 0

def on_feed_update(data):
    """Callback for feed updates."""
    global last_seen_bottle_timestamp
    
    prefs = data.get('prefs', {})
    last_bottle = prefs.get('lastBottle', {})
    
    if last_bottle:
        start = last_bottle.get('start')
        
        # Only print if this is a new bottle event (based on timestamp)
        # using a small epsilon for float comparison safety, though exact match usually works for timestamps
        if start and abs(start - last_seen_bottle_timestamp) > 0.001:
            amount = int(last_bottle.get('bottleAmount', 0))
            unit = last_bottle.get('bottleUnits', 'ml')
            
            start_dt = datetime.fromtimestamp(start)
            # Format: 120ml@2400
            time_str = start_dt.strftime('%H%M')
            
            # Print update
            print(f"\n{amount}{unit}@{time_str}")
            
            # Update state
            last_seen_bottle_timestamp = start
        else:
            logger.debug("Received update, but bottle timestamp hasn't changed.")
    else:
        logger.debug("No last bottle found.")

        
def main():
    email = os.environ.get('HUCKLEBERRY_EMAIL')
    password = os.environ.get('HUCKLEBERRY_PASSWORD')

    if not email or not password:
        logger.error("Please set HUCKLEBERRY_EMAIL and HUCKLEBERRY_PASSWORD environment variables.")
        sys.exit(1)

    logger.info(f"Authenticating as {email}...")
    
    try:
        api = HuckleberryAPI(email, password)
        api.authenticate()
        logger.info("Authentication successful.")
        
        children = api.get_children()
        if not children:
            logger.error("No children found!")
            sys.exit(1)
            
        # For now, just pick the first child. 
        # In a real TUI we'd let the user select.
        child = children[0]
        child_uid = child['uid']
        child_name = child['name']
        
        logger.info(f"Monitoring feeding for: {child_name} (UID: {child_uid})")
        print(f"--- Listening for updates for {child_name} ---")
        print("Press Ctrl+C to exit.")

        # Set up the listener
        api.setup_feed_listener(child_uid, on_feed_update)
        
        # Keep the script running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Stopping...")
        api.stop_all_listeners()
    except Exception as e:
        logger.exception("An error occurred")
        sys.exit(1)

if __name__ == "__main__":
    main()
