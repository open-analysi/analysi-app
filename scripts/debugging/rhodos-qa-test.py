#!/usr/bin/env python3
"""Rhodos (Project Rhodes) chatbot QA testing helper.

Creates conversations, sends questions, collects streaming responses,
and outputs structured results for comparison with ground truth.

Usage:
  python3 scripts/debugging/rhodos-qa-test.py "How many tasks are there?"
  python3 scripts/debugging/rhodos-qa-test.py --conversation <id> "Follow-up question"
"""

import argparse
import json
import sys

import httpx

API_BASE = "http://localhost:8001/v1/default"
API_KEY = "dev-owner-api-key-change-in-production"
HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json",
}


def create_conversation(page_context: dict | None = None) -> str:
    """Create a new chat conversation, return its ID."""
    body = {}
    if page_context:
        body["page_context"] = page_context
    resp = httpx.post(
        f"{API_BASE}/chat/conversations", json=body, headers=HEADERS, timeout=10
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    return data["id"]


def send_message(
    conversation_id: str, content: str, page_context: dict | None = None
) -> dict:
    """Send a message and collect the full streaming response.

    Returns dict with keys: text, tool_calls, error, raw_events
    """
    body: dict = {"content": content}
    if page_context:
        body["page_context"] = page_context

    result = {
        "text": "",
        "tool_calls": [],
        "error": None,
        "raw_events": [],
    }

    current_tool: dict | None = None

    with httpx.stream(
        "POST",
        f"{API_BASE}/chat/conversations/{conversation_id}/messages",
        json=body,
        headers=HEADERS,
        timeout=120,
    ) as stream:
        buffer = ""
        for chunk in stream.iter_text():
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        result["raw_events"].append(event)
                        etype = event.get("type", "")
                        if etype == "text_delta":
                            result["text"] += event.get("content", "")
                        elif etype == "tool_call_start":
                            current_tool = {
                                "tool": event.get("tool", "unknown"),
                                "input": event.get("input", {}),
                                "output": None,
                            }
                        elif etype == "tool_call_end":
                            if current_tool:
                                current_tool["output"] = event.get("output")
                                result["tool_calls"].append(current_tool)
                                current_tool = None
                        elif etype == "error":
                            result["error"] = event.get("message", "Unknown error")
                    except json.JSONDecodeError:
                        pass

    return result


def main():
    parser = argparse.ArgumentParser(description="Rhodos chatbot QA tester")
    parser.add_argument("question", help="Question to ask Rhodos")
    parser.add_argument(
        "--conversation", "-c", help="Existing conversation ID (skip creation)"
    )
    parser.add_argument(
        "--page", "-p", default=None, help="Page context route (e.g., /tasks)"
    )
    parser.add_argument("--raw", action="store_true", help="Show raw events")
    args = parser.parse_args()

    page_context = {"route": args.page} if args.page else None

    # Create or reuse conversation
    if args.conversation:
        conv_id = args.conversation
        print(f"Using conversation: {conv_id}")
    else:
        conv_id = create_conversation(page_context)
        print(f"Created conversation: {conv_id}")

    print(f"Q: {args.question}")
    print("---")

    # Send and collect response
    result = send_message(conv_id, args.question, page_context)

    if result["error"]:
        print(f"ERROR: {result['error']}")
        sys.exit(1)

    # Show tool calls
    if result["tool_calls"]:
        print(f"Tools used ({len(result['tool_calls'])}):")
        for tc in result["tool_calls"]:
            print(f"  - {tc['tool']}({json.dumps(tc['input'], default=str)[:200]})")
        print("---")

    # Show response
    print(f"A: {result['text']}")
    print(f"\nConversation ID: {conv_id}")

    if args.raw:
        print("\n--- Raw Events ---")
        for ev in result["raw_events"]:
            if ev.get("type") != "text_delta":
                print(json.dumps(ev, indent=2, default=str)[:500])


if __name__ == "__main__":
    main()
