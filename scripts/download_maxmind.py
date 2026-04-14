#!/usr/bin/env python3
"""Download and bootstrap GeoLite2-City.mmdb from MaxMind."""
import hashlib
import io
import logging
import os
import sys
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
_log = logging.getLogger(__name__)

_BASE_URL = "https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City"


def _download_bytes(url: str) -> bytes:
    # nosec B310: URL is built from a fixed HTTPS MaxMind endpoint and controlled query params.
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def _parse_checksum(content: bytes) -> str:
    text = content.decode("utf-8").strip()
    if not text:
        raise ValueError("Empty checksum response")
    return text.split()[0]


def _extract_mmdb(archive_bytes: bytes) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile() or not member.name.endswith(".mmdb"):
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            return extracted.read()
    raise ValueError("No .mmdb file found in archive")


def main() -> int:
    license_key = os.getenv("MAXMIND_LICENSE_KEY")
    if not license_key:
        print("ERROR: MAXMIND_LICENSE_KEY environment variable is required.", file=sys.stderr)
        return 1

    encoded_key = urllib.parse.quote_plus(license_key)
    archive_url = f"{_BASE_URL}&license_key={encoded_key}&suffix=tar.gz"
    checksum_url = f"{_BASE_URL}&license_key={encoded_key}&suffix=tar.gz.sha256"

    try:
        archive_bytes = _download_bytes(archive_url)
        checksum_bytes = _download_bytes(checksum_url)
        expected_sha256 = _parse_checksum(checksum_bytes)
        actual_sha256 = hashlib.sha256(archive_bytes).hexdigest()
        if actual_sha256 != expected_sha256:
            _log.error("Checksum verification failed for MaxMind archive.")
            return 1

        mmdb_bytes = _extract_mmdb(archive_bytes)
    except (OSError, ValueError, tarfile.TarError) as exc:
        _log.error("Failed to download/extract MaxMind DB: %s", exc)
        return 1

    output_dir = Path("data")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "GeoLite2-City.mmdb"
    output_path.write_bytes(mmdb_bytes)
    _log.info("Saved %s (%d bytes)", output_path, output_path.stat().st_size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
