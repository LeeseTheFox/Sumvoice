#!/usr/bin/env python
import logging
import os
import tempfile

import requests
from dotenv import load_dotenv
from groq import Groq
from pyrogram import Client, filters
from pyrogram.types import Message

# Session files are stored in data/ for persistence across redeployments
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get tokens from environment variables
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
API_ID = int(os.getenv("PYROGRAM_API_ID", "0"))
API_HASH = os.getenv("PYROGRAM_API_HASH")

# Initialize Groq client
groq_client = Groq(api_key=GROQ_API_KEY)

# Initialize Pyrogram client (session file stored in data/ for persistence)
app = Client(
    os.path.join(DATA_DIR, "sumvoice_userbot"),
    api_id=API_ID,
    api_hash=API_HASH,
)


async def process_audio_file(audio_file_path) -> str:
    """Process an audio file and return the transcription."""
    try:
        # Determine file extension
        file_ext = os.path.splitext(audio_file_path)[1]
        if not file_ext:
            file_ext = ".ogg"  # Default extension for voice messages

        # Transcribe using Groq API directly
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
        }

        with open(audio_file_path, "rb") as audio_file:
            files = {
                "file": (
                    os.path.basename(audio_file_path),
                    audio_file,
                    f"audio/{file_ext[1:]}",
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

        return transcription.get("text", "")

    except Exception as e:
        logger.error(f"Error processing audio file: {e}")
        raise


@app.on_message(filters.text & filters.regex(r"^\.sumvoice$") & filters.reply)
async def handle_sumvoice_command(pyrogram_client, message: Message):
    """Handle .sumvoice command when replying to voice messages or audio files."""
    # Get the replied message
    replied = message.reply_to_message

    # Check if the replied message contains a voice message or audio file
    if not (replied.voice or replied.audio):
        await message.edit_text(
            "Error: You must reply to a voice message or audio file."
        )
        return

    # Edit the original .sumvoice command message
    await message.edit_text("Processing audio...")

    try:
        # Download the voice message or audio file
        media = replied.voice or replied.audio
        file_path = await pyrogram_client.download_media(media)

        # Process the audio file
        transcribed_text = await process_audio_file(file_path)

        # Clean up the downloaded file
        os.remove(file_path)

        # If the transcription is too short, just send it back
        if len(transcribed_text) < 100:
            await message.edit_text(f"Transcription: {transcribed_text}")
            return

        # Generate a summary using Groq
        response = groq_client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert summarizer for transcribed voice messages. Your task is to distill the key point(s) of the transcription into a single brief summary of 1-2 sentences. Always respond in the same language as the transcribed text. Output only the summary itself \u2014 no labels, no preamble, no closing remarks.",
                },
                {"role": "user", "content": f"Transcription:\n{transcribed_text}"},
            ],
            max_tokens=8192,
        )

        summary = response.choices[0].message.content

        # Update the original command message with the summary
        await message.edit_text(f"AI summary: {summary}")

    except Exception as e:
        logger.error(f"Error handling voice message: {e}")
        await message.edit_text(f"Sorry, I encountered an error: {str(e)}")


if __name__ == "__main__":
    print("Sumvoice Userbot is starting...")
    app.run()
