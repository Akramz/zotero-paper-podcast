#!/usr/bin/env python3
import os
import logging
from openai import OpenAI
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """You are an expert summarizer of academic papers, particularly in geospatial machine learning. 
Your task is to create engaging, podcast-friendly summaries that capture the essence of research papers.
Keep your responses clear, engaging and suitable for audio consumption."""

USER_PROMPT_TEMPLATE = """Answer the following questions about the paper in a podcast-friendly tone:
1. What is the title of the paper?
2. Which institution the authors come from and who is the first author?
3. What is the problem addressed by the paper?
4. Why is it an interesting problem?
5. What dataset(s) were used in the paper?
6. What is the proposed solution?
7. What is novel about the solution?
8. What baselines were compared against?
9. What was achieved by the solution?
10. What comes next?

The paper text has been truncated to fit within token limits. Focus on extracting information from the available content.

Paper content below:
{paper_text}"""


def truncate_text(text, max_chars=4000):  # 40000 (more capacity if you want)
    """Truncate text to approximately max_chars."""
    if len(text) <= max_chars:
        return text

    logger.info(f"Truncating paper from {len(text)} to {max_chars} characters")
    return text[:max_chars]


def create_summary(paper_text, max_chars=40000):
    """Create a summary of a paper using GPT-4o."""
    logger.info("Creating paper summary")

    # Truncate text to avoid token limit errors
    truncated_text = truncate_text(paper_text, max_chars)

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": USER_PROMPT_TEMPLATE.format(paper_text=truncated_text),
                },
            ],
            temperature=0.3,
            max_tokens=800,
        )

        summary = response.choices[0].message.content.strip()
        token_usage = response.usage.total_tokens
        logger.info(f"Summary created successfully. Token usage: {token_usage}")

        return summary

    except Exception as e:
        logger.error(f"Error creating summary: {str(e)}")
        raise
