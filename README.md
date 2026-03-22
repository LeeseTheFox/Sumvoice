# Sumvoice Bot

This repository contains two Telegram bots for transcribing and summarizing voice messages and audio files:

1. **SumvoiceBot** - A traditional Telegram bot that uses a bot token
2. **Sumvoice Userbot** - A userbot that runs on your personal Telegram account

## Setup

### Prerequisites
- Python 3.7+
- Groq API key (for AI transcription and summarization)

### Installation

1. Clone this repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Create a `.env` file with the following variables:
   ```
   # Required for both bots
   GROQ_API_KEY=your_groq_api_key
   
   # Required only for SumvoiceBot
   TELEGRAM_TOKEN=your_telegram_bot_token
   ADMIN_ID=your_telegram_user_id  # Required for /whitelist and /toggle_whitelist commands
   WHITELIST_IDS=comma,separated,list,of,allowed,user,ids

   # Required only for Sumvoice Userbot
   PYROGRAM_API_ID=your_pyrogram_api_id
   PYROGRAM_API_HASH=your_pyrogram_api_hash
   ```

## Usage

### SumvoiceBot

Run the traditional bot with:
```
python sumvoice_bot.py
```

Send a voice message or audio file to the bot, and it will transcribe and summarize it. You can then ask questions about the content.

### Sumvoice Userbot

Run the userbot with:
```
python sumvoice_userbot.py
```

On first run, you'll need to authenticate with your Telegram account.

To use the userbot:
1. Find a voice message or audio file in any chat
2. Reply to it with `.sumvoice`
3. The userbot will process it and reply with a summary

## Features

### SumvoiceBot
- Transcription and summarization of voice messages and audio files
- Question answering about transcribed content
- User whitelist system
- Admin commands for managing users

### Sumvoice Userbot
- Simple command-based interface (`.sumvoice`)
- Works in private chats and groups
- Lightweight with minimal features
- Runs on your personal Telegram account

## Commands

- `/start` - Start the bot and get a welcome message
- `/help` - Display help information 