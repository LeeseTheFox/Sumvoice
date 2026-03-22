#!/usr/bin/env python
import os
import tempfile
import logging
import requests
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message
from groq import Groq

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

# Initialize Pyrogram client
app = Client(
    "sumvoice_userbot",
    api_id=API_ID,
    api_hash=API_HASH,
)

async def process_audio_file(audio_file_path) -> str:
    """Process an audio file and return the transcription."""
    try:
        # Determine file extension
        file_ext = os.path.splitext(audio_file_path)[1]
        if not file_ext:
            file_ext = '.ogg'  # Default extension for voice messages
            
        # Transcribe using Groq API directly
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
        }
        
        with open(audio_file_path, "rb") as audio_file:
            files = {
                "file": (os.path.basename(audio_file_path), audio_file, f"audio/{file_ext[1:]}"),
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
        await message.edit_text("Error: You must reply to a voice message or audio file.")
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
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": "You are a concise summarizer. Provide very brief summaries (1-2 sentences) in english, russian, or ukrainian language, depending on the input text. If the input text is not in english, russian, or ukrainian, then your response must be in english. Your response must contain only the summary, no other text."},
                {"role": "user", "content": f"Summarize this in 1-2 sentences, either in english, russian, or ukrainian: {transcribed_text}"}
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