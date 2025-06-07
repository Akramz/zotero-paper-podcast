#!/usr/bin/env python3
import os
import logging
import anthropic
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_MESSAGE = """You are an expert summarizer of academic papers. 
Your task is to create engaging, podcast-friendly summaries that capture the essence of research papers.
Keep your responses clear, engaging and suitable for audio consumption.

Answer the following questions about the paper in a podcast-friendly tone:
- What is the title of the paper?
- What institution(s) the authors come from?
- What is the problem addressed by the paper?
- Why is it an interesting problem?
- What dataset(s) were used in the paper?
- What is the proposed solution?
- What metrics were used to measure performance and what were the results?
- What baselines were compared against?
- What limitations does the paper mention?

Don't start with an intro, dive straight into the paper. Keep it short and concise."""


def create_summary(pdf_url):
    """Create a summary of a paper using Claude with PDF URL."""
    logger.info(f"Creating paper summary for PDF: {pdf_url}")

    try:
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "document", "source": {"type": "url", "url": pdf_url}},
                        {"type": "text", "text": SYSTEM_MESSAGE},
                    ],
                }
            ],
        )

        summary = message.content[0].text.strip()
        logger.info("Summary created successfully")
        return summary

    except Exception as e:
        logger.error(f"Error creating summary: {str(e)}")
        raise
