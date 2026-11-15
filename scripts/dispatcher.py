#!/usr/bin/env python3
"""Build the deterministic briefing handed to the Twilio adapter."""

from incident import (
    PERMITTED_FACT_FIELDS,
    SOURCE_CERTAINTY,
    parse_timestamp,
    validate_fact_value,
)


FORBIDDEN_SPOKEN_TERMS = (
    "camera",
    "passthrough",
    "cv_model",
    "yolov9",
    "blazepose",
    "object detection",
    "in frame",
)

TRACKED_UNKNOWN_FIELDS = (
    "incident.help_requested",
    "patient.responsive",
    "patient.breathing",
)

SOURCE_LABELS = {
    "operator_report": "Bystander reports",
    "dispatcher_confirmed": "Dispatcher confirms",
    "aed_telemetry": "AED reports",
}

SCENE_LABELS = {
    "scene.witnessed_submersion": "submersion",
    "scene.recovered_from_water": "patient recovered from water",
    "scene.witnessed_drug_use": "witnessed drug use",
    "scene.witnessed_electrical_contact": "electrical contact",
    "scene.exposed_electrical_hazard": "an electrical hazard",
    "scene.reported_smoke_exposure": "smoke exposure",
    "scene.visible_smoke": "visible smoke",
    "scene.witnessed_crash_or_fall": "a crash or fall",
}


def resolve_location(context):
    location = context["location"]
    reported = context["facts"]["scene.location_description"]
    reported_description = (
        reported["value"]
        if reported["source"] in {"operator_report", "dispatcher_confirmed"}
        else None
    )

    if reported_description:
        if reported_description == "roadside":
            spoken = "Caller reports roadside location; exact address unconfirmed."
            description = "roadside; exact location unconfirmed"
        else:
            spoken = f"Caller reports location: {reported_description}."
            description = reported_description
        return {
            "lat": None,
            "lon": None,
            "accuracy_m": None,
            "source": reported["source"],
            "captured_at": reported["observed_at"] or location["captured_at"],
            "description": description,
            "resolution_basis": "operator_report",
            "spoken_clause": spoken,
        }

    has_geo = (
        location["source"] in {"companion_phone", "headset_service"}
        and location["lat"] is not None
        and location["lon"] is not None
    )
    if has_geo:
        place = location["description"] or f"{location['lat']:.4f}, {location['lon']:.4f}"
        accuracy = location["accuracy_m"]
        accuracy_text = (
            f", within {int(round(accuracy))} meters" if accuracy is not None else ""
        )
        return {
            "lat": location["lat"],
            "lon": location["lon"],
            "accuracy_m": accuracy,
            "source": location["source"],
            "captured_at": location["captured_at"],
            "description": f"Device location: {place}",
            "resolution_basis": "geo_inferred",
            "spoken_clause": f"Device location: {place}{accuracy_text}.",
        }

    return {
        "lat": None,
        "lon": None,
        "accuracy_m": None,
        "source": "unknown",
        "captured_at": None,
        "description": None,
        "resolution_basis": "unknown",
        "spoken_clause": "Location unconfirmed; caller needs to state an address or landmark.",
    }


def _format_patient_value(field, value):
    if field == "patient.approximate_age":
        return f"approximately {value} years old"
    if field in {"patient.age_group", "patient.sex"}:
        return value
    if field == "patient.responsive":
        if value is True:
            return "responsive"
        if value is False:
            return "unresponsive"
        return "responsiveness uncertain"
    if field == "patient.breathing":
        return {
            "normal": "breathing normally",
            "absent": "not breathing",
            "gasping": "gasping",
            "abnormal": "breathing abnormally",
            "uncertain": "breathing uncertain",
        }[value]
    raise ValueError(f"unsupported patient field: {field}")


def _patient_clauses(facts):
    patient_fields = (
        "patient.approximate_age",
        "patient.age_group",
        "patient.sex",
        "patient.responsive",
        "patient.breathing",
    )
    grouped = {}
    for field in patient_fields:
        fact = facts[field]
        if fact["value"] is not None:
            grouped.setdefault(fact["source"], []).append((field, fact["value"]))

    clauses = []
    for source in ("dispatcher_confirmed", "operator_report"):
        values = grouped.get(source)
        if not values:
            continue
        fields = {field for field, _ in values}
        descriptions = [
            _format_patient_value(field, value)
            for field, value in values
            if not (
                field == "patient.age_group"
                and "patient.approximate_age" in fields
            )
        ]
        clauses.append(f"{SOURCE_LABELS[source]}: {'; '.join(descriptions)}.")
    return clauses


def _scene_clauses(facts):
    grouped = {}
    for field, label in SCENE_LABELS.items():
        fact = facts[field]
        if fact["value"] is True:
            grouped.setdefault(fact["source"], []).append(label)

    exposure = facts["scene.reported_substance_exposure"]
    if exposure["value"]:
        grouped.setdefault(exposure["source"], []).append(
            f"possible substance exposure ({exposure['value']})"
        )
    injury = facts["scene.reported_injury"]
    if injury["value"]:
        grouped.setdefault(injury["source"], []).append(injury["value"])

    clauses = []
    for source in ("dispatcher_confirmed", "operator_report"):
        values = grouped.get(source)
        if values:
            clauses.append(f"{SOURCE_LABELS[source]}: {', '.join(values)}.")
    return clauses


