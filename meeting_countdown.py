#!/usr/bin/env python3
"""
Meeting Countdown Timer
=======================
Polls macOS Calendar (synced with Google Calendar) and plays a countdown
audio clip timed to end exactly when your FIRST meeting of the day starts.
After that, it sleeps until midnight and resets.

Requirements:
  - macOS with a calendar synced to Calendar.app
    (System Settings → Internet Accounts → Google / Exchange / etc.)
  - Python 3.9+
  - icalBuddy (brew install ical-buddy)
  - A countdown audio file (e.g. the BBC News 30s countdown)

Usage:
  python3 meeting_countdown.py          # run in foreground
  python3 meeting_countdown.py --test   # test audio playback immediately

Configuration:
  Copy config.example.ini to config.ini and edit to taste, or set
  environment variables (see README).
"""

import configparser
import os
import subprocess
import sys
import time
import signal
import logging
from typing import Optional
from datetime import datetime, timedelta
from pathlib import Path

# ─── Configuration ───────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
_config = configparser.ConfigParser()
_config.read(SCRIPT_DIR / "config.ini")

def _cfg(key: str, fallback: str) -> str:
    """Read from [countdown] in config.ini, then env var, then fallback."""
    env_key = f"COUNTDOWN_{key.upper()}"
    return _config.get("countdown", key, fallback=os.environ.get(env_key, fallback))

AUDIO_FILENAME = _cfg("audio_file", str(SCRIPT_DIR / "countdown.mp3"))
COUNTDOWN_DURATION = int(_cfg("duration", "34"))
POLL_INTERVAL = int(_cfg("poll_interval", "15"))
CALENDAR_ACCOUNT = _cfg("calendar_account", "")
LOG_FILE = Path(_cfg("log_file", str(SCRIPT_DIR / "meeting_countdown.log")))
STATE_FILE = SCRIPT_DIR / ".last_played_date"

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("meeting_countdown")

# ─── Globals ─────────────────────────────────────────────────────────────────
AUDIO_PATH = Path(AUDIO_FILENAME)
audio_process = None


def already_played_today() -> bool:
    """Check if we already played the countdown today."""
    if STATE_FILE.exists():
        last_date = STATE_FILE.read_text().strip()
        return last_date == datetime.now().strftime("%Y-%m-%d")
    return False


def mark_played_today():
    """Record that we played the countdown today."""
    STATE_FILE.write_text(datetime.now().strftime("%Y-%m-%d"))


def _find_icalbuddy() -> str:
    """Locate the icalBuddy binary. LaunchAgents don't inherit shell PATH."""
    for path in ["/opt/homebrew/bin/icalBuddy", "/usr/local/bin/icalBuddy"]:
        if Path(path).exists():
            return path
    raise FileNotFoundError(
        "icalBuddy not found. Install it with: brew install ical-buddy"
    )


def get_first_meeting_today() -> Optional[dict]:
    """
    Query macOS Calendar.app via icalBuddy for today's first upcoming event.
    Returns dict with 'title', 'start_time', 'uid' or None.
    """
    ical_path = _find_icalbuddy()
    return _query_icalbuddy(ical_path)


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    import re
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


