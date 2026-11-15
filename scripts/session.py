#!/usr/bin/env python3
"""Load, append, and reduce a local list of incident events."""

from datetime import datetime, timezone
import json
from pathlib import Path

from incident import apply_event, new_context
from transcriber import extract_transcript_facts


SPEECH_SOURCES = {"operator_report", "dispatcher_confirmed"}
LOCAL_STT_PROVIDER = "faster-whisper"


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_events(path):
    path = Path(path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a list of events")
    return data


def save_events(path, events):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(events, indent=2) + "\n", encoding="utf-8")


def next_event_id(events):
    number = len(events) + 1
    existing = {event["event_id"] for event in events}
    while f"evt_{number:03d}" in existing:
        number += 1
    return f"evt_{number:03d}"


def speech_event(
    session_id,
    event_id,
    transcript,
    source,
    observed_at,
    stt_provider,
    confidence=None,
):
    if source not in SPEECH_SOURCES:
        raise ValueError(f"unsupported speech source: {source}")
    text = transcript.strip()
    if not text:
        raise ValueError("transcript is empty")
    if len(text) > 2000:
        raise ValueError("transcript is longer than 2000 characters")

    extracted = extract_transcript_facts(text, source=source)
    payload = {
        "transcript": text,
        "stt_provider": stt_provider,
        "is_final": True,
        "facts": extracted["facts"],
        "unresolved": extracted["unresolved"],
    }
    if confidence is not None:
        payload["confidence"] = confidence
    return {
        "event_id": event_id,
        "session_id": session_id,
        "type": "speech_transcript",
        "source": source,
        "observed_at": observed_at,
        "received_at": observed_at,
        "payload": payload,
    }


def append_speech(
    path,
    transcript,
    source,
    session_id,
    stt_provider=LOCAL_STT_PROVIDER,
    confidence=None,
    observed_at=None,
):
    events = load_events(path)
    if events and events[0]["session_id"] != session_id:
        raise ValueError(
            f"{path} belongs to session {events[0]['session_id']}, not {session_id}"
        )
    event = speech_event(
        session_id,
        next_event_id(events),
        transcript,
        source,
        observed_at or utc_now(),
        stt_provider,
        confidence,
    )
    events.append(event)
    save_events(path, events)
    return events


def reduce_events(events):
    if not events:
        raise ValueError("session has no events")
    context = new_context(
        session_id=events[0]["session_id"],
        started_at=events[0]["observed_at"],
    )
    for event in events:
        context = apply_event(context, event)
    return context
