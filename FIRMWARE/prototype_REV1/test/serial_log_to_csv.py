from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


MQ_KEYS = ["2", "3", "4", "5", "8", "9", "135", "255"]
BME_KEYS = ["temperature", "pressure", "approx_altitude", "humidity"]

MQ_PATTERN = re.compile(r">?MQ\s*(\d+)\s*:\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
TEMP_PATTERN = re.compile(r">?Temperature\s*:\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
PRESSURE_PATTERN = re.compile(r">?Pressure\s*:\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
ALT_PATTERN = re.compile(r">?Approx_altitude\s*:\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
HUMIDITY_PATTERN = re.compile(r">?Humidity\s*:\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)


def build_row(sample_number: int, sample_data: dict[str, float | int | None]) -> dict[str, float | int | None]:
    row: dict[str, float | int | None] = {"sample_number": sample_number}
    for key in MQ_KEYS:
        row[f"mq_{key}"] = sample_data.get(f"mq_{key}")
    for key in BME_KEYS:
        row[key] = sample_data.get(key)
    return row


def parse_log_to_rows(text: str) -> list[dict[str, float | int | None]]:
    rows: list[dict[str, float | int | None]] = []
    current: dict[str, float | int | None] = {}
    sample_number = 0

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        mq_match = MQ_PATTERN.search(line)
        if mq_match:
            mq_id = mq_match.group(1)
            raw_value = mq_match.group(2)

            # Start a new sample when a new MQ2 arrives and current has data.
            if mq_id == "2" and current:
                sample_number += 1
                rows.append(build_row(sample_number, current))
                current = {}

            key = f"mq_{mq_id}"
            if key in {f"mq_{k}" for k in MQ_KEYS}:
                if "." in raw_value:
                    current[key] = float(raw_value)
                else:
                    current[key] = int(raw_value)
            continue

        temp_match = TEMP_PATTERN.search(line)
        if temp_match:
            current["temperature"] = float(temp_match.group(1))
            continue

        pressure_match = PRESSURE_PATTERN.search(line)
        if pressure_match:
            current["pressure"] = float(pressure_match.group(1))
            continue

        altitude_match = ALT_PATTERN.search(line)
        if altitude_match:
            current["approx_altitude"] = float(altitude_match.group(1))
            continue

        humidity_match = HUMIDITY_PATTERN.search(line)
        if humidity_match:
            current["humidity"] = float(humidity_match.group(1))
            continue

    if current:
        sample_number += 1
        rows.append(build_row(sample_number, current))

    return rows


def write_rows_to_csv(rows: list[dict[str, float | int | None]], output_path: Path) -> None:
    fieldnames = [
        "sample_number",
        "mq_2",
        "mq_3",
        "mq_4",
        "mq_5",
        "mq_8",
        "mq_9",
        "mq_135",
        "mq_255",
        "temperature",
        "pressure",
        "approx_altitude",
        "humidity",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert ESP32 serial log text (MQ + BME280) into CSV samples."
    )
    parser.add_argument("input", type=Path, help="Path to input .txt log file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Path to output CSV (default: same name as input with .csv extension)",
    )
    args = parser.parse_args()

    input_path = args.input
    output_path = args.output if args.output else input_path.with_suffix(".csv")

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    text = input_path.read_text(encoding="utf-8", errors="replace")
    rows = parse_log_to_rows(text)
    write_rows_to_csv(rows, output_path)

    print(f"Wrote {len(rows)} samples to {output_path}")


if __name__ == "__main__":
    main()
