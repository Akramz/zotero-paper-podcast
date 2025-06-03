#!/usr/bin/env python3
import os
import logging
import subprocess
import tempfile
from pathlib import Path
import boto3
import requests
from pyzotero import zotero
from pydub import AudioSegment
from dotenv import load_dotenv

# Add homebrew bin to PATH for cronjob compatibility
os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ.get("PATH", "")

logger = logging.getLogger(__name__)

load_dotenv()


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


def download_zotero_pdf(item, output_path):
    """Download a PDF file from a Zotero item"""
    logger.info(f"Downloading PDF for item {item.get('key')}")

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

        # Check if this is an external URL
        if link_mode == "imported_url" and pdf_item["data"].get("url"):
            # For externally linked PDFs, download directly from the URL
            pdf_url = pdf_item["data"]["url"]

            # Check if URL is from arxiv
            if "arxiv" not in pdf_url.lower():
                logger.info(f"Skipping non-arxiv URL: {pdf_url}")
                raise ValueError(f"Not an arxiv URL: {pdf_url}")

            logger.info(f"Downloading PDF from external URL: {pdf_url}")

            try:
                response = requests.get(pdf_url, stream=True, timeout=10)
                response.raise_for_status()

                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
            except requests.exceptions.Timeout:
                logger.error(f"Timeout downloading PDF from {pdf_url}")
                raise TimeoutError(f"Download timeout for {pdf_url}")
        else:
            # For Zotero-stored PDFs, check if original URL is from arxiv
            url = pdf_item["data"].get("url", "")
            if not url or "arxiv" not in url.lower():
                logger.info(f"Skipping non-arxiv or missing URL: {url}")
                raise ValueError(f"Not an arxiv URL or URL missing")

            # Try using dump function
            pdf_key = pdf_item["key"]
            try:
                # Try using dump function
                zot.dump(
                    pdf_key, os.path.basename(output_path), os.path.dirname(output_path)
                )
            except Exception as dump_error:
                logger.warning(f"Could not download using dump: {str(dump_error)}")

                # Fallback to manual file download
                try:
                    # Get the file download URL
                    file_url = (
                        f"https://api.zotero.org/users/{user_id}/items/{pdf_key}/file"
                    )
                    headers = {"Zotero-API-Key": api_key}

                    try:
                        response = requests.get(
                            file_url, headers=headers, allow_redirects=True, timeout=10
                        )
                        response.raise_for_status()

                        with open(output_path, "wb") as f:
                            f.write(response.content)
                    except requests.exceptions.Timeout:
                        logger.error(f"Timeout downloading PDF from {file_url}")
                        raise TimeoutError(f"Download timeout for {file_url}")
                except Exception as file_error:
                    logger.error(
                        f"All download attempts failed. Last error: {str(file_error)}"
                    )
                    raise

        logger.info(f"PDF downloaded successfully to {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Error downloading PDF: {str(e)}")
        raise


def extract_text_from_pdf(pdf_path):
    """Extract text content from a PDF file using pdftotext"""
    logger.info(f"Extracting text from PDF: {pdf_path}")

    try:
        # Create a temporary file for the text output
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp_file:
            tmp_txt_path = tmp_file.name

        # Use pdftotext (from poppler-utils) to extract text
        subprocess.run(
            ["/opt/homebrew/bin/pdftotext", "-layout", str(pdf_path), tmp_txt_path],
            check=True,
        )

        # Read the text file
        with open(tmp_txt_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()

        # Clean up
        os.unlink(tmp_txt_path)

        text_length = len(text)
        logger.info(f"Extracted {text_length} characters from PDF")

        return text

    except subprocess.CalledProcessError as e:
        logger.error(f"Error running pdftotext: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {str(e)}")
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
