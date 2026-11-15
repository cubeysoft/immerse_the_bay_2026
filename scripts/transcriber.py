#!/usr/bin/env python3
"""Convert operator or dispatcher speech into conservative structured facts."""

import re


NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}

HUMAN_SPEECH_SOURCES = {"operator_report", "dispatcher_confirmed"}


def _split_clauses(text):
    normalized = text.replace("’", "'")
    parts = re.split(r"[.;!?]+|\b(?:but|however|although|then)\b", normalized, flags=re.IGNORECASE)
    return [part.strip(" ,") for part in parts if part.strip(" ,")]


def _age_group(years):
    if years < 1:
        return "infant"
    if years <= 12:
        return "child"
    if years <= 17:
        return "adolescent"
    return "adult"


def _extract_age(text):
    lower = text.lower()
    month_match = re.search(r"\b(\d{1,2})\s*[- ]?\s*months?\s+old\b", lower)
    if month_match:
        return 0, "infant", month_match.group(0)

    number = r"(?:\d{1,3}|" + "|".join(NUMBER_WORDS) + r")"
    year_match = re.search(
        rf"\b(?:about|around|approximately)?\s*({number})\s*[- ]?\s*(?:years?|yrs?)\s*[- ]?\s*old\b",
        lower,
    )
    if not year_match:
        return None

    token = year_match.group(1)
    years = int(token) if token.isdigit() else NUMBER_WORDS[token]
    if years > 130:
        return None
    return years, _age_group(years), year_match.group(0)


def _extract_location(text):
    lower = text.lower()
    if re.search(r"\b(?:highway|roadside|freeway|side of the road)\b", lower):
        return "roadside"

    location_match = re.search(
        r"\b(?:we are at|we're at|i am at|i'm at|located at|location is|we are in|outside)"
        r"\s+(.+?)(?=,\s*(?:and\s+)?(?:this is|there is|he is|she is|they are|it is|"
        r"the patient|someone|the person)|[.;!?]|$)",
        text,
        flags=re.IGNORECASE,
    )
    if not location_match:
        return None
    return location_match.group(1).strip(" ,")


def _extract_demographics(text, add_fact):
    lower = text.lower()
    age = _extract_age(text)
    if age:
        years, group, evidence = age
        add_fact("patient.approximate_age", years, evidence)
        add_fact("patient.age_group", group, evidence)
    elif re.search(r"\b(?:infant|baby|newborn)\b", lower):
        add_fact("patient.age_group", "infant")
    elif re.search(r"\b(?:child|kid|toddler)\b", lower):
        add_fact("patient.age_group", "child")
    elif re.search(r"\b(?:teenager|adolescent)\b", lower):
        add_fact("patient.age_group", "adolescent")
    elif re.search(r"\b(?:adult|elderly)\b", lower):
        add_fact("patient.age_group", "adult")

    female_patterns = (
        r"\b(?:adult|elderly)\s+(?:female|woman)\b",
        r"\b(?:female|woman|girl)\s+(?:patient|person|victim)\b",
        r"\b(?:patient|person|victim)\s+(?:is|appears to be)\s+(?:a\s+)?(?:female|woman|girl)\b",
        r"\b\d{1,3}\s*[- ]?\s*(?:year|yr)s?\s*[- ]?\s*old\s+girl\b",
        r"\bthis is (?:an?\s+)?(?:adult\s+)?(?:female|woman)\b",
    )
    male_patterns = (
        r"\b(?:adult|elderly)\s+(?:male|man)\b",
        r"\b(?:male|man|boy)\s+(?:patient|person|victim)\b",
        r"\b(?:patient|person|victim)\s+(?:is|appears to be)\s+(?:a\s+)?(?:male|man|boy)\b",
        r"\b\d{1,3}\s*[- ]?\s*(?:year|yr)s?\s*[- ]?\s*old\s+boy\b",
        r"\bthis is (?:an?\s+)?(?:adult\s+)?(?:male|man)\b",
    )
    if any(re.search(pattern, lower) for pattern in female_patterns):
        add_fact("patient.sex", "female")
    elif any(re.search(pattern, lower) for pattern in male_patterns):
        add_fact("patient.sex", "male")
    elif re.search(r"\b(?:nonbinary|non-binary)\s+(?:patient|person)\b", lower):
        add_fact("patient.sex", "other")


