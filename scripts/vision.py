#!/usr/bin/env python3
"""Turn one still into claims, then keep only what a final transcript agrees with.

A look is either a closed set of claims or a decision to stay with the audio
briefing. Claims never become incident facts. Corroboration is a table join
between a claim and a finished operator or dispatcher line.
"""

from datetime import datetime, timedelta
from pathlib import Path
import json
import re
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "ai/vision-contract.json").read_text(encoding="utf-8"))

IMAGE_SIZE = CONTRACT["image_size"]
BUDGET_SECONDS = CONTRACT["budget_seconds"]
STALE_SECONDS = CONTRACT["stale_seconds"]
HUMAN_SOURCES = set(CONTRACT["human_sources"])
FORBIDDEN_WORDS = tuple(CONTRACT["forbidden_words"])
VOCABULARY = {item["name"]: item for item in CONTRACT["vocabulary"]}
CLAIM_NAMES = tuple(VOCABULARY)
ALIGNMENTS = {item["claim"]: item for item in CONTRACT["alignments"]}

PROMPT = (
    "Reply with one JSON object and no other text. "
    "person_visible is yes, no, or unclear. "
    "person_count is an integer or unclear. "
    "posture is upright, seated, reclined, or unclear. "
    "aed_like_object is yes, no, or unclear. "
    "smoke_visible is yes, no, or unclear. "
    "If you are unsure, use unclear."
)

_LOCK = threading.Lock()
_BUSY = False


class Look:
    """The outcome of one still. mode 'audio' means the briefing stays on speech."""

    def __init__(self, mode, reason, claims, latency_ms):
        self.mode = mode
        self.reason = reason
        self.claims = claims
        self.latency_ms = latency_ms

    def as_dict(self):
        return {
            "mode": self.mode,
            "reason": self.reason,
            "latency_ms": self.latency_ms,
            "claims": self.claims,
        }


def _parse_time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include a timezone: {value}")
    return parsed


def _forbidden(text):
    lowered = text.lower()
    return any(
        re.search(rf"\b{re.escape(phrase)}\b", lowered) for phrase in FORBIDDEN_WORDS
    )


def _json_body(text):
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 2 or lines[-1].strip() != "```":
        return None
    if lines[0].strip() not in {"```", "```json"}:
        return None
    return "\n".join(lines[1:-1]).strip()


def _coerce_count(raw, spec):
    bounds = spec["integers"]
    if isinstance(raw, str) and raw in spec["values"]:
        return raw
    if isinstance(raw, str) and raw.isdigit():
        raw = int(raw)
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None
    if raw > bounds["maximum"]:
        return bounds["above"]
    if bounds["minimum"] <= raw <= bounds["maximum"]:
        return raw
    return None


def _coerce(name, raw):
    spec = VOCABULARY[name]
    if isinstance(raw, str):
        raw = raw.strip().lower()
    if "integers" in spec:
        return _coerce_count(raw, spec)
    if raw in spec["values"]:
        return raw
    return None


def _consistent(claims):
    values = {item["claim"]: item["value"] for item in claims}
    visible = values.get("person_visible")
    count = values.get("person_count")
    if visible == "no" and isinstance(count, int):
        return False
    if visible == "no" and count == "many":
        return False
    return True


def _blank_claim(name, value):
    return {
        "claim": name,
        "value": value,
        "status": "uncorroborated",
        "transcript_event_id": None,
    }


def parse_model_text(text):
    """Return the five claims, or None when the reply is not the closed vocabulary."""
    if not isinstance(text, str):
        return None
    if len(text) > CONTRACT["max_characters"] or _forbidden(text):
        return None
    body = _json_body(text)
    if body is None:
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or set(data) != set(CLAIM_NAMES):
        return None
    claims = []
    for name in CLAIM_NAMES:
        value = _coerce(name, data[name])
        if value is None:
            return None
        claims.append(_blank_claim(name, value))
    if not _consistent(claims):
        return None
    return claims


def detector_claims():
    """YOLO saw nobody. Skip the vision-language model."""
    return [_blank_claim("person_visible", "no")]


def _begin():
    global _BUSY
    with _LOCK:
        if _BUSY:
            return False
        _BUSY = True
        return True


def _end():
    global _BUSY
    with _LOCK:
        _BUSY = False


