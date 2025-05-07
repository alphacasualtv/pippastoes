# Discord Link Mover Bot

A Discord bot that automatically monitors a specific channel for links, deletes the original messages, and reposts the links to a designated channel.

## Features

- Monitors a specific Discord channel for messages containing URLs
- Extracts links from messages
- Deletes the original message containing the link
- Reposts the link to a designated channel with a reference to the source
- Configurable through environment variables
- Supports posting via Discord webhooks (alternative to direct bot posting)
- **Ready for Docker, Portainer, and GitHub deployment**

## Prerequisites

- Python 3.8 or higher (for manual runs)
- A Discord account
- Permission to create and invite bots to a Discord server

## Setup Instructions

### 1. Create a Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Navigate to the "Bot" tab and click "Add Bot"
4. Under the "Privileged Gateway Intents" section, enable "MESSAGE CONTENT INTENT"
5. Copy your bot token (you'll need this later)

### 2. Invite the Bot to Your Server

1. In the Developer Portal, go to the "OAuth2" → "URL Generator" tab
2. Select the following scopes:
   - `bot`
3. Select the following bot permissions:
   - Read Messages/View Channels
   - Send Messages
   - Manage Messages (to delete messages)
   - Read Message History
4. Copy the generated URL and open it in your browser
5. Select your server and authorize the bot

### 3. (Optional) Create a Discord Webhook

If you prefer to use a webhook for posting links (instead of the bot posting directly):

1. Go to the Discord server where you want the bot to post links
2. Right-click on the destination channel and select "Edit Channel"
3. Go to the "Integrations" tab
4. Click on "Webhooks" and then "New Webhook"
5. Give the webhook a name and copy the webhook URL
6. You'll use this URL in your .env file later

### 4. Install the Bot (Manual Python)

1. Clone this repository or download the files
2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   ```
3. Activate the virtual environment:
   - Windows: `venv\Scripts\activate`
   - macOS/Linux: `source venv/bin/activate`
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### 5. Configure the Bot

1. Copy the `.env.example` file to a new file named `.env`:
   ```bash
   cp .env.example .env
   ```
2. Open the `.env` file and replace the placeholder values:
   - `BOT_TOKEN`: Your bot token from the Discord Developer Portal
   - `SOURCE_CHANNEL_ID`: The ID of the channel to monitor for links
   - `DESTINATION_CHANNEL_ID`: The ID of the channel where links will be reposted

   > **How to get channel IDs**: In Discord, enable Developer Mode in Settings → Advanced, then right-click on a channel and select "Copy ID"

### 6. Run the Bot (Manual Python)

```bash
python link_mover_direct_channel.py
```

If everything is set up correctly, you should see a message indicating that the bot has connected to Discord.

## Docker & Portainer Deployment

### 1. Build and Run with Docker Compose

1. Ensure you have Docker and Docker Compose installed (or use Portainer).
2. Copy `.env.example` to `.env` and fill in your secrets.
3. Make sure you have a `logs/` directory in your project root:
   ```bash
   mkdir -p logs
   ```
4. Run:
   ```bash
   docker compose up --build -d
   ```

### 2. Persistent Data
- All logs and persistent data (including `recent_links.json`) are stored in the `logs/` directory.
- The following volume is mapped in `docker-compose.yml`:
  ```yaml
  volumes:
    - ./logs:/app/logs
  ```
- This ensures that logs and recent links are preserved across container restarts.

### 3. Permissions (Important for Portainer)
- Ensure the `logs/` directory on your host is writable by the container user (UID/GID may be 1000:1000 or as set in the Dockerfile).
- If you encounter permission errors, you can run:
  ```bash
  chmod -R 777 logs
  ```
  (or set more restrictive permissions as needed)

### 4. Portainer
- You can deploy this repository directly from GitHub in Portainer.
- Set environment variables in the Portainer UI or mount your `.env` file.
- Make sure the `logs/` volume is mapped as above.
- The container runs as a non-root user for security.

## Usage

1. When a message containing a link is posted in the designated source channel, the bot will:
   - Delete the original message
   - Repost the link to the designated link channel with a note indicating where it came from
2. The bot ignores messages without links and only processes messages from the configured source channel

## Troubleshooting

- **Bot doesn't respond**: Make sure the bot token is correct and the bot has been invited to your server
- **Bot can't delete messages**: Ensure the bot has the "Manage Messages" permission in the source channel
- **Bot can't post messages**: Ensure the bot has the "Send Messages" permission in the link channel (or use a webhook instead)
- **Bot doesn't detect links**: Make sure the link starts with http:// or https://
- **Webhook isn't working**: Verify the webhook URL is correct and hasn't been deleted or revoked
- **Permission errors in Docker/Portainer**: Ensure the `logs/` directory is writable by the container user

## License

This project is open-source and available for anyone to use and modify. 