def _query_icalbuddy(ical_path: str = "icalBuddy") -> Optional[dict]:
    """Query calendar using icalBuddy (fast, no timeout issues)."""
    try:
        import re
        log.info("Querying calendar via icalBuddy: %s", ical_path)

        # Set TERM=dumb to suppress color output
        import os
        env = os.environ.copy()
        env["TERM"] = "dumb"

        result = subprocess.run(
            [
                ical_path,
                "-nc",                       # no calendar names
                "-nrd",                      # no relative dates
                "-npn",                      # no property names
                "-ea",                       # exclude all-day events
                "-uid",                      # show UIDs
                "-eep", "notes,attendees,location,url",  # exclude noisy properties
                "-li", "1",                  # limit to 1 event
                *((["-ic", CALENDAR_ACCOUNT]) if CALENDAR_ACCOUNT else []),
                "eventsToday",
            ],
            capture_output=True, text=True, timeout=10,
            env=env,
        )
        if result.returncode != 0 or not result.stdout.strip():
            log.info("icalBuddy returned no events")
            return None

        # Strip ANSI color codes
        output = _strip_ansi(result.stdout).strip()
        lines = output.split("\n")
        log.info("icalBuddy clean output: %s", repr(output[:300]))

        # Line 1: event title (e.g. "• Daily Sync")
        title = lines[0].strip().lstrip("•").strip()

        start_time = None
        uid = title

        for line in lines[1:]:
            stripped = line.strip()

            # Match time patterns:
            #   "7:00 PM - 8:00 PM"  (12-hour, may have \u202f narrow no-break space)
            #   "19:00 - 20:00"      (24-hour)
            #   "19:00:00 - 20:00:00" (24-hour with seconds)
            # Normalize non-breaking spaces first
            normalized = stripped.replace('\u202f', ' ').replace('\xa0', ' ')
            time_match = re.match(
                r'^(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap][Mm])?)\s*-\s*\d{1,2}:\d{2}',
                normalized
            )
            if time_match:
                time_str = time_match.group(1).strip()
                today = datetime.now().strftime("%Y-%m-%d")
                # Try 12-hour formats first, then 24-hour
                for fmt in ["%Y-%m-%d %I:%M %p", "%Y-%m-%d %I:%M:%S %p",
                            "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]:
                    try:
                        start_time = datetime.strptime(today + " " + time_str, fmt)
                        break
                    except ValueError:
                        continue

            if stripped.startswith("uid:") or re.match(r'^[a-f0-9]{10,}', stripped):
                uid = stripped.replace("uid:", "").strip()

        if start_time is None:
            log.warning("Could not parse time from icalBuddy output")
            return None

        if start_time < datetime.now():
            log.info("Meeting \"%s\" already started, skipping", title)
            return None

        log.info("Found meeting: \"%s\" at %s (uid: %s)", title, start_time, uid[:20])
        return {"title": title, "start_time": start_time, "uid": uid}
    except Exception as e:
        log.warning("icalBuddy error: %s", e)
    return None



def play_countdown() -> bool:
    """Play the countdown audio using macOS afplay."""
    global audio_process
    if not AUDIO_PATH.exists():
        log.error("Audio file not found: %s", AUDIO_PATH)
        return False
    try:
        log.info("Playing countdown: %s", AUDIO_PATH.name)
        audio_process = subprocess.Popen(
            ["afplay", str(AUDIO_PATH)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as e:
        log.error("Failed to play audio: %s", e)
        return False


def stop_audio():
    global audio_process
    if audio_process and audio_process.poll() is None:
        audio_process.terminate()
        audio_process = None


def handle_signal(signum, frame):
    log.info("Shutting down (signal %d)...", signum)
    stop_audio()
    sys.exit(0)


def seconds_until_midnight() -> float:
    now = datetime.now()
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (midnight - now).total_seconds()


def test_mode():
    log.info("=== TEST MODE ===")
    if not AUDIO_PATH.exists():
        log.error("Audio file not found: %s", AUDIO_PATH)
        log.error("Place your countdown MP3 at that path and retry.")
        sys.exit(1)
    log.info("Playing countdown now...")
    play_countdown()
    if audio_process:
        audio_process.wait()
    log.info("Done.")


def main():
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    if "--test" in sys.argv:
        test_mode()
        return

    log.info("=" * 60)
    log.info("Meeting Countdown Timer")
    log.info("Audio   : %s %s", AUDIO_PATH, "(OK)" if AUDIO_PATH.exists() else "(MISSING)")
    log.info("Length  : %ds countdown", COUNTDOWN_DURATION)
    log.info("Account : %s", CALENDAR_ACCOUNT or "(all calendars)")
    log.info("Poll    : every %ds", POLL_INTERVAL)
    log.info("=" * 60)

    if not AUDIO_PATH.exists():
        log.warning("Audio file missing! Place your MP3 at: %s", AUDIO_PATH)

    while True:
        try:
            # If already played today, sleep until midnight then reset
            if already_played_today():
                wait = seconds_until_midnight() + 5
                log.info("Already played today. Sleeping %.0f min until midnight...", wait / 60)
                time.sleep(wait)
                continue

            event = get_first_meeting_today()
            now = datetime.now()

            if event is None:
                log.info("No upcoming meetings today. Checking again in 5 min...")
                time.sleep(300)
                continue

            seconds_until = (event["start_time"] - now).total_seconds()
            play_at = seconds_until - COUNTDOWN_DURATION

            if seconds_until < -60:
                # Meeting already started more than a minute ago — skip today
                log.info("First meeting \"%s\" already started. Done for today.", event["title"])
                mark_played_today()
                continue

            if play_at > POLL_INTERVAL + 5:
                # Too far away — just log and wait
                mins = play_at / 60
                log.info(
                    "First meeting \"%s\" at %s (%.0f min away). Waiting...",
                    event["title"],
                    event["start_time"].strftime("%H:%M"),
                    mins,
                )
                # Sleep for at most half the remaining time, or poll interval
                time.sleep(min(play_at / 2, 60))
                continue

            # Time to play!
            if play_at > 0:
                log.info(
                    "  \"%s\" starts at %s — playing in %.1fs...",
                    event["title"],
                    event["start_time"].strftime("%H:%M:%S"),
                    play_at,
                )
                time.sleep(play_at)

            log.info(
                "  \"%s\" — countdown started! Meeting begins in %ds.",
                event["title"], COUNTDOWN_DURATION,
            )
            play_countdown()
            mark_played_today()

            # Wait for audio to finish
            if audio_process:
                audio_process.wait()

        except KeyboardInterrupt:
            break
        except Exception as e:
            log.error("Unexpected error: %s", e)
            time.sleep(POLL_INTERVAL)

    stop_audio()
    log.info("Goodbye!")


if __name__ == "__main__":
    main()
