# Discord CTF Reminder Bot

A Discord bot that helps manage CTF competitions, including reminders, participant management, and timezone support.

## Features

- CTF competition management
  - Add competitions from CTFtime
  - List all competitions
  - Delete competitions
  - Join/leave competitions
  - View your participating competitions
- Automatic reminders
  - 24 hours before competition starts
  - When competition starts
- Timezone support
  - Set personal timezone
  - View time in your timezone
- Role management
  - Automatic role creation for competitions
  - Role assignment when joining competitions
- Utility commands
  - Base64 encoding/decoding
  - Ping test

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/discord-ctf-remind-bot.git
cd discord-ctf-remind-bot
```

2. Create and activate virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies using uv:
   ```bash
uv pip install -r requirements.txt
   ```

4. Create `.env` file and add your Discord bot token:
   ```
DISCORD_TOKEN=your_bot_token_here
   ```

## Usage

1. Start the bot:
   ```bash
   python main.py
   ```

2. Bot commands:
- `!timezone` - View current timezone
- `!timezone list` - Show available timezones
- `!timezone <timezone>` - Set timezone (e.g., `!timezone Asia/Taipei`)
- `!addctf <ctftime_id>` - Add CTF competition
- `!listctf` - List all competitions
- `!delctf <ctftime_id>` - Delete competition
- `!joinctf <ctftime_id>` - Join competition
- `!leavectf <ctftime_id>` - Leave competition
- `!myctf` - View your competitions
- `!base64 encode <text>` - Encode text to base64
- `!base64 decode <text>` - Decode base64 to text
- `!ping` - Test bot response time

## Requirements

- Python 3.8+
- discord.py
- pytz
- requests
- python-dotenv

## License

MIT License
