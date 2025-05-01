#!/usr/bin/env python3
import os
import logging
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def create_audio(text, output_path):
    """
    Convert text to speech using OpenAI's TTS API

    Args:
        text (str): The text to convert to speech
        output_path (Path): Path where the MP3 file will be saved
    """
    logger.info(f"Creating audio file at {output_path}")

    try:
        # Ensure the output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Call the OpenAI TTS API
        response = client.audio.speech.create(
            model="tts-1",
            voice="alloy",  # Options: alloy, echo, fable, onyx, nova, shimmer
            input=text,
        )

        # Save the audio file
        response.stream_to_file(str(output_path))

        file_size = output_path.stat().st_size
        duration_estimate = (
            file_size / 1024 / 25
        )  # Rough estimate: ~25KB per second of audio

        logger.info(
            f"Audio created successfully. Size: {file_size/1024:.2f}KB, "
            f"Estimated duration: {duration_estimate:.2f} seconds"
        )

        return output_path

    except Exception as e:
        logger.error(f"Error creating audio: {str(e)}")
        raise
