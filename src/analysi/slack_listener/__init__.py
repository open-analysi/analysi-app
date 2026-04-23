"""Slack listener for HITL interactive payloads.

Receives Slack Socket Mode events (button clicks on HITL questions),
matches them to pending questions in the database, records answers,
and emits ``human:responded`` control events to resume paused workflows.

Run as a standalone process::

    python -m analysi.slack_listener
"""
