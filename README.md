# Meeting Countdown Music
A background service that plays a countdown audio clip timed to end exactly when your first meeting of the day starts. 

Inspired by this tweet: https://x.com/rtwlz/status/2036082537949434164 that played the BBC news theme (epic)

## How it works

1. Polls your macOS Calendar for today's first upcoming meeting.
2. Calculates when to start playing so the audio finishes right as the meeting begins.
3. Plays the countdown, then sleeps until midnight and resets for the next day.

Only the **first** meeting each day gets the countdown treatment.

## Requirements

- **macOS** (uses Calendar.app, `afplay`, and `launchctl`)
- **Python 3.9+** (ships with macOS)
- **[icalBuddy](https://formulae.brew.sh/formula/ical-buddy)** -- reads events from Calendar.app: `brew install ical-buddy`
- **A calendar synced to Calendar.app** (Google, Exchange, iCloud, etc. via System Settings > Internet Accounts)
- **A countdown audio file** (you supply your own MP3 -- see below)

## Quick start

```bash
# Install icalBuddy
brew install ical-buddy

git clone https://github.com/YOUR_USERNAME/meeting-countdown.git
cd meeting-countdown

# Copy and edit config
cp config.example.ini config.ini
# Edit config.ini with your audio file path and calendar account

# Place your countdown audio file in this directory (or update config.ini with the path)
# e.g. cp ~/Downloads/bbc_countdown.mp3 ./countdown.mp3

# Run setup to install as a background service
./setup.sh
```

The setup script will:
- Create `config.ini` interactively if it doesn't exist
- Install a macOS LaunchAgent that starts on login
- Begin monitoring your calendar immediately

## Configuration

Copy `config.example.ini` to `config.ini` and edit:

| Setting | Default | Description |
|---------|---------|-------------|
| `audio_file` | `countdown.mp3` | Path to your countdown audio (absolute or relative) |
| `duration` | `34` | Length of the audio in seconds |
| `poll_interval` | `15` | Seconds between calendar checks |
| `calendar_account` | *(blank = all)* | Filter to a specific calendar account (e.g. `you@gmail.com`) |

## Where to get a countdown audio file

The repo does not include an audio file. Some options:

- [BBC News countdown on archive.org](https://archive.org/details/tvtunes_26038)


## Usage

```bash
# Test that audio plays correctly
python3 meeting_countdown.py --test

# Run in foreground (for debugging)
python3 meeting_countdown.py

# View logs
tail -f meeting_countdown.log
```

## Managing the background service

```bash
# Stop
launchctl unload ~/Library/LaunchAgents/com.meeting.countdown.plist

# Start
launchctl load ~/Library/LaunchAgents/com.meeting.countdown.plist

# Restart
launchctl unload ~/Library/LaunchAgents/com.meeting.countdown.plist && \
launchctl load ~/Library/LaunchAgents/com.meeting.countdown.plist

# Uninstall completely
launchctl unload ~/Library/LaunchAgents/com.meeting.countdown.plist && \
rm ~/Library/LaunchAgents/com.meeting.countdown.plist
```

## How calendar lookup works

The script uses [icalBuddy](https://hasseg.org/icalBuddy/) to read events directly from the macOS Calendar store. It's fast, reliable, and doesn't require Calendar.app to be running. Any calendar account synced through System Settings (Google, Exchange, iCloud, etc.) will work.

## License

MIT
