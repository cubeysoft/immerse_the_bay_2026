#!/usr/bin/env python3
"""Run the transcriber, reducer, and dispatcher formatter demonstration."""

import json
import sys
from pathlib import Path

from dispatcher import compose_summary
from incident import apply_event, new_context
from session import load_events, reduce_events
from transcriber import extract_transcript_facts


ROOT = Path(__file__).resolve().parents[1]


def _print_summary(title, summary):
    print(f"[{title}]")
    print(f"Session: {summary['session_id']}")
    print(
        f"Location ({summary['location']['resolution_basis']}): "
        f"{summary['location']['description'] or 'Unconfirmed'}"
    )
    print(f"Conflicts: {len(summary['conflicts'])}")
    print(f"Unknown fields: {', '.join(summary['unknown_fields']) or 'none'}")
    print("Transcript:")
    if summary["transcripts"]:
        for item in summary["transcripts"]:
            speaker = "Operator" if item["source"] == "operator_report" else "Dispatcher"
            print(f"  {speaker}: {item['text']}")
    else:
        print("  none")
    print(f"Spoken briefing: {summary['spoken_text']}")


def _operator_event(session_id, event_id, transcript, observed_at):
    extracted = extract_transcript_facts(transcript)
    return {
        "event_id": event_id,
        "session_id": session_id,
        "type": "speech_transcript",
        "source": extracted["source"],
        "observed_at": observed_at,
        "received_at": observed_at,
        "payload": {
            "transcript": transcript,
            "stt_provider": "meta_unity_ai_stt",
            "is_final": True,
            "facts": extracted["facts"],
            "unresolved": extracted["unresolved"],
        },
    }


def _demo_context():
    session_id = "sim_demo_adult_male"
    context = new_context(session_id=session_id)
    context = apply_event(
        context,
        {
            "event_id": "evt_help_01",
            "session_id": session_id,
            "type": "help_request",
            "source": "app",
            "observed_at": "2026-11-14T19:10:00Z",
            "received_at": "2026-11-14T19:10:00Z",
            "payload": {
                "facts": [
                    {"field": "incident.help_requested", "value": True}
                ]
            },
        },
    )
    context = apply_event(
        context,
        {
            "event_id": "evt_geo_01",
            "session_id": session_id,
            "type": "location_update",
            "source": "companion_phone",
            "observed_at": "2026-11-14T19:10:01Z",
            "received_at": "2026-11-14T19:10:01Z",
            "payload": {
                "lat": 37.4275,
                "lon": -122.1697,
                "accuracy_m": 12,
                "description": "near 450 Serra Mall",
            },
        },
    )
    return apply_event(
        context,
        _operator_event(
            session_id,
            "evt_op_01",
            "This is an adult male, unconscious, breathing normally",
            "2026-11-14T19:10:02Z",
        ),
    )


def summarize_events(events, title):
    context = reduce_events(events)
    _print_summary(
        title,
        compose_summary(
            context,
            summary_id=f"summary_{context['session_id']}",
            created_at=events[-1]["observed_at"],
        ),
    )


def _print_builtin_demos():
    example = new_context()
    for event in json.loads(
        (ROOT / "runtime/events.example.json").read_text(encoding="utf-8")
    ):
        example = apply_event(example, event)
    _print_summary(
        "EXAMPLE CONTEXT BRIEFING — NOT A DIAGNOSIS",
        compose_summary(example),
    )
    print()
    _print_summary(
        "ADULT MALE NORMAL-BREATHING DEMO — NOT A DIAGNOSIS",
        compose_summary(_demo_context(), summary_id="summary_demo_02"),
    )


if __name__ == "__main__":
    if len(sys.argv) > 2:
        raise SystemExit("Usage: python3 scripts/summarize.py [session.json]")
    if len(sys.argv) == 2:
        path = Path(sys.argv[1])
        try:
            events = load_events(path)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        if not events:
            raise SystemExit(f"No events in {path}")
        try:
            summarize_events(events, "SESSION BRIEFING — NOT A DIAGNOSIS")
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    else:
        _print_builtin_demos()
