import os
import sys
import logging
import time
import uuid
from datetime import datetime, timedelta
from huckleberry_api.api import HuckleberryAPI
from textual.app import App, ComposeResult
from textual.widgets import Static, Input, Label
from textual.containers import Grid, Vertical
from textual.screen import ModalScreen
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

class BottleLogScreen(ModalScreen[int]):
    """Screen for logging a bottle feeding."""
    BINDINGS = [("escape", "dismiss", "Dismiss")]
    CSS = """
    BottleLogScreen {
        align: center middle;
    }
    #dialog {
        width: 17;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    Input {
        margin-top: 1;
    }
    """
    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Amount (ml):")
            yield Input(placeholder="ml", id="amount_input", restrict=r"^[0-9]*$")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def action_dismiss(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        try:
            if event.value:
                amount = int(event.value)
                self.dismiss(amount)
            else:
                self.dismiss(None)
        except ValueError:
            self.notify("Please enter a valid number", severity="error")

class HuckleberryTUI(App):
    BINDINGS = [
        ("l", "log_bottle", "Log Bottle"),
        ("ctrl+c", "quit", "Quit")
    ]
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
        self.child_uid = None

    def compose(self) -> ComposeResult:
        with Grid(id="container"):
            yield Static("", id="last_feed", classes="data")
            yield Static("", id="last_volume", classes="label")
            yield Static("", id="elapsed", classes="data")
            yield Static("since", classes="label")
            yield Static("", id="nap_time", classes="data")
            yield Static("sleepy", classes="label")
            yield Static("", id="short_wake", classes="data")
            yield Static("short", classes="label")
            yield Static("", id="long_wake", classes="data")
            yield Static("long", classes="label")

    def on_mount(self) -> None:
        self.start_monitoring()
        self.set_interval(1, self.update_times)

    def action_log_bottle(self) -> None:
        self.push_screen(BottleLogScreen(), self.do_log_bottle)

    @work(exclusive=True, thread=True)
    def do_log_bottle(self, amount: int | None) -> None:
        if amount is None or not self.api or not self.child_uid:
            return

        try:
            logger.info(f"Logging bottle: {amount}ml")
            
            # Use the underlying firestore client from the API
            # Since we can't easily modify the library, we'll implement it here
            db = self.api._get_firestore_client()
            feed_ref = db.collection("feed").document(self.child_uid)
            
            now_time = time.time()
            # Calculate offset in minutes (UTC - Local)
            # time.localtime().tm_gmtoff is seconds east of UTC
            offset = -time.localtime(now_time).tm_gmtoff / 60
            interval_id = f"{int(now_time * 1000)}-{uuid.uuid4().hex[:20]}"
            
            # Create interval
            feed_ref.collection("intervals").document(interval_id).set({
                "mode": "bottle",
                "start": now_time,
                "amount": float(amount),
                "units": "ml",
                "bottleType": "Formula",
                "lastUpdated": now_time,
                "offset": offset,
                "end_offset": offset,
            })
            
            # Update prefs
            feed_ref.update({
                "prefs.lastBottle": {
                    "mode": "bottle",
                    "start": now_time,
                    "bottleAmount": float(amount),
                    "bottleUnits": "ml",
                    "bottleType": "Formula",
                    "offset": offset,
                },
                "prefs.timestamp": {"seconds": now_time},
                "prefs.local_timestamp": now_time,
            })
            
            self.call_from_thread(self.notify, f"Logged {amount}ml bottle")
        except Exception as e:
            logger.exception("Failed to log bottle")
            self.call_from_thread(self.notify, f"Error: {e}", severity="error")

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
            self.child_uid = child['uid']
            
            logger.info(f"Monitoring feeding for: {child['name']}")
            self.api.setup_feed_listener(self.child_uid, self.on_feed_update)
        except Exception as e:
            logger.exception("Failed to start monitoring")
            self.call_from_thread(self.notify, f"Error: {e}", severity="error")

    def on_feed_update(self, data):
        """Callback for feed updates from the API listener thread."""
        logger.debug(f"Raw feed update data: {data}")
        prefs = data.get('prefs', {})
        last_bottle = prefs.get('lastBottle', {})
        
        if last_bottle:
            logger.info(f"Last bottle found in prefs: {last_bottle}")
            start = last_bottle.get('start')
            if start:
                # prefs.lastBottle uses bottleAmount/bottleUnits
                amount = last_bottle.get('bottleAmount', 0)
                unit = last_bottle.get('bottleUnits', 'ml')
                logger.info(f"Extracted bottle info: amount={amount}, unit={unit}")
                
                self.last_feed_time = datetime.fromtimestamp(start)
                self.last_feed_amount = int(amount) if amount is not None else 0
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
        return f"{sign}{hours}:{minutes:02d}"

    def update_times(self) -> None:
        if not self.last_feed_time:
            return

        now = datetime.now()
        elapsed_td = now - self.last_feed_time
        elapsed_seconds = elapsed_td.total_seconds()
        
        # Line: +hh:mm
        self.query_one("#elapsed", Static).update(f"[b]{self.format_diff(elapsed_seconds)}[/b]")

        # Midpoints (in seconds from feed)
        # Sleepy: 1:07:30 (Midpoint of 1:00-1:15)
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