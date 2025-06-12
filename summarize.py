#!/usr/bin/env python3
import os
import logging
import tempfile
from pathlib import Path
import requests
from PyPDF2 import PdfReader, PdfWriter
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


def _write_pages(reader: PdfReader, pages: int, out_path: Path) -> None:
    """Write the first `pages` pages from reader to out_path."""
    writer = PdfWriter()
    for i in range(pages):
        writer.add_page(reader.pages[i])
    with open(out_path, "wb") as f:
        writer.write(f)


def download_pdf(url: str) -> Path:
    """Download a PDF from a URL to a temporary path."""
    logger.info(f"Downloading PDF from {url}")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    tmp.write(chunk)
    finally:
        tmp.close()
    return Path(tmp.name)


def process_pdf(pdf_path: Path, max_pages: int = 100, max_size_mb: int = 32) -> Path:
    """Trim PDF pages to satisfy size and page count limits."""
    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)

    pages_to_keep = total_pages
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.close()
    out_path = Path(tmp.name)

    if total_pages > max_pages:
        pages_to_keep = max_pages
        logger.info(f"Trimming PDF from {total_pages} to {pages_to_keep} pages")

    _write_pages(reader, pages_to_keep, out_path)

    max_size_bytes = max_size_mb * 1024 * 1024
    while out_path.stat().st_size > max_size_bytes and pages_to_keep > 1:
        pages_to_keep -= 1
        logger.info(
            f"PDF size {out_path.stat().st_size} exceeds limit, trimming to {pages_to_keep} pages"
        )
        _write_pages(reader, pages_to_keep, out_path)

    return out_path


def create_summary(pdf_url: str) -> str:
    """Create a summary of a paper using Claude with a downloaded PDF."""
    logger.info(f"Creating paper summary for PDF: {pdf_url}")

    original_pdf = download_pdf(pdf_url)
    processed_pdf = process_pdf(original_pdf)

    try:
        with open(processed_pdf, "rb") as f:
            file_upload = client.beta.files.upload(
                file=(processed_pdf.name, f, "application/pdf")
            )

        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {"type": "file", "file_id": file_upload.id},
                        },
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
    finally:
        try:
            os.remove(original_pdf)
        except OSError:
            pass
        try:
            os.remove(processed_pdf)
        except OSError:
            pass

