#!/usr/bin/env python3
"""Verify the Meta STT transcript-to-Twilio briefing boundary."""

from pathlib import Path
import json
import sys

from dispatcher import FORBIDDEN_SPOKEN_TERMS, compose_summary, validate_summary
from incident import EventValidationError, PERMITTED_FACT_FIELDS, apply_event, new_context
from transcriber import extract_transcript_facts


ROOT = Path(__file__).resolve().parents[1]


def load(relative_path):
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def make_event(
    event_id,
    *,
    event_type="speech_transcript",
    session_id="sim_demo_001",
    source="operator_report",
    observed_at="2026-11-14T19:00:01Z",
    received_at=None,
    payload=None,
):
    return {
        "event_id": event_id,
        "session_id": session_id,
        "type": event_type,
        "source": source,
        "observed_at": observed_at,
        "received_at": received_at or observed_at,
        "payload": dict(payload or {}),
    }


def transcript_event(
    event_id,
    transcript,
    *,
    source="operator_report",
    observed_at="2026-11-14T19:00:01Z",
    confidence=None,
):
    extracted = extract_transcript_facts(transcript, source=source)
    payload = {
        "transcript": transcript,
        "stt_provider": "meta_unity_ai_stt",
        "is_final": True,
        "facts": extracted["facts"],
        "unresolved": extracted["unresolved"],
    }
    if confidence is not None:
        payload["confidence"] = confidence
    return make_event(
        event_id,
        source=source,
        observed_at=observed_at,
        payload=payload,
    )


def help_event(event_id="help", observed_at="2026-11-14T19:00:00Z"):
    return make_event(
        event_id,
        event_type="help_request",
        source="app",
        observed_at=observed_at,
        payload={
            "facts": [{"field": "incident.help_requested", "value": True}]
        },
    )


def expect_rejected(errors, label, context, event):
    try:
        apply_event(context, event)
    except EventValidationError:
        return
    errors.append(f"{label}: invalid event was accepted")


def check_contracts():
    errors = []
    for path in sorted(ROOT.rglob("*.json")):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"invalid JSON: {path.relative_to(ROOT)}: {exc}")
    if errors:
        return errors

    contract = load("ai/transcriber-contract.json")
    allowed = set(contract["permitted_fact_fields"])
    domains = set(contract["fact_value_domains"])
    if allowed != domains:
        errors.append(f"fact domains out of sync: {sorted(allowed ^ domains)}")
    if "incident.help_requested" not in allowed:
        errors.append("explicit help request is absent from the fact contract")
    if "scene.background_context" in allowed:
        errors.append("CV background leaked into the transcript-to-call contract")

    schema = load("dispatch/summary-schema.json")
    schema_fields = set(
        schema["properties"]["facts"]["items"]["properties"]["field"]["enum"]
    )
    if schema_fields != allowed:
        errors.append(f"summary schema fields out of sync: {sorted(schema_fields ^ allowed)}")
    if "recognition_flags" in schema["properties"]:
        errors.append("medical recognition flags remain in the Twilio summary contract")
    if "transcripts" not in schema["required"]:
        errors.append("structured summary does not require raw STT transcripts")

    scenario_fields = set()
    scenarios = load("knowledge-base/scenarios.json")
    scenario_fields.update(scenarios["recognition_rule"]["inputs"])
    for scenario in scenarios["scenarios"]:
        scenario_fields.update(scenario["evidence_fields"])
    if scenario_fields - allowed:
        errors.append(
            f"scenario evidence absent from fact contract: {sorted(scenario_fields - allowed)}"
        )

    manifest = load("knowledge-base/manifest.json")
    if manifest["clinical_approval"]["status"] != "not_approved":
        errors.append("clinical release gate changed without review")
    if manifest["safety_policy"]["clinical_response_playback_enabled"]:
        errors.append("unapproved clinical speech is enabled")
    return errors


def check_transcriber():
    errors = []
    for index, case in enumerate(load("tests/routing.json")["cases"], start=1):
        result = extract_transcript_facts(
            case["input"],
            source=case.get("source", "operator_report"),
        )
        actual = {item["field"]: item["value"] for item in result["facts"]}
        if actual != case["expected_facts"]:
            errors.append(
                f"transcript #{index} exact facts differ; "
                f"expected {case['expected_facts']}, got {actual}"
            )
        expected_unresolved = case.get("expected_unresolved", [])
        if result["unresolved"] != expected_unresolved:
            errors.append(
                f"transcript #{index} unresolved differs; "
                f"expected {expected_unresolved}, got {result['unresolved']}"
            )
        if result["source"] != case.get("source", "operator_report"):
            errors.append(f"transcript #{index} changed speaker provenance")
    return errors


