"""Utilities for parsing Cy script execution output in tests.

The Cy runtime (cy-language package) currently serializes return values using
Python's str(), producing repr format: {'key': 'value'} with single quotes.

A prodsec fix (commit dff19b2) replaced ast.literal_eval with json.loads in
task_execution.py, which correctly rejects Python repr. As a result, dict/list
outputs from Cy scripts arrive as strings in test assertions.

Once the Cy language outputs JSON natively, this helper becomes unnecessary
and can be replaced with plain json.loads().
"""

import ast
import json
from typing import Any


def parse_cy_output(output: Any) -> Any:
    """Parse Cy script output that may be JSON or Python repr format.

    Tries json.loads first (future-proof), falls back to ast.literal_eval
    for the current Python repr format from the Cy runtime.

    Handles double-wrapping: MCP adhoc execution returns a JSON string
    containing a Python repr string (e.g., '"{\\'key\\': \\'value\\'}"').
    """
    if not isinstance(output, str):
        return output
    try:
        parsed = json.loads(output)
        # If json.loads returned another string, it may be double-wrapped
        # (e.g., JSON-encoded Python repr). Try parsing the inner string too.
        if isinstance(parsed, str):
            return parse_cy_output(parsed)
        return parsed
    except (json.JSONDecodeError, ValueError):
        try:
            return ast.literal_eval(output)
        except (ValueError, SyntaxError):
            return output
