from __future__ import annotations

import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings


class OCRServiceError(Exception):
    pass


@dataclass(frozen=True)
class OCRGuess:
    query: str
    card_number: str = ""


class OCRClient:
    def __init__(self, service_url: str | None = None) -> None:
        self.service_url = (service_url or settings.OCR_SERVICE_URL).rstrip("/")

    def extract_text(self, image_path: str) -> str:
        url = f"{self.service_url}/ocr"
        data = Path(image_path).read_bytes()
        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/octet-stream"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as error:
            raise OCRServiceError(f"OCR service request failed: {error}") from error


def guess_from_ocr_text(text: str) -> OCRGuess:
    lines = [
        _clean_line(line)
        for line in text.splitlines()
        if _clean_line(line)
    ]
    card_number = ""
    for line in lines:
        match = re.search(r"\b([A-Z]{0,4}\s*)?(\d{1,3})\s*/\s*(\d{1,3})\b", line, flags=re.IGNORECASE)
        if match:
            card_number = match.group(2)
            break

    name_candidates = [
        line for line in lines
        if not re.search(r"\d+\s*/\s*\d+", line) and len(line) >= 3
    ]
    query = name_candidates[0] if name_candidates else (lines[0] if lines else "")
    return OCRGuess(query=query[:80], card_number=card_number)


def run_local_tesseract(image_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".image") as image_file:
        image_file.write(image_bytes)
        image_file.flush()
        try:
            result = subprocess.run(
                ["tesseract", image_file.name, "stdout", "--psm", "6"],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as error:
            raise OCRServiceError(f"Tesseract failed: {error}") from error
    return result.stdout


def _clean_line(line: str) -> str:
    return " ".join(line.strip().split())

