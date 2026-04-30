#!/usr/bin/env python
import functools
import json
import logging
import os
import tempfile

import requests
from dotenv import load_dotenv
from groq import Groq
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get tokens from environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Admin ID with special privileges
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Persistent data directory – whitelist state, session files, etc.
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)
WHITELIST_FILE = os.path.join(DATA_DIR, "whitelist.json")


def load_whitelist():
    """Load whitelist state from data/whitelist.json.

    Falls back to WHITELIST_ENABLED / WHITELIST_IDS env vars on first run
    (so they can be used to seed the initial whitelist regardless of whether
    the user is using a .env file or plain environment variables).
    """
    if os.path.exists(WHITELIST_FILE):
        try:
            with open(WHITELIST_FILE, "r") as f:
                data = json.load(f)
            enabled = bool(data.get("enabled", False))
            ids = [int(x) for x in data.get("ids", [])]
            logger.info(
                f"Whitelist loaded from file – enabled={enabled}, {len(ids)} user(s)"
            )
            return enabled, ids
        except Exception as e:
            logger.error(f"Error reading whitelist file, falling back to env vars: {e}")

    # First run or corrupted file – seed from env vars
    enabled = os.getenv("WHITELIST_ENABLED", "false").lower() in (
        "true",
        "1",
        "yes",
        "on",
    )
    ids_str = os.getenv("WHITELIST_IDS", "")
    ids = [int(uid.strip()) for uid in ids_str.split(",") if uid.strip().isdigit()]
    if enabled:
        logger.info(f"Whitelist seeded from env – enabled, {len(ids)} user(s)")
    else:
        logger.info("Whitelist seeded from env – disabled (bot responds to all users)")
    return enabled, ids


def save_whitelist(enabled, ids):
    """Persist whitelist state to data/whitelist.json."""
    try:
        with open(WHITELIST_FILE, "w") as f:
            json.dump({"enabled": enabled, "ids": ids}, f)
        return True
    except Exception as e:
        logger.error(f"Error saving whitelist: {e}")
        return False


WHITELIST_ENABLED, WHITELIST = load_whitelist()

# Validate admin configuration
if ADMIN_ID == 0:
    logger.warning(
        "⚠️  ADMIN_ID not configured! Please set your Telegram User ID in the .env file"
    )
else:
    logger.info(f"Admin ID configured: {ADMIN_ID}")

# Environment file path
ENV_FILE = ".env"

# Initialize Groq client
client = Groq(api_key=GROQ_API_KEY)


def ensure_env_file():
    """Create .env file with default settings if it doesn't exist."""
    try:
        if not os.path.exists(ENV_FILE):
            logger.info("Creating .env file with default settings")
            with open(ENV_FILE, "w") as f:
                f.write("# Telegram Bot Configuration\n")
                f.write("TELEGRAM_TOKEN=your_telegram_token_here\n")
                f.write("GROQ_API_KEY=your_groq_api_key_here\n")
                f.write("ADMIN_ID=your_telegram_user_id_here\n")
                f.write("\n# Whitelist Configuration\n")
                f.write("WHITELIST_ENABLED=false\n")
                f.write("WHITELIST_IDS=\n")
            return True
        else:
            # File exists, check if WHITELIST_ENABLED is present
            with open(ENV_FILE, "r") as f:
                content = f.read()

            # Check and add missing configuration options
            missing_configs = []
            if "ADMIN_ID=" not in content:
                missing_configs.append("ADMIN_ID=your_telegram_user_id_here")
            if "WHITELIST_ENABLED=" not in content:
                missing_configs.append("WHITELIST_ENABLED=false")

            if missing_configs:
                logger.info("Adding missing configuration to existing .env file")
                with open(ENV_FILE, "a") as f:
                    if "ADMIN_ID=" not in content:
                        f.write("\n# Admin Configuration\n")
                        f.write("ADMIN_ID=your_telegram_user_id_here\n")
                    if "WHITELIST_ENABLED=" not in content:
                        f.write("\n# Whitelist Configuration\n")
                        f.write("WHITELIST_ENABLED=false\n")
            return True
    except Exception as e:
        logger.error(f"Error ensuring .env file: {e}")
        return False


