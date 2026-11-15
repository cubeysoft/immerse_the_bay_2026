#!/usr/bin/env python3
"""Validate events and reduce them into incident context.

Vision hypotheses are stored beside the transcript. They do not write facts.
"""

from datetime import datetime
from pathlib import Path
import copy
import json

from vision import validate_hypothesis_payload


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads(
    (ROOT / "ai/transcriber-contract.json").read_text(encoding="utf-8")
)

PERMITTED_FACT_FIELDS = set(CONTRACT["permitted_fact_fields"])
FACT_VALUE_DOMAINS = CONTRACT["fact_value_domains"]

EVENT_SOURCES = {
    "speech_transcript": {"operator_report", "dispatcher_confirmed"},
    "help_request": {"app"},
    "location_update": {
        "operator_report",
        "dispatcher_confirmed",
        "companion_phone",
        "headset_service",
    },
    "aed_telemetry": {"aed_telemetry"},
    "call_status": {"phone_server"},
    "vision_hypothesis": {"cv_model"},
}

EVENT_FIELD_PREFIXES = {
    "speech_transcript": ("patient.", "scene.", "response.", "aed."),
    "help_request": ("incident.help_requested",),
    "location_update": ("scene.location_description",),
    "aed_telemetry": ("aed.",),
}

SOURCE_CERTAINTY = {
    "app": "verified",
    "operator_report": "reported",
    "dispatcher_confirmed": "verified",
    "aed_telemetry": "verified",
}

SOURCE_PRIORITY = {
    "unknown": 0,
    "operator_report": 2,
    "app": 3,
    "dispatcher_confirmed": 3,
    "aed_telemetry": 3,
}

CALL_STATUSES = {"not_requested", "requested", "ringing", "connected", "ended", "failed"}


class EventValidationError(ValueError):
    """Raised when an event violates the transcriber-to-call contract."""


