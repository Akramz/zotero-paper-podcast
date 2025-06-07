#!/usr/bin/env python3
import os
import logging
from pathlib import Path
import boto3
import requests
from pyzotero import zotero
from pydub import AudioSegment
from openai import OpenAI
from dotenv import load_dotenv

# Add homebrew bin to PATH for cronjob compatibility
os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ.get("PATH", "")

logger = logging.getLogger(__name__)

load_dotenv()

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def get_queued_zotero_items():
    """Fetch items from Zotero with the 'queue' tag"""
    logger.info("Fetching queued items from Zotero")

    api_key = os.getenv("ZOTERO_API_KEY")
    user_id = os.getenv("ZOTERO_USER_ID")

    if not api_key or not user_id:
        logger.error("Missing Zotero API credentials")
        raise ValueError("Missing Zotero API credentials")

    try:
        zot = zotero.Zotero(user_id, "user", api_key)
        items = zot.items(tag="queue")
        logger.info(f"Found {len(items)} items with 'queue' tag")
        return items
    except Exception as e:
        logger.error(f"Error fetching Zotero items: {str(e)}")
        raise


def get_pdf_url(item):
    """Extract PDF URL from a Zotero item"""
    logger.info(f"Getting PDF URL for item {item.get('key')}")

    api_key = os.getenv("ZOTERO_API_KEY")
    user_id = os.getenv("ZOTERO_USER_ID")

    if not api_key or not user_id:
        logger.error("Missing Zotero API credentials")
        raise ValueError("Missing Zotero API credentials")

    try:
        zot = zotero.Zotero(user_id, "user", api_key)

        # Get child attachments
        children = zot.children(item["key"])
        pdf_items = [
            c for c in children if c["data"].get("contentType") == "application/pdf"
        ]

        if not pdf_items:
            logger.error(f"No PDF attachment found for item {item.get('key')}")
            raise ValueError(f"No PDF attachment found for item {item.get('key')}")

        # Get the first PDF
        pdf_item = pdf_items[0]
        link_mode = pdf_item["data"].get("linkMode")

        pdf_url = None

        # Check if this is an external URL
        if link_mode == "imported_url" and pdf_item["data"].get("url"):
            pdf_url = pdf_item["data"]["url"]
        else:
            # For Zotero-stored PDFs, check if original URL exists
            pdf_url = pdf_item["data"].get("url", "")

        if not pdf_url:
            logger.error(f"No URL found for PDF item {item.get('key')}")
            raise ValueError(f"No URL found for PDF item {item.get('key')}")

        # Convert arxiv abstract URLs to PDF URLs
        if "arxiv.org/abs/" in pdf_url:
            pdf_url = pdf_url.replace("/abs/", "/pdf/") + ".pdf"

        logger.info(f"Found PDF URL: {pdf_url}")
        return pdf_url

    except Exception as e:
        logger.error(f"Error getting PDF URL: {str(e)}")
        raise


def concatenate_audio_files(input_paths, output_path):
    """Concatenate multiple MP3 files into a single file"""
    logger.info(f"Concatenating {len(input_paths)} audio files")

    try:
        if not input_paths:
            raise ValueError("No input files provided")

        # Load the first file
        combined = AudioSegment.from_mp3(input_paths[0])

        # Add 1 second silence between segments
        silence = AudioSegment.silent(duration=1000)

        # Append the rest
        for path in input_paths[1:]:
            segment = AudioSegment.from_mp3(path)
            combined += silence + segment

        # Export the combined file
        combined.export(output_path, format="mp3")

        file_size = os.path.getsize(output_path)
        logger.info(
            f"Concatenated audio saved to {output_path} ({file_size/1024/1024:.2f} MB)"
        )

        return output_path

    except Exception as e:
        logger.error(f"Error concatenating audio: {str(e)}")
        raise


def upload_to_s3(file_path, bucket, key):
    """Upload a file to an S3 bucket"""
    logger.info(f"Uploading {file_path} to s3://{bucket}/{key}")

    try:
        s3_client = boto3.client("s3")
        s3_client.upload_file(
            str(file_path), bucket, key, ExtraArgs={"ACL": "public-read"}
        )
        logger.info("Upload successful")
        return f"https://{bucket}.s3.amazonaws.com/{key}"

    except Exception as e:
        logger.error(f"Error uploading to S3: {str(e)}")
        raise


def mark_item_as_processed(item):
    """Mark a Zotero item as processed by removing 'queue' tag and adding 'processed' tag"""
    logger.info(f"Marking item {item.get('key')} as processed")

    api_key = os.getenv("ZOTERO_API_KEY")
    user_id = os.getenv("ZOTERO_USER_ID")

    if not api_key or not user_id:
        logger.error("Missing Zotero API credentials")
        raise ValueError("Missing Zotero API credentials")

    try:
        zot = zotero.Zotero(user_id, "user", api_key)

        # Get current tags
        tags = item["data"].get("tags", [])

        # Remove 'queue' tag
        tags = [tag for tag in tags if tag.get("tag") != "queue"]

        # Add 'processed' tag
        tags.append({"tag": "processed"})

        # Update the item
        item["data"]["tags"] = tags
        zot.update_item(item)

        logger.info(f"Item {item.get('key')} marked as processed")
        return True

    except Exception as e:
        logger.error(f"Error marking item as processed: {str(e)}")
        raise


def harmonize_summaries(paper_summaries):
    """Harmonize multiple paper summaries into a single podcast content using ChatGPT"""
    logger.info(f"Harmonizing {len(paper_summaries)} paper summaries")

    # Combine all summaries into a single prompt
    combined_summaries = "\n\n---\n\n".join(
        [f"Paper {i+1}:\n{summary}" for i, summary in enumerate(paper_summaries)]
    )

    prompt = f"""You are a podcast host creating an engaging daily AI research podcast. 
You have summaries of {len(paper_summaries)} research papers. Your task is to create a cohesive, engaging podcast script that flows naturally between papers.

IMPORTANT: The final script must be suitable for a 20-minute podcast episode (approximately 3200-3600 words maximum).

Here are the paper summaries:

{combined_summaries}

Create a podcast script that:
- Has a brief, engaging introduction to the episode (30 seconds)
- Flows smoothly between papers with natural transitions
- Maintains a conversational, enthusiastic tone throughout
- Remains scientific and technical, covering the original content for each paper.
- Is suitable for audio consumption (no visual elements)
- Stays within 20 minutes total listening time (~3200-3600 words)

Keep the content informative but concise. Focus on the most interesting and impactful aspects of each paper rather than covering every detail."""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert podcast host specializing in AI research. Create engaging, conversational content suitable for audio.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=4000,
            temperature=0.7,
        )

        harmonized_content = response.choices[0].message.content.strip()

        # Check word count and truncate if necessary
        word_count = len(harmonized_content.split())
        logger.info(f"Harmonized content has {word_count} words")

        if word_count > 3600:
            logger.warning(
                f"Content exceeds 3600 words ({word_count}), truncating to fit 20-minute limit"
            )
            words = harmonized_content.split()
            truncated_content = " ".join(words[:3600])
            # Try to end on a complete sentence
            last_period = truncated_content.rfind(".")
            if last_period > len(truncated_content) * 0.9:  # If period is in last 10%
                harmonized_content = truncated_content[: last_period + 1]
            else:
                harmonized_content = truncated_content + "..."
            logger.info(f"Content truncated to {len(harmonized_content.split())} words")

        logger.info("Successfully harmonized summaries into podcast content")
        return harmonized_content

    except Exception as e:
        logger.error(f"Error harmonizing summaries: {str(e)}")
        raise