def _extract_responsiveness(clause):
    lower = clause.lower()
    if (
        re.search(r"\b(?:was|were|had been)\s+(?:unconscious|unresponsive|awake|responsive)\b", lower)
        and not re.search(r"\b(?:still|now|currently)\b", lower)
    ):
        return None
    if re.search(
        r"\b(?:do not know|don't know|not sure|uncertain|cannot tell|can't tell)"
        r"\b.*\b(?:awake|responsive|conscious|responding)\b",
        lower,
    ):
        return "uncertain"
    if re.search(r"\b(?:not|isn't|is not|no longer)\s+(?:unconscious|unresponsive)\b", lower):
        return True
    if re.search(r"\b(?:not|isn't|is not)\s+(?:awake|responsive|conscious|responding)\b", lower):
        return False
    if re.search(r"\b(?:unconscious|unresponsive|passed out)\b", lower):
        return False
    if re.search(r"\b(?:awake|conscious|responsive|alert|talking|responding)\b", lower):
        return True
    return None


def _extract_breathing(clause):
    lower = clause.lower()
    if (
        re.search(r"\b(?:was|were|had been)\s+(?:gasping|breathing)\b", lower)
        and not re.search(r"\b(?:still|now|currently)\b", lower)
    ):
        return None
    if re.search(
        r"\b(?:do not know|don't know|do not think|don't think|not sure|uncertain|cannot tell|can't tell|hard to tell)"
        r"\b.*\bbreath",
        lower,
    ):
        return "uncertain"
    if re.search(r"\b(?:not breathing normally|breathing is not normal)\b", lower):
        return "abnormal"
    if re.search(r"\b(?:not breathing|no breathing|stopped breathing)\b", lower):
        return "absent"
    if re.search(r"\b(?:breathing normally|normal breathing|breathing fine|breathing okay)\b", lower):
        return "normal"
    if re.search(r"\b(?:not|no longer)\s+gasping\b|\bgasping\s+stopped\b", lower):
        return None
    if re.search(r"\b(?:gasping|agonal)\b", lower):
        return "gasping"
    if re.search(
        r"\b(?:abnormal|labored|shallow|barely|irregular|slow|noisy)\s+breathing\b"
        r"|\bbreathing\s+(?:abnormally|barely|irregularly|slowly)\b",
        lower,
    ):
        return "abnormal"
    return None


def _extract_cpr(clause):
    lower = clause.lower()
    if re.search(r"\b(?:do not|don't|should not|shouldn't)\s+(?:start|do)\s+(?:cpr|compressions)\b", lower):
        return None
    if re.search(r"\b(?:restarted|resumed|started|doing|performing)\s+(?:cpr|chest compressions|compressions)\b", lower):
        return True
    if re.search(r"\b(?:cpr|chest compressions|compressions)\s+(?:started|resumed|are underway)\b", lower):
        return True
    if re.search(r"\b(?:stopped|paused)\s+(?:cpr|chest compressions|compressions)\b", lower):
        return False
    if re.search(r"\b(?:not doing|isn't doing|is not doing)\s+(?:cpr|compressions)\b", lower):
        return False
    return None


def _extract_aed(clause):
    lower = clause.lower()
    facts = {}
    if re.search(r"\b(?:no|do not have|don't have|without)\s+(?:an?\s+)?(?:aed|defibrillator)\b", lower):
        facts["aed.available"] = False
    elif re.search(
        r"\b(?:have|got|brought)\s+(?:an?\s+)?(?:aed|defibrillator)\b"
        r"|\b(?:aed|defibrillator)\s+(?:is\s+)?(?:here|available)\b",
        lower,
    ):
        facts["aed.available"] = True

    if re.search(r"\b(?:pads?|electrodes?)\s+(?:are\s+)?(?:not|aren't)\s+(?:on|attached)\b", lower):
        facts["aed.pads_attached"] = False
    elif re.search(r"\b(?:pads?|electrodes?)\s+(?:are\s+)?(?:on|attached)\b", lower):
        facts["aed.pads_attached"] = True

    if re.search(r"\b(?:aed|defibrillator)\s+(?:is\s+)?(?:not|isn't)\s+(?:on|powered on)\b", lower):
        facts["aed.powered_on"] = False
    elif re.search(r"\b(?:aed|defibrillator)\s+(?:is\s+)?(?:on|powered on)\b", lower):
        facts["aed.powered_on"] = True
    return facts