def check_event_validation():
    errors = []
    context = new_context()
    valid = transcript_event(
        "valid-transcript",
        "An adult is unconscious and breathing normally",
        confidence=0.91,
    )

    invalid = [
        (
            "cross-session transcript",
            {**valid, "event_id": "bad-session", "session_id": "other"},
        ),
        (
            "interim transcript",
            {
                **valid,
                "event_id": "bad-interim",
                "payload": {**valid["payload"], "is_final": False},
            },
        ),
        (
            "missing STT provider",
            {
                **valid,
                "event_id": "bad-provider",
                "payload": {**valid["payload"], "stt_provider": ""},
            },
        ),
        (
            "invalid STT confidence",
            {
                **valid,
                "event_id": "bad-confidence",
                "payload": {**valid["payload"], "confidence": 1.5},
            },
        ),
        (
            "invalid breathing value",
            {
                **valid,
                "event_id": "bad-breathing",
                "payload": {
                    **valid["payload"],
                    "facts": [{"field": "patient.breathing", "value": "banana"}],
                },
            },
        ),
        (
            "speech fabricates help activation",
            {
                **valid,
                "event_id": "bad-help-source",
                "payload": {
                    **valid["payload"],
                    "facts": [
                        {"field": "incident.help_requested", "value": True}
                    ],
                },
            },
        ),
        (
            "invalid help event",
            make_event(
                "bad-help",
                event_type="help_request",
                source="app",
                payload={
                    "facts": [
                        {"field": "incident.help_requested", "value": False}
                    ]
                },
            ),
        ),
        (
            "IP geolocation",
            make_event(
                "bad-ip",
                event_type="location_update",
                source="companion_phone",
                payload={
                    "lat": 37,
                    "lon": -122,
                    "accuracy_m": 5000,
                    "method": "ip",
                },
            ),
        ),
        (
            "device location fabricates operator description",
            make_event(
                "bad-device-fact",
                event_type="location_update",
                source="companion_phone",
                payload={
                    "lat": 37,
                    "lon": -122,
                    "accuracy_m": 5,
                    "facts": [
                        {
                            "field": "scene.location_description",
                            "value": "reported address"
                        }
                    ],
                },
            ),
        ),
        (
            "received before observed",
            {
                **valid,
                "event_id": "bad-time",
                "observed_at": "2026-11-14T19:00:02Z",
                "received_at": "2026-11-14T19:00:01Z",
            },
        ),
    ]
    for label, event in invalid:
        expect_rejected(errors, label, context, event)

    context = apply_event(context, valid)
    if context["facts"]["patient.responsive"]["value"] is not False:
        errors.append("valid final transcript did not update context")
    if context["event_history"][0]["payload"]["transcript"] != valid["payload"]["transcript"]:
        errors.append("raw STT transcript was not retained")

    context = apply_event(context, valid)
    if len(context["event_history"]) != 1:
        errors.append("identical duplicate transcript was not idempotent")

    changed = {
        **valid,
        "payload": {**valid["payload"], "transcript": "different content"},
    }
    expect_rejected(errors, "changed duplicate transcript", context, changed)
    return errors


def reduce_events(events):
    context = new_context()
    for event in events:
        context = apply_event(context, event)
    return context


