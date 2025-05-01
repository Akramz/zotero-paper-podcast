# Personalized Research Podcasts

A system that automatically delivers daily personalized Spotify Postcasts from academic papers you bookmarked in Zotero.

> **Note:** This project is currently a work in progress and in proof-of-concept stage.

## Overview

![System Components](static/components.png)

The repo covers the following:
1. Fetches papers you've bookmarked in Zotero,
2. Uses GPT-4o to generate podcast-style summaries.
3. Converts these summaries to speech using AI TTS.
4. Creates a podcast feed that can be subscribed to in Spotify.

Once set up, you will get daily paper summaries based on your recent paper bookmarks!

## Setup Instructions

### AWS Setup

1. Launch a `t3.small` (or similar) [EC2](https://console.aws.amazon.com/ec2/) instance running `Ubuntu 22.04`
2. Create an [IAM role](https://console.aws.amazon.com/iam/home#/roles) with S3 read/write access limited to your chosen bucket
3. Attach the IAM role to your EC2 instance.
4. Create an S3 bucket (e.g. papers-podcast-bucket) with the following structure:
   - `audio/` - Holds generated MP3 files
   - `rss/` - Holds the podcast feed.xml file
5. Configure bucket hosting:
   - Enable static website hosting on the bucket or serve through CloudFront.
   - Make audio/ and rss/feed.xml public-read. A simple bucket policy with "Allow": "s3:GetObject" for those paths is sufficient.
   - Verify https://<bucket-url>/rss/feed.xml loads in a browser.

### Local Environment Setup

Run these commands on your EC2 instance:

```bash
# Add 1GB of swap memory (Optional)
sudo dd if=/dev/zero of=/swapfile bs=1M count=1024
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Install packages
sudo apt update && sudo apt install -y python3-pip ffmpeg git poppler-utils

# Install mamba
wget -q https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash Miniforge3-Linux-x86_64.sh -b

# Install required packages
pip install -r requirements.txt
```

### Configuration

1. Copy `env.example` to `.env`
2. Fill in your API keys and configuration values:
   - OpenAI API key for GPT-4o and TTS
   - Zotero API key and user ID
   - S3 bucket name
   - Feed URL, author name, and podcast title

### Scheduling

Set up a cron job to run the script daily:

```bash
crontab -e
# Add this line (runs daily at 2:15 AM):
15 02 * * * /home/ubuntu/miniforge3/bin/python /home/ubuntu/repos/paper-speed-reader/main.py >> /var/log/papercast.log 2>&1
```

## Usage

1. Tag papers in Zotero with the "queue" tag
2. The system will process these papers at the scheduled time
3. After processing, papers are tagged as "processed"
4. Subscribe to your podcast feed in Spotify or any podcast app

### Adding the Feed to Spotify

1. Log in to Spotify for Podcasters → "Add or claim your podcast" → paste the FEED_URL.
2. Spotify polls the RSS every few hours; new episodes appear automatically.

### First Run Checklist

- Tag two papers in Zotero with "queue" to seed.
- Run python main.py manually and check S3 for the MP3 and updated feed.
- Add the feed to a podcast player and listen for audio quality issues.
- Tune voice, prompt length, or compression bitrate as desired.

## Security Notes

- Keep your `.env` file private and readable only by your user
- Rotate API keys periodically
- Enable automatic security updates on the VM (unattended-upgrades)
- Set up CloudWatch alarms for cost monitoring
- Configure OpenAI budget alerts

## TODO

- Use OpenAI assistant API to serve papers as attachments
- Ensure multi-paper jobs produce coherent podcast episodes
- Add support for conversation-based podcasts
- Add docs for Azure Cloud setup
