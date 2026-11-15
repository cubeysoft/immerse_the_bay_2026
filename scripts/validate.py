#!/usr/bin/env python3
"""Verify the Meta STT transcript-to-Twilio briefing boundary."""

from pathlib import Path
import json
import sys
import time

from dispatcher import FORBIDDEN_SPOKEN_TERMS, compose_summary, validate_summary
from incident import EventValidationError, PERMITTED_FACT_FIELDS, apply_event, new_context
from session import reduce_events
from transcriber import extract_transcript_facts
from vision import (
    BUDGET_SECONDS,
    corroborate_context,
    look_at,
    parse_model_text,
    wait_until_idle,
)


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
        "Emergency assistance has been requested.",
        "The device is near 450 Serra Mall, within 12 meters.",
        "The bystander reports an adult male who is unresponsive and breathing normally.",
    )
    for phrase in expected_phrases:
        if phrase not in summary["spoken_text"]:
            errors.append(f"minimum briefing omitted {phrase!r}")
    if len(summary["transcripts"]) != 1:
        errors.append("minimum briefing did not retain exactly one STT transcript")
    if "recognition_flags" in summary:
        errors.append("minimum briefing still contains medical recognition output")

    no_help = compose_summary(reduce_events([geo, report]))
    if "A help request has not been confirmed." not in no_help["spoken_text"]:
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
    if "The reports disagree about breathing." not in conflict_summary["spoken_text"]:
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
    if (
        "The dispatcher confirms that the patient is responsive and breathing normally."
        not in dispatcher_summary["spoken_text"]
    ):
        errors.append("briefing lost dispatcher provenance")

    instruction = "Push hard in the center of the chest."
    instruction_event = transcript_event(
        "dispatcher-instruction",
        instruction,
        source="dispatcher_confirmed",
        observed_at="2026-11-14T19:00:07Z",
    )
    instruction_summary = compose_summary(
        reduce_events([help_event(), report, instruction_event])
    )
    if (
        "The dispatcher said, push hard in the center of the chest."
        not in instruction_summary["spoken_text"]
    ):
        errors.append("briefing dropped a dispatcher instruction that matched no fact")
    if not any(item["text"] == instruction for item in instruction_summary["transcripts"]):
        errors.append("transcript list dropped the dispatcher instruction")
    if any(fact["field"] == "response.cpr_started" for fact in instruction_summary["facts"]):
        errors.append("unmatched dispatcher instruction was stored as CPR started")

    scenario_reports = [
        ("He was pulled from the water and is not breathing", "the patient was recovered from water"),
        ("She overdosed and is unresponsive, barely breathing", "possible substance exposure"),
        ("He touched a live wire and is unresponsive", "the patient made electrical contact"),
        ("There is visible smoke and the patient is gasping", "smoke is visible"),
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
        instruction_summary,
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
    if "Emergency assistance has been requested." not in fixture_summary["spoken_text"]:
        errors.append("runtime fixture lost explicit help request")
    if len(fixture_summary["transcripts"]) != 2:
        errors.append("runtime fixture did not retain both Meta STT transcripts")
    fixture_text = [item["text"] for item in fixture_summary["transcripts"]]
    if fixture_text != [
        "I am by the highway. Someone is unconscious.",
        "They are gasping.",
    ]:
        errors.append("runtime fixture changed the verbatim transcript")

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


def _claim(name, value):
    return {
        "claim": name,
        "value": value,
        "status": "uncorroborated",
        "transcript_event_id": None,
    }


def _vision_event(event_id, claims, observed_at, *, person_count=1, include_vlm=True):
    payload = {
        "frame_id": "frame_88",
        "image_width": 378,
        "image_height": 378,
        "claims": claims,
    }
    if person_count is not None:
        payload["detector"] = {
            "name": "yolov9",
            "person_count": person_count,
            "confidence": 0.86,
        }
    if include_vlm:
        payload["vlm"] = {
            "name": "moondream2",
            "revision": "2025-06-21",
            "latency_ms": 40,
        }
    return make_event(
        event_id,
        event_type="vision_hypothesis",
        source="cv_model",
        observed_at=observed_at,
        payload=payload,
    )


def _claim_status(context, name):
    report = corroborate_context(context)
    if not report:
        return None
    for item in report[-1]["claims"]:
        if item["claim"] == name:
            return item
    return None


def _spoken(events):
    return compose_summary(reduce_events(events))["spoken_text"]


def check_vision():
    errors = []
    if BUDGET_SECONDS != 1:
        errors.append("vision budget must stay at one second so audio remains the fallback")

    still_at = "2026-11-14T19:00:00Z"
    speech_at = "2026-11-14T19:00:10Z"
    aed_yes = _vision_event("vision-aed", [_claim("aed_like_object", "yes")], still_at)
    aed_no = _vision_event("vision-no-aed", [_claim("aed_like_object", "no")], still_at)
    aed_speech = transcript_event("speech-aed", "I have an AED.", observed_at=speech_at)
    no_aed_speech = transcript_event("speech-no-aed", "We have no AED.", observed_at=speech_at)

    def require_status(context, name, expected, label):
        found = _claim_status(context, name)
        if found is None or found["status"] != expected:
            errors.append(label)
            return None
        return found

    agreed = reduce_events([aed_yes, aed_speech])
    agreed_claim = require_status(
        agreed, "aed_like_object", "corroborated", "AED speech inside 15 seconds did not corroborate the still"
    )
    if agreed_claim and agreed_claim["transcript_event_id"] != "speech-aed":
        errors.append("corroboration did not point at the transcript event")
    if agreed["facts"]["aed.available"]["source"] != "operator_report" or agreed["facts"]["aed.available"]["value"] is not True:
        errors.append("AED corroboration changed the operator fact")
    if _spoken([aed_yes, aed_speech]) != _spoken([aed_speech]):
        errors.append("a corroborated still changed the spoken briefing")

    alone = reduce_events([aed_yes])
    if alone["facts"]["aed.available"]["value"] is not None:
        errors.append("a vision hypothesis wrote aed.available with nobody speaking")
    require_status(alone, "aed_like_object", "uncorroborated", "an unspoken still was treated as confirmed")

    stale_speech = transcript_event("speech-stale", "I have an AED.", observed_at="2026-11-14T19:00:16Z")
    require_status(
        reduce_events([aed_yes, stale_speech]),
        "aed_like_object",
        "uncorroborated",
        "a still older than 15 seconds corroborated a new line",
    )
    boundary_speech = transcript_event("speech-boundary", "I have an AED.", observed_at="2026-11-14T19:00:15Z")
    require_status(
        reduce_events([aed_yes, boundary_speech]),
        "aed_like_object",
        "corroborated",
        "a still 15 seconds before speech was treated as stale",
    )

    early_speech = transcript_event("speech-early", "I have an AED.", observed_at=still_at)
    later_still = _vision_event("vision-later", [_claim("aed_like_object", "yes")], "2026-11-14T19:00:05Z")
    require_status(
        reduce_events([early_speech, later_still]),
        "aed_like_object",
        "corroborated",
        "a still just after the latest line did not corroborate it",
    )
    too_late = _vision_event("vision-too-late", [_claim("aed_like_object", "yes")], "2026-11-14T19:00:20Z")
    require_status(
        reduce_events([early_speech, too_late]),
        "aed_like_object",
        "uncorroborated",
        "a still 20 seconds after speech corroborated an old line",
    )

    conflict = reduce_events([aed_no, aed_speech])
    require_status(conflict, "aed_like_object", "conflict", "a still that misses a spoken AED was not a conflict")
    if conflict["facts"]["aed.available"]["value"] is not True:
        errors.append("a conflicting still cleared the operator's AED report")
    if _spoken([aed_no, aed_speech]) != _spoken([aed_speech]):
        errors.append("a conflicting still changed the spoken briefing")

    negative = reduce_events([aed_no, no_aed_speech])
    require_status(
        negative,
        "aed_like_object",
        "uncorroborated",
        "a negative still corroborated a negative speech value",
    )
    if negative["facts"]["aed.available"]["value"] is not False:
        errors.append("negative speech lost aed.available=false")

    opposite = reduce_events([aed_yes, no_aed_speech])
    require_status(
        opposite, "aed_like_object", "conflict", "a positive still against a spoken absence was not a conflict"
    )
    if opposite["facts"]["aed.available"]["source"] != "operator_report":
        errors.append("a positive still overrode a spoken AED absence")

    gasping = transcript_event("speech-gasp", "They are gasping.", observed_at=speech_at)
    reclined = _vision_event("vision-posture", [_claim("posture", "reclined")], still_at)
    gasp_context = reduce_events([reclined, gasping])
    if gasp_context["facts"]["patient.breathing"]["value"] != "gasping":
        errors.append("gasping speech was lost beside a posture claim")
    if gasp_context["facts"]["patient.responsive"]["value"] is not None:
        errors.append("a reclined posture set patient.responsive")
    require_status(gasp_context, "posture", "uncorroborated", "gasping speech corroborated a reclined posture")
    gasp_spoken = _spoken([reclined, gasping])
    if gasp_spoken != _spoken([gasping]):
        errors.append("a posture claim changed the spoken briefing")
    for term in FORBIDDEN_SPOKEN_TERMS:
        if term in gasp_spoken.lower():
            errors.append(f"posture briefing contains forbidden term: {term}")

    dispatcher = transcript_event(
        "speech-ground",
        "You said they are on the ground.",
        source="dispatcher_confirmed",
        observed_at=speech_at,
    )
    ground = reduce_events([reclined, dispatcher])
    ground_claim = require_status(
        ground, "posture", "corroborated", "dispatcher posture words did not corroborate reclined"
    )
    if ground_claim and ground_claim["transcript_event_id"] != "speech-ground":
        errors.append("posture corroboration did not point at the dispatcher line")
    if ground["facts"]["patient.responsive"]["value"] is not None:
        errors.append("dispatcher posture words set patient.responsive")
    if _spoken([reclined, dispatcher]) != _spoken([dispatcher]):
        errors.append("corroborated posture changed the spoken briefing")

    smoke_speech = transcript_event("speech-smoke", "There is visible smoke.", observed_at=speech_at)
    smoke_still = _vision_event("vision-smoke", [_claim("smoke_visible", "yes")], still_at)
    smoke_context = reduce_events([smoke_still, smoke_speech])
    require_status(smoke_context, "smoke_visible", "corroborated", "spoken smoke did not corroborate smoke_visible")
    if smoke_context["facts"]["scene.visible_smoke"]["source"] != "operator_report":
        errors.append("smoke corroboration changed the fact source")

    interim = transcript_event("speech-interim", "I have an AED.", observed_at=speech_at)
    interim["payload"]["is_final"] = False
    interim_context = new_context()
    interim_context["event_history"] = [interim, aed_yes]
    require_status(
        interim_context, "aed_like_object", "uncorroborated", "an interim transcript corroborated a still"
    )

    for fact in agreed["facts"].values():
        if fact["source"] == "cv_model":
            errors.append("a fact lists cv_model as its source")

    context = new_context()
    oversized = _vision_event("bad-size", [_claim("posture", "reclined")], still_at)
    oversized["payload"]["image_width"] = 1000
    fact_payload = _vision_event("bad-facts", [_claim("posture", "reclined")], still_at)["payload"]
    fact_payload["facts"] = [{"field": "patient.breathing", "value": "gasping"}]
    rejected = [
        ("clinical vision claim", _vision_event("bad-clinical", [_claim("patient.breathing", "gasping")], still_at)),
        ("unconscious posture", _vision_event("bad-unconscious", [_claim("posture", "unconscious")], still_at)),
        (
            "vision fact payload",
            make_event(
                "bad-facts",
                event_type="vision_hypothesis",
                source="cv_model",
                observed_at=still_at,
                payload=fact_payload,
            ),
        ),
        ("oversized still", oversized),
        (
            "model ran with nobody present",
            _vision_event(
                "bad-empty",
                [_claim("person_visible", "no")],
                still_at,
                person_count=0,
                include_vlm=True,
            ),
        ),
    ]
    for label, event in rejected:
        expect_rejected(errors, label, context, event)

    model_json = (
        '{"person_visible":"yes","person_count":7,"posture":"reclined",'
        '"aed_like_object":"unclear","smoke_visible":"unclear"}'
    )
    parsed = {item["claim"]: item["value"] for item in (parse_model_text(model_json) or [])}
    if parsed.get("person_count") != "many":
        errors.append("person_count above 5 was not stored as many")
    if parse_model_text("The patient is unconscious.") is not None:
        errors.append("clinical prose was accepted as a vision claim")
    extra = model_json[:-1] + ',"diagnosis":"arrest"}'
    if parse_model_text(extra) is not None:
        errors.append("an unknown vision key was accepted")

    def fail_if_called(_image):
        raise AssertionError("the model ran")

    skipped = look_at(None, fail_if_called, person_count=0)
    if skipped.mode != "vision" or skipped.reason != "detector" or skipped.claims != [_claim("person_visible", "no")]:
        errors.append("a zero person count still called the vision model")

    def slow(_image):
        time.sleep(0.3)
        return model_json

    timed_out = look_at(None, slow, budget_s=0.05)
    busy = look_at(None, slow, budget_s=0.05)
    if not wait_until_idle():
        errors.append("a timed-out vision call never released the look")
    if timed_out.mode != "audio" or timed_out.reason != "timeout" or timed_out.claims:
        errors.append("a slow look was not dropped in favor of audio")
    if busy.mode != "audio" or busy.reason != "busy":
        errors.append("a second look started while the first was still running")

    def crash(_image):
        raise RuntimeError("down")

    crashed = look_at(None, crash, budget_s=1)
    if crashed.mode != "audio" or crashed.reason != "model_error":
        errors.append("a crashed look did not fall back to audio")
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
    errors.extend(check_vision())
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
        "location fallback, event rejection, provenance, vision corroboration, "
        "one-second audio fallback and Twilio briefing."
    )
    print(
        "IMPORTANT: This is not an STT accuracy test, clinical approval, "
        "API integration test, or proof of headset performance."
    )
