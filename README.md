# XR-AED — dispatcher-first prototype starter

**Runtime boundary:** Meta Unity AI Speech to Text produces final transcripts. This repository validates transcript-derived facts, combines explicit help and authorized location, and formats a deterministic briefing for an AWS/Twilio test-call adapter.

## Status

This is a **design and JSON prototype**, not a Unity project, hosted AWS service, trained LLM/CV model, playable media collection, medically approved CPR script, or live emergency-response application. No test call or video stream will run simply by opening these files.

## Folders

- `knowledge-base/`: manifest, sources, clinical candidate responses, scenario evidence categories, temporary device profile, training lessons/asset placeholders and fallbacks.
- `ai/`: Meta STT input and permitted transcriber fact contract.
- `runtime/`: example Meta STT/help/location events and separate media-player state.
- `dispatch/`: fixed/evidence-based summary schema and example.
- `api/`: proposed OpenAPI contract and example HTTP requests.
- `tests/`: routing, safety and end-to-end simulation cases.
- `docs/`: team integration handoff, checklist and clinical review log.
- `scripts/`: conservative fact extraction, event validation/reduction, dispatcher formatting and checks.

## Quick checks

```bash
python3 scripts/validate.py
python3 scripts/summarize.py
```

See `RUNBOOK.md` for the current input/output boundaries, expected results, and teammate handoff.

**Safety:** Do not connect this prototype to actual emergency numbers. The `calls/test` endpoint permits only a server-resolved allowlisted `test_dispatcher`. All clinical entries are drafts and are disabled for emergency playback. Do not promote unvalidated CV observations to medical diagnoses; do not depend on the SLM to initiate calls or control an AED.