def wait_until_idle(timeout=5):
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        with _LOCK:
            if not _BUSY:
                return True
        time.sleep(0.01)
    return False


def look_at(image, observe, *, person_count=None, budget_s=None):
    """Run one look. A miss, including a slow model, leaves the audio briefing in charge.

    A timed-out call is not cancelled inside the model runtime. Its result is
    ignored, and another look is refused until that call finishes.
    """
    if person_count == 0:
        return Look("vision", "detector", detector_claims(), 0)

    budget = BUDGET_SECONDS if budget_s is None else budget_s
    if not _begin():
        return Look("audio", "busy", [], None)

    holder = {}

    def run():
        try:
            holder["text"] = observe(image)
        except Exception as exc:
            holder["error"] = exc
        finally:
            _end()

    started = time.perf_counter()
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(budget)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if worker.is_alive():
        return Look("audio", "timeout", [], elapsed_ms)
    if "error" in holder:
        return Look("audio", "model_error", [], elapsed_ms)
    claims = parse_model_text(holder.get("text"))
    if claims is None:
        return Look("audio", "invalid_model_output", [], elapsed_ms)
    return Look("vision", "model", claims, elapsed_ms)


def _is_final_speech(event):
    if event.get("type") != "speech_transcript":
        return False
    if event.get("source") not in HUMAN_SOURCES:
        return False
    payload = event.get("payload")
    return isinstance(payload, dict) and payload.get("is_final") is True


def _phrase_value(alignment, transcript):
    lowered = transcript.lower()
    matched = []
    for label, phrases in alignment["phrases"].items():
        for phrase in phrases:
            if re.search(rf"\b{re.escape(phrase)}\b", lowered):
                matched.append(label)
                break
    if len(set(matched)) != 1:
        return None
    return matched[0]


def _same_count(left, right):
    return str(left) == str(right)


def _relation(claim, speech):
    alignment = ALIGNMENTS.get(claim["claim"])
    if alignment is None or claim["value"] == "unclear":
        return None
    if alignment["kind"] == "fact":
        facts = {
            item["field"]: item["value"]
            for item in speech["payload"].get("facts", [])
            if isinstance(item, dict) and "field" in item
        }
        field = alignment["fact_field"]
        if field not in facts:
            return None
        agrees = claim["value"] == alignment["agree"] and facts[field] == alignment["fact_value"]
        if agrees:
            return "agree"
        disagrees = (
            facts[field] == alignment["fact_value"] and claim["value"] in alignment["conflict"]
        ) or (
            facts[field] != alignment["fact_value"] and claim["value"] == alignment["agree"]
        )
        if disagrees:
            return "conflict"
        return None

    spoken = _phrase_value(alignment, speech["payload"].get("transcript", ""))
    if spoken is None:
        return None
    if _same_count(claim["value"], spoken):
        return "agree"
    return "conflict"


def _still_is_fresh(still_at, speech_at, speech_is_latest, previous_still_at):
    gap = speech_at - still_at
    window = timedelta(seconds=STALE_SECONDS)
    if timedelta(0) <= gap <= window:
        return True
    arrived_after_speech = timedelta(0) < -gap <= window
    newer_than_previous = previous_still_at is None or still_at > previous_still_at
    return speech_is_latest and arrived_after_speech and newer_than_previous


