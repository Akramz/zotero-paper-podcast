import os
from pathlib import Path

import pytest
from PyPDF2 import PdfReader

from summarize import download_pdf, process_pdf

PDF_URLS = [
    # Full Deep Learning book, >1000 pages and ~40 MB
    "https://arxiv.org/pdf/2106.11342.pdf",
    # A long survey paper (~106 pages)
    "https://arxiv.org/pdf/2105.05208.pdf",
    # Another extensive survey (~191 pages)
    "https://arxiv.org/pdf/1612.09375.pdf",
]


@pytest.mark.parametrize("url", PDF_URLS)
def test_pdf_processed_within_limits(url):
    original = download_pdf(url)
    try:
        reader_original = PdfReader(str(original))
        original_size = original.stat().st_size
        original_pages = len(reader_original.pages)
        assert original_pages > 100 or original_size > 32 * 1024 * 1024

        processed = process_pdf(original)
        reader_processed = PdfReader(str(processed))
        processed_size = processed.stat().st_size
        processed_pages = len(reader_processed.pages)

        assert processed_pages <= 100
        assert processed_size < 32 * 1024 * 1024
    finally:
        for path in [original, locals().get("processed")]:
            if path and isinstance(path, Path) and path.exists():
                os.remove(path)

