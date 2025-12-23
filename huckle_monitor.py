import os
import sys
import logging
from datetime import datetime, timedelta
from huckleberry_api.api import HuckleberryAPI
from textual.app import App, ComposeResult
from textual.widgets import Static
from textual.containers import Grid
from textual import work

# Configure logging to a file to avoid messing up the TUI
logging.basicConfig(
    filename='huckle_monitor.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
# Silence the huckleberry_api logger
logging.getLogger('huckleberry_api').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

class HuckleberryTUI(App):
    CSS = """
    #container {
        width: 100%;
        height: 100%;
        border: solid grey;
        layout: grid;
        grid-size: 2;
        grid-columns: 1fr 1fr;
        align: center middle;
    }
    .data {
        content-align: right middle;
        padding-right: 1;
    }
    .label {
        content-align: left middle;
        padding-left: 1;
        color: $text-muted;
    }
    """

    def __init__(self):
        super().__init__()
        self.last_feed_time = None
        self.last_feed_amount = 0
        self.last_feed_unit = "ml"
        self.api = None

    def compose(self) -> ComposeResult:
        with Grid(id="container"):
            yield Static("", id="last_feed", classes="data")
            yield Static("", id="last_volume", classes="label")
            yield Static("", id="elapsed", classes="data")
            yield Static("elapsed", classes="label")
            yield Static("", id="nap_time", classes="data")
            yield Static("naptime", classes="label")
            yield Static("", id="short_wake", classes="data")
            yield Static("short wake", classes="label")
            yield Static("", id="long_wake", classes="data")
            yield Static("long wake", classes="label")

    def on_mount(self) -> None:
        self.start_monitoring()
        self.set_interval(1, self.update_times)

    @work(exclusive=True, thread=True)
    def start_monitoring(self) -> None:
        email = os.environ.get('HUCKLEBERRY_EMAIL')
        password = os.environ.get('HUCKLEBERRY_PASSWORD')

        if not email or not password:
            self.call_from_thread(self.notify, "Missing HUCKLEBERRY_EMAIL or HUCKLEBERRY_PASSWORD", severity="error")
            return

        try:
            self.api = HuckleberryAPI(email, password)
            self.api.authenticate()
            
            children = self.api.get_children()
            if not children:
                self.call_from_thread(self.notify, "No children found!", severity="error")
                return
                
            child = children[0]
            child_uid = child['uid']
            
            logger.info(f"Monitoring feeding for: {child['name']}")
            self.api.setup_feed_listener(child_uid, self.on_feed_update)
        except Exception as e:
            logger.exception("Failed to start monitoring")
            self.call_from_thread(self.notify, f"Error: {e}", severity="error")

    def on_feed_update(self, data):
        """Callback for feed updates from the API listener thread."""
        prefs = data.get('prefs', {})
        last_bottle = prefs.get('lastBottle', {})
        
        if last_bottle:
            start = last_bottle.get('start')
            if start:
                amount = int(last_bottle.get('bottleAmount', 0))
                unit = last_bottle.get('bottleUnits', 'ml')
                
                self.last_feed_time = datetime.fromtimestamp(start)
                self.last_feed_amount = amount
                self.last_feed_unit = unit
                
                # Update UI from thread
                self.call_from_thread(self.refresh_ui)
        else:
            logger.debug("No last bottle found in update.")

    def refresh_ui(self) -> None:
        if self.last_feed_time:
            time_str = self.last_feed_time.strftime('%H:%M')
            self.query_one("#last_feed", Static).update(f"[b]{time_str}[/b]")
            self.query_one("#last_volume", Static).update(f"{self.last_feed_amount}{self.last_feed_unit}")
            self.update_times()

    def format_diff(self, total_seconds: int) -> str:
        sign = "+" if total_seconds >= 0 else "-"
        total_seconds = abs(int(total_seconds))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{sign}{hours:02d}:{minutes:02d}"

    def update_times(self) -> None:
        if not self.last_feed_time:
            return

        now = datetime.now()
        elapsed_td = now - self.last_feed_time
        elapsed_seconds = elapsed_td.total_seconds()
        
        # Line: +hh:mm
        self.query_one("#elapsed", Static).update(f"[b]{self.format_diff(elapsed_seconds)}[/b]")

        # Midpoints (in seconds from feed)
        # Naptime: 1:07:30 (Midpoint of 1:00-1:15)
        # Short: 2:07:30 (Midpoint of 2:00-2:15)
        # Long: 2:37:30 (Midpoint of 2:30-2:45)
        midpoints = {
            "#nap_time": 1 * 3600 + 7 * 60 + 30,
            "#short_wake": 2 * 3600 + 7 * 60 + 30,
            "#long_wake": 2 * 3600 + 37 * 60 + 30
        }

        for widget_id, midpoint_sec in midpoints.items():
            diff_sec = elapsed_seconds - midpoint_sec
            self.query_one(widget_id, Static).update(f"[b]{self.format_diff(diff_sec)}±7[/b]")

    def on_unmount(self) -> None:
        if self.api:
            # Try to stop listeners gracefully
            try:
                self.api.stop_all_listeners()
            except:
                pass

if __name__ == "__main__":
    app = HuckleberryTUI()
    app.run()