def parse_timestamp(value):
    if not isinstance(value, str):
        raise EventValidationError("timestamp must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EventValidationError(f"invalid timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise EventValidationError(f"timestamp must include a timezone: {value}")
    return parsed


def empty_fact():
    return {
        "value": None,
        "source": "unknown",
        "certainty": "unknown",
        "last_event_id": None,
        "observed_at": None,
    }


def new_context(session_id="sim_demo_001", started_at="2026-11-14T19:00:00Z"):
    parse_timestamp(started_at)
    return {
        "session_id": session_id,
        "session_started_at": started_at,
        "location": {
            "lat": None,
            "lon": None,
            "accuracy_m": None,
            "source": "unknown",
            "captured_at": None,
            "description": None,
        },
        "facts": {field: empty_fact() for field in sorted(PERMITTED_FACT_FIELDS)},
        "conflicts": [],
        "event_ids": [],
        "event_history": [],
        "communications": {
            "test_call_status": "not_requested",
            "test_dispatcher_connected": False,
            "summary_last_sent_at": None,
        },
    }


def _matches_field_rule(event_type, field):
    return any(
        field == prefix or (prefix.endswith(".") and field.startswith(prefix))
        for prefix in EVENT_FIELD_PREFIXES.get(event_type, ())
    )


def validate_fact_value(field, value):
    domain = FACT_VALUE_DOMAINS[field]
    if isinstance(domain, list):
        if value not in domain:
            raise EventValidationError(f"{field} has invalid value: {value!r}")
        return

    value_type = domain["type"]
    if value_type == "boolean" and type(value) is not bool:
        raise EventValidationError(f"{field} must be boolean")
    if value_type == "integer":
        if type(value) is not int:
            raise EventValidationError(f"{field} must be an integer")
        if not domain["minimum"] <= value <= domain["maximum"]:
            raise EventValidationError(f"{field} is outside the accepted range")
    if value_type == "string":
        if not isinstance(value, str):
            raise EventValidationError(f"{field} must be a string")
        length = len(value.strip())
        if not domain["minLength"] <= length <= domain["maxLength"]:
            raise EventValidationError(f"{field} has invalid length")


def _validate_transcript_payload(payload):
    transcript = payload.get("transcript")
    provider = payload.get("stt_provider")
    if not isinstance(transcript, str) or not transcript.strip():
        raise EventValidationError("speech_transcript requires non-empty transcript")
    if len(transcript) > 2000:
        raise EventValidationError("speech transcript is too long")
    if not isinstance(provider, str) or not provider.strip():
        raise EventValidationError("speech_transcript requires stt_provider")
    if payload.get("is_final") is not True:
        raise EventValidationError("only final STT transcripts are accepted")
    confidence = payload.get("confidence")
    if confidence is not None and (
        type(confidence) not in {int, float} or not 0 <= confidence <= 1
    ):
        raise EventValidationError("STT confidence must be between 0 and 1")


def validate_event(context, event):
    required = {
        "event_id",
        "session_id",
        "type",
        "source",
        "observed_at",
        "received_at",
        "payload",
    }
    if not isinstance(event, dict):
        raise EventValidationError("event must be an object")
    missing = required - set(event)
    if missing:
        raise EventValidationError(f"event missing fields: {sorted(missing)}")
    if event["session_id"] != context["session_id"]:
        raise EventValidationError("event session_id does not match context")
    if not isinstance(event["event_id"], str) or not event["event_id"].strip():
        raise EventValidationError("event_id must be a non-empty string")

    event_type = event["type"]
    source = event["source"]
    if event_type not in EVENT_SOURCES:
        raise EventValidationError(f"unsupported event type: {event_type}")
    if source not in EVENT_SOURCES[event_type]:
        raise EventValidationError(f"{source} cannot submit {event_type}")
    if not isinstance(event["payload"], dict):
        raise EventValidationError("event payload must be an object")

    observed_at = parse_timestamp(event["observed_at"])
    received_at = parse_timestamp(event["received_at"])
    if received_at < observed_at:
        raise EventValidationError("received_at cannot precede observed_at")

    payload = event["payload"]
    if event_type == "speech_transcript":
        _validate_transcript_payload(payload)

    facts = payload.get("facts", [])
    if not isinstance(facts, list):
        raise EventValidationError("payload facts must be an array")
    if facts and event_type not in EVENT_FIELD_PREFIXES:
        raise EventValidationError(f"{event_type} cannot contain facts")

    seen_fields = set()
    for fact in facts:
        if not isinstance(fact, dict) or not {"field", "value"} <= set(fact):
            raise EventValidationError("each fact must contain field and value")
        field = fact["field"]
        if field in seen_fields:
            raise EventValidationError(f"event contains duplicate fact: {field}")
        seen_fields.add(field)
        if field not in PERMITTED_FACT_FIELDS:
            raise EventValidationError(f"unsupported fact field: {field}")
        if not _matches_field_rule(event_type, field):
            raise EventValidationError(f"{event_type} cannot update {field}")
        validate_fact_value(field, fact["value"])

    if event_type == "help_request":
        expected = [{"field": "incident.help_requested", "value": True}]
        if facts != expected:
            raise EventValidationError("help_request must set incident.help_requested=true")

    if event_type == "location_update" and source in {"companion_phone", "headset_service"}:
        if facts:
            raise EventValidationError("device location events cannot submit report facts")
        if payload.get("method") == "ip":
            raise EventValidationError("IP geolocation is not accepted")
        lat, lon = payload.get("lat"), payload.get("lon")
        if (lat is None) != (lon is None):
            raise EventValidationError("location requires both lat and lon")
        if lat is not None:
            if type(lat) not in {int, float} or not -90 <= lat <= 90:
                raise EventValidationError("latitude is invalid")
            if type(lon) not in {int, float} or not -180 <= lon <= 180:
                raise EventValidationError("longitude is invalid")
            accuracy = payload.get("accuracy_m")
            if type(accuracy) not in {int, float} or accuracy < 0:
                raise EventValidationError("accuracy_m must be a non-negative number")

    if event_type == "call_status" and payload.get("status") not in CALL_STATUSES:
        raise EventValidationError("call_status event has invalid status")

    if event_type == "vision_hypothesis":
        try:
            validate_hypothesis_payload(payload)
        except ValueError as exc:
            raise EventValidationError(str(exc)) from exc


def _fact_wins(existing, incoming_source, incoming_at, incoming_event_id):
    if existing["value"] is None:
        return True
    old_at = parse_timestamp(existing["observed_at"])
    new_at = parse_timestamp(incoming_at)
    if new_at != old_at:
        return new_at > old_at
    old_priority = SOURCE_PRIORITY.get(existing["source"], 0)
    new_priority = SOURCE_PRIORITY.get(incoming_source, 0)
    if new_priority != old_priority:
        return new_priority > old_priority
    return incoming_event_id > (existing["last_event_id"] or "")


def _record_conflict(context, field, existing, incoming, event):
    if existing["value"] is None or existing["value"] == incoming:
        return
    existing_key = (parse_timestamp(existing["observed_at"]), existing["last_event_id"])
    incoming_key = (parse_timestamp(event["observed_at"]), event["event_id"])
    if existing_key <= incoming_key:
        conflict = {
            "field": field,
            "previous_value": existing["value"],
            "previous_source": existing["source"],
            "previous_event_id": existing["last_event_id"],
            "incoming_value": incoming,
            "incoming_source": event["source"],
            "incoming_event_id": event["event_id"],
        }
    else:
        conflict = {
            "field": field,
            "previous_value": incoming,
            "previous_source": event["source"],
            "previous_event_id": event["event_id"],
            "incoming_value": existing["value"],
            "incoming_source": existing["source"],
            "incoming_event_id": existing["last_event_id"],
        }
    identity = (
        conflict["field"],
        conflict["previous_event_id"],
        conflict["incoming_event_id"],
    )
    existing_identities = {
        (item["field"], item["previous_event_id"], item["incoming_event_id"])
        for item in context["conflicts"]
    }
    if identity not in existing_identities:
        context["conflicts"].append(conflict)
        context["conflicts"].sort(
            key=lambda item: (
                item["field"],
                item["previous_event_id"],
                item["incoming_event_id"],
            )
        )


def _apply_location(context, event):
    payload = event["payload"]
    source = event["source"]
    observed_at = event["observed_at"]
    current_at = context["location"].get("captured_at")
    if current_at and parse_timestamp(observed_at) < parse_timestamp(current_at):
        return

    if source in {"companion_phone", "headset_service"} and payload.get("lat") is not None:
        context["location"].update(
            {
                "lat": payload["lat"],
                "lon": payload["lon"],
                "accuracy_m": payload["accuracy_m"],
                "source": source,
                "captured_at": observed_at,
                "description": payload.get("description"),
            }
        )
    elif source in {"operator_report", "dispatcher_confirmed"} and payload.get("description"):
        context["location"].update(
            {
                "source": source,
                "captured_at": observed_at,
                "description": payload["description"],
            }
        )


def apply_event(context, event):
    """Validate and apply one event without losing its raw transcript."""
    validate_event(context, event)
    updated = copy.deepcopy(context)
    updated.setdefault("event_ids", [])
    updated.setdefault("event_history", [])
    updated.setdefault("conflicts", [])
    for field in PERMITTED_FACT_FIELDS:
        updated["facts"].setdefault(field, empty_fact())

    if event["event_id"] in updated["event_ids"]:
        previous = next(
            item for item in updated["event_history"] if item["event_id"] == event["event_id"]
        )
        if previous != event:
            raise EventValidationError("duplicate event_id has different content")
        return updated

    updated["event_ids"].append(event["event_id"])
    updated["event_history"].append(copy.deepcopy(event))
    event_type = event["type"]
    payload = event["payload"]

    if event_type == "vision_hypothesis":
        return updated
    if event_type == "call_status":
        status = payload["status"]
        updated["communications"]["test_call_status"] = status
        updated["communications"]["test_dispatcher_connected"] = status == "connected"
        return updated
    if event_type == "location_update":
        _apply_location(updated, event)

    for item in payload.get("facts", []):
        field = item["field"]
        value = item["value"]
        existing = updated["facts"][field]
        _record_conflict(updated, field, existing, value, event)
        if not _fact_wins(existing, event["source"], event["observed_at"], event["event_id"]):
            continue
        updated["facts"][field] = {
            "value": value,
            "source": event["source"],
            "certainty": SOURCE_CERTAINTY[event["source"]],
            "last_event_id": event["event_id"],
            "observed_at": event["observed_at"],
        }
        if field == "scene.location_description":
            description = "roadside; exact location unconfirmed" if value == "roadside" else value
            updated["location"]["description"] = description
            if updated["location"]["lat"] is None:
                updated["location"].update(
                    {
                        "source": event["source"],
                        "captured_at": event["observed_at"],
                    }
                )
    return updated