def _intervention_clauses(facts):
    grouped = {}
    labels = {
        "response.cpr_started": {True: "CPR started", False: "CPR not started"},
        "aed.available": {True: "AED available", False: "no AED available"},
        "aed.powered_on": {True: "AED powered on", False: "AED not powered on"},
        "aed.pads_attached": {True: "AED pads attached", False: "AED pads not attached"},
    }
    for field, value_labels in labels.items():
        fact = facts[field]
        if fact["value"] is not None:
            grouped.setdefault(fact["source"], []).append(value_labels[fact["value"]])

    clauses = []
    for source in ("aed_telemetry", "dispatcher_confirmed", "operator_report"):
        values = grouped.get(source)
        if values:
            clauses.append(f"{SOURCE_LABELS[source]}: {', '.join(values)}.")
    return clauses


def _conflict_clauses(context):
    conflict_fields = {conflict["field"] for conflict in context["conflicts"]}
    clauses = []
    for field in ("patient.responsive", "patient.breathing", "response.cpr_started"):
        if field not in conflict_fields:
            continue
        current = context["facts"][field]
        label = field.split(".")[-1].replace("_", " ")
        value = (
            _format_patient_value(field, current["value"])
            if field.startswith("patient.")
            else ("started" if current["value"] else "not started")
        )
        clauses.append(f"Reports conflict on {label}; latest report says {value}.")
    return clauses


def _transcripts(context):
    transcripts = []
    for event in context["event_history"]:
        if event["type"] != "speech_transcript":
            continue
        payload = event["payload"]
        transcripts.append(
            {
                "event_id": event["event_id"],
                "source": event["source"],
                "observed_at": event["observed_at"],
                "text": payload["transcript"],
                "stt_provider": payload["stt_provider"],
                "confidence": payload.get("confidence"),
            }
        )
    return transcripts


def validate_summary(summary):
    required = {
        "summary_id",
        "session_id",
        "created_at",
        "simulation_only",
        "location",
        "facts",
        "unknown_fields",
        "conflicts",
        "transcripts",
        "spoken_text",
        "note",
    }
    if set(summary) != required:
        raise ValueError(f"summary fields differ from contract: {set(summary) ^ required}")
    if summary["simulation_only"] is not True:
        raise ValueError("summary must be simulation-only")
    parse_timestamp(summary["created_at"])

    location = summary["location"]
    location_fields = {
        "lat",
        "lon",
        "accuracy_m",
        "source",
        "captured_at",
        "description",
        "resolution_basis",
    }
    if set(location) != location_fields:
        raise ValueError(
            f"summary location fields differ from contract: {set(location) ^ location_fields}"
        )
    if location["captured_at"] is not None:
        parse_timestamp(location["captured_at"])

    for fact in summary["facts"]:
        if fact["field"] not in PERMITTED_FACT_FIELDS:
            raise ValueError(f"summary contains unsupported field: {fact['field']}")
        validate_fact_value(fact["field"], fact["value"])
        if SOURCE_CERTAINTY.get(fact["source"]) != fact["certainty"]:
            raise ValueError(
                f"summary certainty does not match source for {fact['field']}"
            )
        parse_timestamp(fact["observed_at"])

    for transcript in summary["transcripts"]:
        parse_timestamp(transcript["observed_at"])
        if not transcript["text"].strip():
            raise ValueError("summary contains empty transcript")

    spoken = summary["spoken_text"].lower()
    for term in FORBIDDEN_SPOKEN_TERMS:
        if term in spoken:
            raise ValueError(f"spoken_text contains forbidden hardware term: {term}")


def compose_summary(context, summary_id="summary_001", created_at="2026-11-14T19:00:13Z"):
    facts = context["facts"]
    location = resolve_location(context)
    location_clause = location.pop("spoken_clause")

    summary_facts = []
    for field in sorted(facts):
        fact = facts[field]
        if fact["value"] is not None:
            summary_facts.append(
                {
                    "field": field,
                    "value": fact["value"],
                    "source": fact["source"],
                    "certainty": fact["certainty"],
                    "observed_at": fact["observed_at"],
                }
            )

    unknown_fields = [
        field for field in TRACKED_UNKNOWN_FIELDS if facts[field]["value"] is None
    ]
    if location["resolution_basis"] == "unknown":
        unknown_fields.append("location")

    spoken_parts = ["Simulated emergency briefing."]
    if facts["incident.help_requested"]["value"] is True:
        spoken_parts.append("Emergency assistance requested.")
    else:
        spoken_parts.append("Help request not confirmed.")
    spoken_parts.append(location_clause)
    spoken_parts.extend(
        _patient_clauses(facts)
        or ["Patient responsiveness and breathing not confirmed."]
    )
    spoken_parts.extend(_scene_clauses(facts))
    spoken_parts.extend(_conflict_clauses(context))
    spoken_parts.extend(_intervention_clauses(facts))

    summary = {
        "summary_id": summary_id,
        "session_id": context["session_id"],
        "created_at": created_at,
        "simulation_only": True,
        "location": location,
        "facts": summary_facts,
        "unknown_fields": unknown_fields,
        "conflicts": context["conflicts"],
        "transcripts": _transcripts(context),
        "spoken_text": " ".join(spoken_parts),
        "note": (
            "Deterministic simulated dispatcher briefing from explicit help, location, "
            "and source-labelled reports. Not a medical diagnosis."
        ),
    }
    validate_summary(summary)
    return summary