def whitelist_only(func):
    """Decorator to only allow whitelisted users to access the bot (if whitelist is enabled)."""

    @functools.wraps(func)
    async def wrapper(
        update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs
    ):
        # If whitelist is disabled, allow all users
        if not WHITELIST_ENABLED:
            return await func(update, context, *args, **kwargs)

        # If whitelist is enabled, check if user is whitelisted
        user_id = update.effective_user.id
        if user_id not in WHITELIST:
            # Silently ignore messages from non-whitelisted users
            logger.info(f"Ignored message from non-whitelisted user: {user_id}")
            return
        return await func(update, context, *args, **kwargs)

    return wrapper


def admin_only(func):
    """Decorator to only allow admin users to access the function."""

    @functools.wraps(func)
    async def wrapper(
        update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs
    ):
        user_id = update.effective_user.id
        if user_id != ADMIN_ID:
            logger.info(f"Non-admin user {user_id} tried to access admin function")
            await update.message.reply_text(
                "You don't have permission to use this command."
            )
            return
        return await func(update, context, *args, **kwargs)

    return wrapper


@whitelist_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    # Clear any existing context
    context.user_data.clear()

    await update.message.reply_text(
        "Hi! Send me a voice message or an audio file, and I'll summarize what's being said. "
        "You can then ask me questions about the content!"
    )


@whitelist_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    user_id = update.effective_user.id

    # Basic help message for all users
    help_message = (
        "Just send me a voice message or an audio file, and I'll provide a concise summary of the content. "
        "After that, you can ask me questions about the content, and I'll try to answer based on what was said. "
        "When you send a new audio file or voice message, we'll start a new conversation."
    )

    # Add admin commands for admin users
    if user_id == ADMIN_ID:
        whitelist_status = "enabled" if WHITELIST_ENABLED else "disabled"
        help_message += f"\n\nWhitelist is currently: {whitelist_status}"
        help_message += "\n\nAdmin commands:\n"
        help_message += "/whitelist [user_id] - Add a user to the whitelist\n"
        help_message += "/toggle_whitelist - Enable/disable the whitelist system"

    await update.message.reply_text(help_message)


@admin_only
async def whitelist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a user to the whitelist. Admin only command."""
    # Check if a user ID was provided
    if not context.args:
        await update.message.reply_text(
            "Please provide a user ID to whitelist.\nUsage: /whitelist [user_id]"
        )
        return

    try:
        # Get the user ID to whitelist
        new_id = int(context.args[0])

        # Check if the user is already whitelisted
        if new_id in WHITELIST:
            await update.message.reply_text(f"User {new_id} is already whitelisted.")
            return

        # Add the user to the whitelist and persist
        WHITELIST.append(new_id)

        if save_whitelist(WHITELIST_ENABLED, WHITELIST):
            await update.message.reply_text(
                f"User {new_id} has been added to the whitelist."
            )
            logger.info(
                f"Admin {update.effective_user.id} added user {new_id} to the whitelist"
            )
        else:
            await update.message.reply_text(
                f"User {new_id} has been added to the whitelist, but there was an error persisting the change."
            )

    except ValueError:
        await update.message.reply_text(
            "Invalid user ID. Please provide a valid numeric ID."
        )
    except Exception as e:
        logger.error(f"Error in whitelist command: {e}")
        await update.message.reply_text(f"An error occurred: {str(e)}")


@admin_only
async def toggle_whitelist_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Toggle the whitelist system on/off. Admin only command."""
    global WHITELIST_ENABLED

    try:
        # Toggle the current state and persist
        new_state = not WHITELIST_ENABLED

        if save_whitelist(new_state, WHITELIST):
            WHITELIST_ENABLED = new_state
            status = "enabled" if new_state else "disabled"
            await update.message.reply_text(f"Whitelist has been {status}.")
            logger.info(f"Admin {update.effective_user.id} {status} the whitelist")
        else:
            await update.message.reply_text("Failed to persist the whitelist change.")

    except Exception as e:
        logger.error(f"Error in toggle whitelist command: {e}")
        await update.message.reply_text(f"An error occurred: {str(e)}")