def _extract_scene(clause, add_fact):
    lower = clause.lower()
    if re.search(r"\b(?:pulled|removed|recovered|rescued)\s+from\s+(?:the\s+)?water\b", lower):
        add_fact("scene.recovered_from_water", True, clause)
        add_fact("scene.witnessed_submersion", True, clause)
    elif re.search(r"\b(?:submerged|underwater|went under water|fell into (?:the )?water)\b", lower):
        add_fact("scene.witnessed_submersion", True, clause)

    if re.search(r"\b(?:overdose|overdosed|took drugs?|used drugs?|opioid|fentanyl|heroin|pills?)\b", lower):
        match = re.search(r"\b(?:overdose|overdosed|opioid|fentanyl|heroin|pills?|drugs?)\b", lower)
        add_fact("scene.reported_substance_exposure", match.group(0) if match else "reported substance exposure", clause)
    if re.search(r"\b(?:saw|watched|witnessed)\b.*\b(?:take|use|inject|swallow)\b.*\b(?:drug|pill|opioid|heroin|fentanyl)\b", lower):
        add_fact("scene.witnessed_drug_use", True, clause)

    if re.search(r"\b(?:shocked|electrocuted|touched|contact with)\b.*\b(?:wire|power|electric|outlet)\b", lower):
        add_fact("scene.witnessed_electrical_contact", True, clause)
    if re.search(r"\b(?:live wire|downed power line|electrical hazard|exposed wire)\b", lower):
        add_fact("scene.exposed_electrical_hazard", True, clause)

    if re.search(r"\b(?:visible smoke|smoke in the room|room is smoky|building is on fire)\b", lower):
        add_fact("scene.visible_smoke", True, clause)
        add_fact("scene.reported_smoke_exposure", True, clause)
    elif re.search(r"\b(?:smoke inhalation|inhaled smoke|exposed to smoke)\b", lower):
        add_fact("scene.reported_smoke_exposure", True, clause)

    injury_match = re.search(
        r"\b((?:severe|heavy|major)\s+bleeding(?:\s+[a-z]+\s+injury)?"
        r"|bleeding\s+[a-z]+\s+injury|[a-z]+\s+injury)\b",
        lower,
    )
    if injury_match:
        add_fact("scene.reported_injury", injury_match.group(1), clause)
    if re.search(r"\b(?:from a fall|fell|witnessed a crash|car crash|hit by a car)\b", lower):
        add_fact("scene.witnessed_crash_or_fall", True, clause)


def extract_transcript_facts(transcript, source="operator_report"):
    """Extract conservative facts from one final Meta Unity STT transcript."""
    if source not in HUMAN_SPEECH_SOURCES:
        raise ValueError(f"unsupported speech source: {source}")

    text = (transcript or "").strip()
    lower = text.lower()
    if not text:
        return {
            "source": source,
            "facts": [],
            "unresolved": ["empty_transcript"],
        }
    status_question = bool(
        re.search(
            r"^(?:is|are|was|were|do|does|did|can|could|has|have)\s+"
            r"(?:he|she|they|the patient|the person|this patient)\b",
            lower,
        )
        or (
            text.endswith("?")
            and re.search(
                r"\b(?:patient|person|awake|responsive|unconscious|breathing|gasping|cpr|aed)\b",
                lower,
            )
        )
    )
    if status_question:
        return {
            "source": source,
            "facts": [],
            "unresolved": ["question_not_fact"],
        }

    facts = {}
    unresolved = []

    def add_fact(field, value, evidence=text):
        facts[field] = {"field": field, "value": value, "evidence": evidence.strip()}

    _extract_demographics(text, add_fact)
    location = _extract_location(text)
    if location:
        add_fact("scene.location_description", location)

    for clause in _split_clauses(text):
        responsive = _extract_responsiveness(clause)
        if responsive is not None:
            add_fact("patient.responsive", responsive, clause)

        breathing = _extract_breathing(clause)
        if breathing is not None:
            add_fact("patient.breathing", breathing, clause)

        cpr_started = _extract_cpr(clause)
        if (
            cpr_started is None
            and "response.cpr_started" in facts
            and re.search(r"\b(?:restarted|resumed)\s+(?:it|them)\b", clause, re.IGNORECASE)
        ):
            cpr_started = True
        if cpr_started is not None:
            add_fact("response.cpr_started", cpr_started, clause)

        for field, value in _extract_aed(clause).items():
            add_fact(field, value, clause)
        _extract_scene(clause, add_fact)

    multiple_patients = bool(
        re.search(r"\b(?:two|multiple|another)\s+(?:people|patients|victims|persons)\b", lower)
    )
    if multiple_patients:
        unresolved.append("multiple_patients")
        facts = {
            field: fact
            for field, fact in facts.items()
            if field.startswith("scene.")
        }

    return {
        "source": source,
        "facts": list(facts.values()),
        "unresolved": unresolved,
    }
