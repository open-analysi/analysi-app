"""CLI tool for alert normalization."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .base import BaseNormalizer
from .splunk import SplunkNotableNormalizer


def parse_args():
    """Parse command line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(description="Normalize alert data between formats")

    parser.add_argument("input_file", help="Input file containing alerts (JSON format)")

    parser.add_argument(
        "-o", "--output", help="Output file (default: stdout)", default=None
    )

    parser.add_argument(
        "-f",
        "--format",
        choices=["json", "pretty"],
        default="json",
        help="Output format",
    )

    parser.add_argument(
        "-t",
        "--type",
        choices=["splunk"],
        default="splunk",
        help="Alert source type",
    )

    parser.add_argument(
        "-r",
        "--reverse",
        action="store_true",
        help="Reverse normalization (AlertCreate to source format)",
    )

    return parser.parse_args()


def normalize_file(
    file_path: str, alert_type: str = "splunk", reverse: bool = False
) -> list[Any]:
    """Process input file and normalize alerts.

    Args:
        file_path: Path to input file
        alert_type: Type of alerts in file
        reverse: Whether to reverse normalize

    Returns:
        List of normalized alerts (Pydantic models or dicts)
    """
    # Read input file
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Get normalizer
    normalizer: BaseNormalizer
    if alert_type == "splunk":
        normalizer = SplunkNotableNormalizer()
    else:
        raise ValueError(f"Unsupported alert type: {alert_type}")

    # JSON format
    with open(path) as f:
        data = json.load(f)

    # Ensure data is a list
    if not isinstance(data, list):
        data = [data]

    # Process each alert
    results = []
    for alert in data:
        try:
            normalized: Any
            if reverse:
                normalized = normalizer.from_alertcreate(alert)
            else:
                normalized = normalizer.to_alertcreate(alert)
            results.append(normalized)
        except Exception as e:
            print(f"Error normalizing alert: {e}", file=sys.stderr)
            continue

    return results


def output_result(results: list[Any], format: str = "json") -> str:
    """Format and output results.

    Args:
        results: List of normalized alerts (Pydantic models or dicts)
        format: Output format

    Returns:
        Formatted string
    """
    # Convert Pydantic models to dicts for output
    dict_results = []
    for result in results:
        if hasattr(result, "model_dump"):
            # It's a Pydantic model
            dict_results.append(result.model_dump(exclude_none=True))
        else:
            # It's already a dict
            dict_results.append(result)

    if format == "json":
        return json.dumps(dict_results, indent=2, default=str)
    if format == "pretty":
        output = []
        for i, alert in enumerate(dict_results, 1):
            output.append(f"Alert {i}:")
            for key, value in alert.items():
                if key == "raw_alert":
                    output.append(f"  {key}: <preserved>")
                else:
                    output.append(f"  {key}: {value}")
            output.append("")
        return "\n".join(output)
    return str(dict_results)


def main():
    """CLI entry point."""
    args = parse_args()

    try:
        # Normalize alerts
        results = normalize_file(
            args.input_file, alert_type=args.type, reverse=args.reverse
        )

        # Format output
        output = output_result(results, format=args.format)

        # Write output
        if args.output:
            with open(args.output, "w") as f:
                f.write(output)
            print(f"Wrote {len(results)} alerts to {args.output}")
        else:
            print(output)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
