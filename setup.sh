#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Meeting Countdown Timer — Setup Script
# Run this once to install the LaunchAgent on your Mac.
# ─────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.meeting.countdown"
PLIST_SRC="$SCRIPT_DIR/$PLIST_NAME.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
CONFIG_FILE="$SCRIPT_DIR/config.ini"

echo ""
echo "  Meeting Countdown Timer — Setup"
echo "  ================================"
echo ""

# ── Check for icalBuddy ──────────────────────────────────────
if ! command -v icalBuddy &>/dev/null && \
   [ ! -f /opt/homebrew/bin/icalBuddy ] && \
   [ ! -f /usr/local/bin/icalBuddy ]; then
    echo "  ✗ icalBuddy is required but not installed."
    echo ""
    echo "  Install it with:"
    echo "    brew install ical-buddy"
    echo ""
    exit 1
fi
echo "  ✓ icalBuddy found"

# ── Interactive configuration ────────────────────────────────
if [ ! -f "$CONFIG_FILE" ]; then
    echo "  No config.ini found — let's create one."
    echo ""

    read -p "  Path to countdown audio file [$SCRIPT_DIR/countdown.mp3]: " AUDIO_FILE
    AUDIO_FILE="${AUDIO_FILE:-$SCRIPT_DIR/countdown.mp3}"

    read -p "  Countdown duration in seconds [34]: " DURATION
    DURATION="${DURATION:-34}"

    read -p "  Calendar account to filter (leave blank for all calendars): " CAL_ACCOUNT

    cat > "$CONFIG_FILE" <<EOCONFIG
[countdown]
audio_file = $AUDIO_FILE
duration = $DURATION
poll_interval = 15
calendar_account = $CAL_ACCOUNT
EOCONFIG

    echo ""
    echo "  ✓ Created config.ini"
    echo ""
fi

# ── Check for audio file ────────────────────────────────────
AUDIO_FILE=$(python3 -c "
import configparser, pathlib
c = configparser.ConfigParser()
c.read('$CONFIG_FILE')
print(c.get('countdown', 'audio_file', fallback='$SCRIPT_DIR/countdown.mp3'))
")

if [ ! -f "$AUDIO_FILE" ]; then
    echo "  ⚠  Audio file not found: $AUDIO_FILE"
    echo ""
    echo "  Place your countdown MP3 at that path before running."
    echo "  (e.g. BBC News 30s countdown from https://archive.org/details/tvtunes_26038)"
    echo ""
    read -p "  Continue setup anyway? (y/N) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "  Setup cancelled. Add the audio file and re-run."
        exit 1
    fi
fi

# ── Install LaunchAgent ──────────────────────────────────────

# Unload existing agent if running
if launchctl list | grep -q "$PLIST_NAME" 2>/dev/null; then
    echo "  Stopping existing agent..."
    launchctl unload "$PLIST_DST" 2>/dev/null || true
fi

echo "  Configuring LaunchAgent..."
SCRIPT_PATH="$SCRIPT_DIR/meeting_countdown.py"
sed "s|PLACEHOLDER_SCRIPT_PATH|$SCRIPT_PATH|g" "$PLIST_SRC" | \
sed "s|PLACEHOLDER_LOG_PATH|$SCRIPT_DIR|g" > "$PLIST_DST"

chmod +x "$SCRIPT_DIR/meeting_countdown.py"

echo "  Starting agent..."
launchctl load "$PLIST_DST"

echo ""
echo "  ✓ Done! The countdown timer is now running."
echo ""
echo "  How it works:"
echo "    • Runs in the background, starts on login"
echo "    • Checks your macOS Calendar for today's first meeting"
echo "    • Plays the countdown audio, ending exactly at meeting start"
echo "    • Only plays once per day (first meeting only)"
echo ""
echo "  Commands:"
echo "    Test audio:   python3 '$SCRIPT_PATH' --test"
echo "    View logs:    tail -f '$SCRIPT_DIR/meeting_countdown.log'"
echo "    Stop:         launchctl unload '$PLIST_DST'"
echo "    Restart:      launchctl unload '$PLIST_DST' && launchctl load '$PLIST_DST'"
echo "    Uninstall:    launchctl unload '$PLIST_DST' && rm '$PLIST_DST'"
echo ""
