# huckletui

A terminal user interface (TUI) for real-time monitoring and logging of bottle feedings in the Huckleberry baby tracker.

Designed to be a quick, low-friction way to track your baby's schedule at a glance.

## Features

- **Real-time Monitoring**: Automatically updates when data is logged in the Huckleberry mobile app.
- **Feeding History**: Displays the time and volume of the most recent bottle feeding.
- **Smart Timers**:
  - **Elapsed**: Time since the last feeding logged.
  - **Naptime**: Target window for the start of naptime.
  - **Short Wake**: Target window to estimate wake time after a short nap.
  - **Long Wake**: Target window to estimate wake time after a long nap.
- **Bottle Logging**: Quickly log a new bottle feeding with a custom volume (ml) at the current time.

## Setup

### Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) (recommended)

### Environment Variables

The application requires your Huckleberry credentials to be set in your environment:

```bash
export HUCKLEBERRY_EMAIL="your-email@example.com"
export HUCKLEBERRY_PASSWORD="your-password"
```

## Usage

To start the monitor:

```bash
uv run huckle_monitor.py
```

### Key Bindings

|  Key     | Action               |
|----------|----------------------|
| `l`      | Log a bottle feeding |
| `ctrl+q` | Quit the application |

## Technical Details

- **Framework**: Built with [Textual](https://textual.textualize.io/).
- **API**: Uses [py-huckleberry-api](https://github.com/tbradlo/py-huckleberry-api) for authentication and real-time listeners.
- **Database**: Interacts directly with Huckleberry's Firestore backend for high-fidelity logging.

## Disclaimer

We only use the formula bottle feeding feature of Huckleberry, so that's the majority of what this app revolves around. Feel free to fork and extend the functionality though!
