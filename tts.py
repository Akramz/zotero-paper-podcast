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

        # Split text into chunks of 4000 characters (OpenAI TTS limit)
        max_chunk_size = 4000
        chunks = []

        # Split by sentences to avoid cutting off mid-sentence
        sentences = text.split(". ")
        current_chunk = ""

        for sentence in sentences:
            # Add sentence with period back
            sentence_with_period = (
                sentence + ". " if not sentence.endswith(".") else sentence + " "
            )

            if len(current_chunk + sentence_with_period) <= max_chunk_size:
                current_chunk += sentence_with_period
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence_with_period

        # Add the last chunk
        if current_chunk:
            chunks.append(current_chunk.strip())

        logger.info(f"Split text into {len(chunks)} chunks for TTS processing")
        temp_files = []

        # Process each chunk
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue

            temp_path = output_path.parent / f"chunk_{i}.mp3"
            logger.info(f"Processing chunk {i+1}/{len(chunks)}")

            response = client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=chunk,
            )
            response.stream_to_file(str(temp_path))
            temp_files.append(temp_path)

        # If only one chunk, just rename it
        if len(temp_files) == 1:
            temp_files[0].rename(output_path)
        else:
            # Concatenate all chunks
            from utils import concatenate_audio_files

            concatenate_audio_files(temp_files, output_path)

        # Clean up temp files
        for temp_file in temp_files:
            if temp_file.exists():
                temp_file.unlink()

        file_size = output_path.stat().st_size
        duration_estimate = file_size / 1024 / 25

        logger.info(
            f"Audio created successfully. Size: {file_size/1024:.2f}KB, "
            f"Estimated duration: {duration_estimate:.2f} seconds"
        )

        return output_path

    except Exception as e:
        logger.error(f"Error creating audio: {str(e)}")
        raise
