#!/usr/bin/env python3
import os
import logging
import datetime
from datetime import timezone
from pathlib import Path
import boto3
from podgen import Podcast, Episode, Media, Person
from dotenv import load_dotenv
import xml.etree.ElementTree as ET
from botocore.exceptions import NoCredentialsError, ClientError

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

        # Try to download existing feed from S3
        existing_episodes = []
        try:
            s3_client.download_file(s3_bucket, "rss/feed.xml", str(tmp_feed_path))
            logger.info("Downloaded existing RSS feed from S3")

            # Parse existing feed to extract episodes
            existing_episodes = parse_existing_episodes(tmp_feed_path)
            logger.info(f"Found {len(existing_episodes)} existing episodes")

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.info("No existing RSS feed found, creating new one")
            else:
                logger.warning(f"Error downloading existing feed: {e}")
        except Exception as e:
            logger.warning(f"Error parsing existing feed: {e}")

        # Create new podcast object
        podcast = Podcast(
            name=podcast_title,
            website=feed_url,
            description=f"Daily summaries of the latest papers in AI",
            explicit=False,
            authors=[Person(author_name)],
            language="en",
        )

        # Add existing episodes back to podcast
        for episode in existing_episodes:
            podcast.episodes.append(episode)

        # Parse the date
        pub_date = (
            datetime.datetime.strptime(episode_date, "%Y-%m-%d")
            .replace(hour=8, minute=0, second=0)
            .replace(tzinfo=timezone.utc)
        )

        # Create a new episode
        new_episode = Episode(
            title=f"Episode {episode_date}",
            media=Media(audio_url, size=size_bytes, type="audio/mpeg"),
            summary=f"Paper summaries for {episode_date}",
            publication_date=pub_date,
        )

        # Check if episode for this date already exists
        episode_exists = any(
            ep.title == f"Episode {episode_date}" for ep in podcast.episodes
        )

        if not episode_exists:
            # Add the new episode to the podcast
            podcast.episodes.append(new_episode)
            logger.info(f"Added new episode for {episode_date}")
        else:
            logger.info(f"Episode for {episode_date} already exists, skipping")

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


def parse_existing_episodes(feed_path):
    """
    Parse existing RSS feed and extract episodes as podgen Episode objects
    """
    episodes = []

    try:
        tree = ET.parse(feed_path)
        root = tree.getroot()

        # Find all item elements (episodes)
        for item in root.findall(".//item"):
            title_elem = item.find("title")
            description_elem = item.find("description")
            enclosure_elem = item.find("enclosure")
            pub_date_elem = item.find("pubDate")

            if title_elem is not None and enclosure_elem is not None:
                title = title_elem.text
                description = (
                    description_elem.text if description_elem is not None else ""
                )

                # Parse enclosure attributes
                audio_url = enclosure_elem.get("url")
                audio_size = int(enclosure_elem.get("length", 0))
                audio_type = enclosure_elem.get("type", "audio/mpeg")

                # Parse publication date
                pub_date = None
                if pub_date_elem is not None:
                    try:
                        pub_date = datetime.datetime.strptime(
                            pub_date_elem.text, "%a, %d %b %Y %H:%M:%S %z"
                        )
                    except ValueError:
                        # Try alternative date format
                        try:
                            pub_date = datetime.datetime.strptime(
                                pub_date_elem.text, "%a, %d %b %Y %H:%M:%S +0000"
                            ).replace(tzinfo=timezone.utc)
                        except ValueError:
                            logger.warning(
                                f"Could not parse date: {pub_date_elem.text}"
                            )

                # Create Episode object
                episode = Episode(
                    title=title,
                    media=Media(audio_url, size=audio_size, type=audio_type),
                    summary=description.replace("<![CDATA[", "").replace("]]>", ""),
                    publication_date=pub_date,
                )

                episodes.append(episode)

    except Exception as e:
        logger.error(f"Error parsing existing episodes: {e}")

    return episodes