async def process_audio_file(file, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Transcribe an audio file or voice message and return the transcription."""
    try:
        # Get file
        audio_file = await context.bot.get_file(file.file_id)

        # Create a temporary file to save the audio
        # Voice messages don't have a file_name, so fall back to .ogg
        suffix = os.path.splitext(getattr(file, "file_name", None) or "audio.ogg")[1]
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_audio:
            # Download the audio to the temporary file
            await audio_file.download_to_drive(temp_audio.name)
            temp_filename = temp_audio.name

        # Transcribe using Groq API directly
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
        }

        with open(temp_filename, "rb") as audio_file:
            files = {
                "file": (
                    os.path.basename(temp_filename),
                    audio_file,
                    f"audio/{suffix[1:]}",
                ),
            }
            data = {
                "model": "whisper-large-v3-turbo",
                "response_format": "verbose_json",
            }

            response = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers=headers,
                files=files,
                data=data,
            )

            if response.status_code != 200:
                raise Exception(f"Error from Groq API: {response.text}")

            transcription = response.json()

        # Clean up the temporary file
        os.unlink(temp_filename)

        return transcription.get("text", "")

    except Exception as e:
        logger.error(f"Error processing audio file: {e}")
        raise


@whitelist_only
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle voice messages and audio files."""
    # Clear any existing conversation context when receiving new media
    context.user_data.clear()

    media = update.message.voice or update.message.audio
    if not media:
        await update.message.reply_text("No audio detected.")
        return

    processing_message = await update.message.reply_text("Processing audio...")

    try:
        # Transcribe the audio
        transcribed_text = await process_audio_file(media, context)

        # Capture caption if available
        caption = update.message.caption or ""

        # Store the transcription and caption in user_data for future questions
        context.user_data["transcribed_text"] = transcribed_text
        context.user_data["caption"] = caption

        # If the transcription is too short, just send it back as-is
        if len(transcribed_text) < 100:
            await processing_message.edit_text(f"Transcription: {transcribed_text}")
            return

        # Generate a summary using Groq
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert summarizer for transcribed audio files. Your task is to distill the key point(s) of the transcription into a single brief summary of 1-2 sentences. Always respond in the same language as the transcribed text. Output only the summary itself — no labels, no preamble, no closing remarks.",
                },
                {"role": "user", "content": f"Transcription:\n{transcribed_text}"},
            ],
            max_tokens=8192,
        )

        summary = response.choices[0].message.content
        await processing_message.edit_text(f"Summary: {summary}")

    except Exception as e:
        logger.error(f"Error handling audio: {e}")
        await processing_message.edit_text(f"Sorry, I encountered an error: {str(e)}")


@whitelist_only
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages as questions about transcribed content."""
    # Check if we have a stored transcription for this user
    if "transcribed_text" not in context.user_data:
        await update.message.reply_text(
            "Please send me a voice message or an audio file first, so I have content to discuss."
        )
        return

    # Get the user's question
    question = update.message.text
    transcribed_text = context.user_data.get("transcribed_text", "")
    caption = context.user_data.get("caption", "")

    try:
        # Send "Thinking" message and save the message reference for editing later
        thinking_message = await update.message.reply_text(
            "Thinking about your question..."
        )

        # Prepare context for the AI
        context_text = ""
        if caption:
            context_text += f'Caption: "{caption}"\n\n'
        context_text += f'Transcription: "{transcribed_text}"'

        # Generate an answer using Groq
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise Q&A assistant. You have been given a transcript of an audio message, and optionally a caption that accompanied it. Answer the user's question using only the information present in the provided transcript and caption — do not speculate or add outside knowledge. If the answer cannot be determined from the available content, say so explicitly. Be concise and direct. Always respond in the same language as the user's question.",
                },
                {
                    "role": "user",
                    "content": f"Available information:\n{context_text}\n\nQuestion: {question}",
                },
            ],
            max_tokens=8192,
        )

        answer = response.choices[0].message.content

        # Edit the "Thinking" message with the answer instead of sending a new message
        await thinking_message.edit_text(answer)

    except Exception as e:
        logger.error(f"Error handling question: {e}")
        await update.message.reply_text(f"Sorry, I encountered an error: {str(e)}")


def main() -> None:
    """Start the bot."""
    # Ensure .env file exists with proper settings
    ensure_env_file()

    # Create the Application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("whitelist", whitelist_command))
    application.add_handler(
        CommandHandler("toggle_whitelist", toggle_whitelist_command)
    )
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_media))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )

    # Run the bot until the user presses Ctrl-C
    application.run_polling()


if __name__ == "__main__":
    main()