def check_briefing():
    errors = []
    geo = make_event(
        "geo",
        event_type="location_update",
        source="companion_phone",
        observed_at="2026-11-14T19:00:01Z",
        payload={
            "lat": 37.4275,
            "lon": -122.1697,
            "accuracy_m": 12,
            "description": "near 450 Serra Mall",
        },
    )
    report = transcript_event(
        "report",
        "This is an adult male, unconscious, breathing normally",
        observed_at="2026-11-14T19:00:02Z",
        confidence=0.9,
    )

    summary = compose_summary(reduce_events([help_event(), geo, report]))
    expected_phrases = (
        "Emergency assistance requested.",
        "Device location: near 450 Serra Mall, within 12 meters.",
        "Bystander reports: adult; male; unresponsive; breathing normally.",
    )
    for phrase in expected_phrases:
        if phrase not in summary["spoken_text"]:
            errors.append(f"minimum briefing omitted {phrase!r}")
    if len(summary["transcripts"]) != 1:
        errors.append("minimum briefing did not retain exactly one STT transcript")
    if "recognition_flags" in summary:
        errors.append("minimum briefing still contains medical recognition output")

    no_help = compose_summary(reduce_events([geo, report]))
    if "Help request not confirmed." not in no_help["spoken_text"]:
        errors.append("speech incorrectly implied explicit help activation")

    normal = transcript_event(
        "normal",
        "The patient is unconscious and breathing normally",
        observed_at="2026-11-14T19:00:03Z",
    )
    gasping = transcript_event(
        "gasping",
        "The patient is gasping",
        observed_at="2026-11-14T19:00:05Z",
    )
    first = reduce_events([help_event(), normal, gasping])
    second = reduce_events([gasping, help_event(), normal])
    if first["facts"] != second["facts"] or first["conflicts"] != second["conflicts"]:
        errors.append("arrival order changed current facts or normalized conflicts")
    conflict_summary = compose_summary(first)
    if "Reports conflict on breathing" not in conflict_summary["spoken_text"]:
        errors.append("briefing did not disclose changed breathing report")

    dispatcher = transcript_event(
        "dispatcher",
        "The patient is awake and breathing normally",
        source="dispatcher_confirmed",
        observed_at="2026-11-14T19:00:06Z",
    )
    dispatcher_summary = compose_summary(
        reduce_events([help_event(), report, dispatcher])
    )
    if "Dispatcher confirms: responsive; breathing normally." not in dispatcher_summary["spoken_text"]:
        errors.append("briefing lost dispatcher provenance")

    scenario_reports = [
        ("He was pulled from the water and is not breathing", "patient recovered from water"),
        ("She overdosed and is unresponsive, barely breathing", "possible substance exposure"),
        ("He touched a live wire and is unresponsive", "electrical contact"),
        ("There is visible smoke and the patient is gasping", "visible smoke"),
        ("He has a bleeding head injury from a fall", "bleeding head injury"),
    ]
    for index, (text, expected) in enumerate(scenario_reports):
        scenario_summary = compose_summary(
            reduce_events([help_event(), transcript_event(f"scenario-{index}", text)])
        )
        if expected not in scenario_summary["spoken_text"]:
            errors.append(f"scenario briefing omitted {expected!r}")

    for candidate in (
        summary,
        no_help,
        conflict_summary,
        dispatcher_summary,
    ):
        validate_summary(candidate)
        for term in FORBIDDEN_SPOKEN_TERMS:
            if term in candidate["spoken_text"].lower():
                errors.append(f"spoken briefing contains forbidden term: {term}")
    return errors


def check_examples():
    errors = []
    context = new_context()
    for event in load("runtime/events.example.json"):
        try:
            context = apply_event(context, event)
        except EventValidationError as exc:
            errors.append(f"invalid runtime fixture {event.get('event_id')}: {exc}")
    fixture_summary = compose_summary(context)
    if "Emergency assistance requested." not in fixture_summary["spoken_text"]:
        errors.append("runtime fixture lost explicit help request")
    if len(fixture_summary["transcripts"]) != 2:
        errors.append("runtime fixture did not retain both Meta STT transcripts")

    example = load("dispatch/summary.example.json")
    try:
        validate_summary(example)
    except ValueError as exc:
        errors.append(f"invalid summary example: {exc}")

    call = load("api/request-examples.json")["test_call"]["body"]
    expected_call = {
        "destination_id": "test_dispatcher",
        "audio_route": "paired_phone",
        "simulation_only": True,
    }
    if call != expected_call:
        errors.append("test call fixture breaks allowlisted simulation policy")
    return errors


def check():
    errors = []
    errors.extend(check_contracts())
    if errors:
        return errors
    errors.extend(check_transcriber())
    errors.extend(check_event_validation())
    errors.extend(check_briefing())
    errors.extend(check_examples())
    return errors


if __name__ == "__main__":
    failures = check()
    if failures:
        print("Validation checks FAILED:")
        for failure in failures:
            print(" -", failure)
        sys.exit(1)
    case_count = len(load("tests/routing.json")["cases"])
    print(
        f"PASS: Meta STT boundary, {case_count} exact transcript cases, explicit help, "
        "location fallback, event rejection, provenance and Twilio briefing."
    )
    print(
        "IMPORTANT: This is not an STT accuracy test, clinical approval, "
        "API integration test, or proof of headset performance."
    )