def corroborate_context(context):
    """Derive claim status from the event log. Does not write facts or spoken text."""
    history = context.get("event_history", [])
    speeches = [event for event in history if _is_final_speech(event)]
    latest_speech_id = speeches[-1]["event_id"] if speeches else None
    hypotheses = [event for event in history if event.get("type") == "vision_hypothesis"]
    previous_still_at = None
    report = []
    for event in hypotheses:
        still_at = _parse_time(event["observed_at"])
        claims = []
        for raw in event["payload"]["claims"]:
            claim = dict(raw)
            claim["status"] = "uncorroborated"
            claim["transcript_event_id"] = None
            for speech in speeches:
                fresh = _still_is_fresh(
                    still_at,
                    _parse_time(speech["observed_at"]),
                    speech["event_id"] == latest_speech_id,
                    previous_still_at,
                )
                if not fresh:
                    continue
                relation = _relation(claim, speech)
                if relation is None:
                    continue
                claim["status"] = "corroborated" if relation == "agree" else "conflict"
                claim["transcript_event_id"] = speech["event_id"]
            claims.append(claim)
        report.append(
            {
                "event_id": event["event_id"],
                "observed_at": event["observed_at"],
                "frame_id": event["payload"]["frame_id"],
                "claims": claims,
            }
        )
        previous_still_at = still_at
    return report


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _validate_claim(claim, seen):
    _require(isinstance(claim, dict), "each vision claim must be an object")
    _require(
        set(claim) == {"claim", "value", "status", "transcript_event_id"},
        "vision claim fields are fixed",
    )
    name = claim["claim"]
    _require(name in VOCABULARY, f"unsupported vision claim: {name}")
    _require(name not in seen, f"duplicate vision claim: {name}")
    seen.add(name)
    _require(claim["status"] == "uncorroborated", "stored vision claims start uncorroborated")
    _require(claim["transcript_event_id"] is None, "stored vision claims have no transcript yet")
    _require(_coerce(name, claim["value"]) == claim["value"], f"invalid value for {name}")


def _validate_detector(detector, claims, vlm):
    if detector is None:
        return
    _require(isinstance(detector, dict), "detector must be an object")
    allowed = {"name", "person_count", "confidence"}
    _require(
        set(detector) <= allowed and {"name", "person_count"} <= set(detector),
        "detector is incomplete",
    )
    _require(isinstance(detector["name"], str) and detector["name"].strip(), "detector name is required")
    count = detector["person_count"]
    _require(isinstance(count, int) and not isinstance(count, bool) and count >= 0, "person_count is invalid")
    confidence = detector.get("confidence")
    _require(
        confidence is None
        or (
            type(confidence) in {int, float}
            and not isinstance(confidence, bool)
            and 0 <= confidence <= 1
        ),
        "detector confidence must be between 0 and 1",
    )
    if count != 0:
        return
    _require(vlm is None, "a still with no person does not run the vision model")
    _require(
        claims == [_blank_claim("person_visible", "no")],
        "a still with no person only records person_visible=no",
    )


def _validate_vlm(vlm):
    if vlm is None:
        return
    _require(isinstance(vlm, dict), "vlm must be an object")
    _require(set(vlm) == {"name", "revision", "latency_ms"}, "vlm fields are fixed")
    _require(vlm["name"] == CONTRACT["model_name"], "unexpected vision model")
    _require(vlm["revision"] == CONTRACT["model_revision"], "unexpected vision model revision")
    latency = vlm["latency_ms"]
    _require(isinstance(latency, int) and not isinstance(latency, bool) and latency >= 0, "latency_ms is invalid")


def validate_hypothesis_payload(payload):
    """Reject a vision event that smuggles facts, clinical words, or a raw image."""
    allowed = {"frame_id", "image_width", "image_height", "detector", "vlm", "claims"}
    _require(set(payload) <= allowed, "vision payload has an unsupported field")
    frame_id = payload.get("frame_id")
    _require(isinstance(frame_id, str) and frame_id.strip(), "frame_id is required")
    _require(
        payload.get("image_width") == IMAGE_SIZE and payload.get("image_height") == IMAGE_SIZE,
        f"still must be {IMAGE_SIZE} px",
    )
    claims = payload.get("claims")
    _require(isinstance(claims, list) and claims, "vision claims are required")
    seen = set()
    for claim in claims:
        _validate_claim(claim, seen)
        if _forbidden(str(claim["value"])):
            raise ValueError("vision claim uses a forbidden clinical word")
    _validate_detector(payload.get("detector"), claims, payload.get("vlm"))
    _validate_vlm(payload.get("vlm"))


def hypothesis_event(session_id, frame_id, observed_at, claims, detector=None, vlm=None):
    payload = {
        "frame_id": frame_id,
        "image_width": IMAGE_SIZE,
        "image_height": IMAGE_SIZE,
        "claims": claims,
    }
    if detector is not None:
        payload["detector"] = detector
    if vlm is not None:
        payload["vlm"] = vlm
    validate_hypothesis_payload(payload)
    return {
        "event_id": "pending",
        "session_id": session_id,
        "type": "vision_hypothesis",
        "source": "cv_model",
        "observed_at": observed_at,
        "received_at": observed_at,
        "payload": payload,
    }
