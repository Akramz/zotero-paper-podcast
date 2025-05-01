#!/usr/bin/env python3
import os
import logging
import datetime
from datetime import timezone
from pathlib import Path
import boto3
from podgen import Podcast, Episode, Media, Person
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()


def update_feed(audio_url, size_bytes, episode_date):
    """
    Update the RSS feed with a new episode

    Args:
        audio_url (str): URL to the MP3 file
        size_bytes (int): Size of the MP3 file in bytes
        episode_date (str): Date string in YYYY-MM-DD format
    """
    logger.info(f"Updating RSS feed with episode for {episode_date}")

    # Get environment variables
    s3_bucket = os.getenv("S3_BUCKET")
    feed_url = os.getenv("FEED_URL")
    author_name = os.getenv("AUTHOR_NAME")
    podcast_title = os.getenv("PODCAST_TITLE")

    if not all([s3_bucket, feed_url, author_name, podcast_title]):
        logger.error("Missing required environment variables for RSS feed")
        raise ValueError("Missing required environment variables for RSS feed")

    try:
        # Create a temporary file for the feed
        tmp_feed_path = Path("/tmp/feed.xml")
        s3_client = boto3.client("s3")

        # Try to download existing feed
        try:
            s3_client.download_file(s3_bucket, "rss/feed.xml", str(tmp_feed_path))
            podcast = Podcast.load(str(tmp_feed_path))
            logger.info("Loaded existing RSS feed")
        except Exception:
            logger.info("Creating new RSS feed")
            # Create new podcast feed
            podcast = Podcast(
                name=podcast_title,
                website=feed_url,
                description=f"Daily summaries of the latest papers in geospatial machine learning",
                explicit=False,
                authors=[Person(author_name)],
                language="en",
            )

        # Parse the date
        pub_date = (
            datetime.datetime.strptime(episode_date, "%Y-%m-%d")
            .replace(hour=8, minute=0, second=0)
            .replace(tzinfo=timezone.utc)
        )

        # Create a new episode
        episode = Episode(
            title=f"Episode {episode_date}",
            media=Media(audio_url, size=size_bytes, type="audio/mpeg"),
            summary=f"Paper summaries for {episode_date}",
            publication_date=pub_date,
        )

        # Add the episode to the podcast
        podcast.episodes.append(episode)

        # Save the updated feed locally
        podcast.rss_file(str(tmp_feed_path), minimize=False)

        # Upload to S3
        s3_client.upload_file(
            str(tmp_feed_path),
            s3_bucket,
            "rss/feed.xml",
            ExtraArgs={"ContentType": "application/rss+xml", "ACL": "public-read"},
        )

        logger.info(
            f"RSS feed updated successfully with {len(podcast.episodes)} episodes"
        )

        return feed_url

    except Exception as e:
        logger.error(f"Error updating RSS feed: {str(e)}")
        raise
