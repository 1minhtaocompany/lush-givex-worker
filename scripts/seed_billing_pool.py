#!/usr/bin/env python3
"""Seed billing pool from CSV/TSV input file.

Usage:
    python scripts/seed_billing_pool.py --input profiles.csv --output billing_pool/
"""
import argparse
import csv
import logging
import sys
from pathlib import Path
from typing import List

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
_LOG = logging.getLogger(__name__)


def _detect_delimiter(sample: str) -> str:
    """Return tab if sample has more tabs than commas, else comma."""
    return "\t" if sample.count("\t") > sample.count(",") else ","


def _format_row(row: List[str]) -> str:
    """Format a CSV row as a pipe-delimited billing profile line."""
    values = [v.strip() for v in row]
    fields = list(values[:6])
    fields.append(values[6] if len(values) > 6 else "")
    fields.append(values[7] if len(values) > 7 else "")
    return "|".join(fields)


def _write_batch(output_dir: Path, batch_index: int, lines: List[str]) -> None:
    """Write a batch of profile lines to a numbered text file."""
    path = output_dir / ("billing_pool_%04d.txt" % batch_index)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    """Parse input CSV/TSV and write batched billing pool files."""
    parser = argparse.ArgumentParser(description="Seed billing pool from CSV/TSV")
    parser.add_argument("--input", required=True, help="Input CSV/TSV file path")
    parser.add_argument("--output", default="billing_pool/", help="Output directory")
    args = parser.parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output)
    if not input_path.exists():
        _LOG.error("Input file not found: %s", input_path)
        return 1
    output_dir.mkdir(parents=True, exist_ok=True)
    total_lines = 0
    accepted = 0
    files_written = 0
    batch_index = 1
    current_batch: List[str] = []
    with input_path.open("r", encoding="utf-8", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        reader = csv.reader(handle, delimiter=_detect_delimiter(sample))
        for row in reader:
            total_lines += 1
            if len(row) < 6:
                continue
            current_batch.append(_format_row(row))
            accepted += 1
            if len(current_batch) == 1000:
                _write_batch(output_dir, batch_index, current_batch)
                files_written += 1
                batch_index += 1
                current_batch = []
    if current_batch:
        _write_batch(output_dir, batch_index, current_batch)
        files_written += 1
    _LOG.info(
        "Completed: input=%d accepted=%d files=%d",
        total_lines, accepted, files_written,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
