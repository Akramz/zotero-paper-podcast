#!/usr/bin/env python3
import os
import sys
import datetime
import tempfile
from pathlib import Path
import logging
from dotenv import load_dotenv
from pdb import set_trace
import summarize
import tts
import rss
import utils

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    load_dotenv()

    # Load environment variables
    zotero_api_key = os.getenv("ZOTERO_API_KEY")
    zotero_user_id = os.getenv("ZOTERO_USER_ID")
    s3_bucket = os.getenv("S3_BUCKET")

    if not all([zotero_api_key, zotero_user_id, s3_bucket]):
        logger.error("Missing required environment variables")
        sys.exit(1)

    # Get today's date for episode naming
    today = datetime.date.today().strftime("%Y-%m-%d")
    episode_filename = f"episode_{today}.mp3"

    # Create temp directory for processing
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Fetch queued items from Zotero
        queue_items = utils.get_queued_zotero_items()

        if not queue_items:
            logger.info("No papers in queue. Exiting.")
            return

        logger.info(f"Processing {len(queue_items)} papers")

        mp3_paths = []
        processed_items = []

        # Process each paper
        for item in queue_items:
            try:
                item_key = item["key"]
                logger.info(
                    f"Processing item {item_key}: {item.get('title', 'Unknown')}"
                )

                # Download PDF
                pdf_path = tmp_path / f"{item_key}.pdf"
                utils.download_zotero_pdf(item, pdf_path)

                # Summarize the paper
                paper_text = utils.extract_text_from_pdf(pdf_path)
                summary = summarize.create_summary(paper_text)

                # Convert to speech
                mp3_path = tmp_path / f"{item_key}.mp3"
                tts.create_audio(summary, mp3_path)

                mp3_paths.append(mp3_path)
                processed_items.append(item)

            except Exception as e:
                logger.error(
                    f"Error processing item {item.get('key', 'unknown')}: {str(e)}"
                )

        if not mp3_paths:
            logger.warning("No items were successfully processed")
            return

        # Concatenate all MP3s
        episode_path = tmp_path / episode_filename
        utils.concatenate_audio_files(mp3_paths, episode_path)

        # Upload to S3
        s3_audio_key = f"audio/{episode_filename}"
        utils.upload_to_s3(episode_path, s3_bucket, s3_audio_key)

        # Update RSS feed
        audio_url = f"https://{s3_bucket}.s3.amazonaws.com/{s3_audio_key}"
        audio_size = os.path.getsize(episode_path)
        rss.update_feed(audio_url, audio_size, today)

        # Mark items as processed in Zotero
        for item in processed_items:
            utils.mark_item_as_processed(item)

        logger.info(f"Successfully processed {len(processed_items)} papers")


if __name__ == "__main__":
    main()
