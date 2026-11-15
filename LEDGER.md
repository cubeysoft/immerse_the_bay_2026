# Project ledger

## Current state
- 2026-11-14 [CODE] Runtime begins after Meta Unity AI Speech to Text. `scripts/transcriber.py` extracts conservative facts from final transcripts, `scripts/incident.py` validates/reduces explicit help, transcript, location, AED and call events, and `scripts/dispatcher.py` creates deterministic `spoken_text` for Twilio.
- 2026-11-14 [CODE] `ai/transcriber-contract.json`, `dispatch/summary-schema.json`, and `api/openapi.yaml` define the Unity → AWS boundary. Raw final transcripts are retained with speaker, provider, confidence and timestamp.
- 2026-11-14 [CODE] Unity Meta STT integration, AWS API Gateway/Lambda/DynamoDB endpoints, and Twilio outbound test-call adapter remain unbuilt.

## Implemented
- 2026-11-14 [CODE] Removed runtime intent/media/clinical-question routing, local STT assumptions, CV background handling, medical recognition flags, `ai/intents.json`, `ai/router-config.json`, and the redundant derived `runtime/context.example.json`.
- 2026-11-14 [CODE] Added explicit app-owned `incident.help_requested`, generic `speech_transcript` events for Meta STT output, final/interim validation, STT metadata validation and structured `transcripts` in dispatcher summaries.
- 2026-11-14 [CODE] Twilio briefing order is now explicit help → operator/device location → optional patient/scene facts. It does not infer help from speech and still produces a useful briefing when STT is unavailable.
- 2026-11-14 [CODE] Updated runtime/API/summary fixtures, 36 exact transcript cases, safety/integration scenarios, `README.md`, `DESIGN.md`, team handoff and implementation checklist for the Meta STT boundary.
- 2026-11-14 [CODE] Removed project release labels and schema release fields. Required OpenAPI format metadata remains.
- 2026-11-14 [CODE] Removed redundant `scene.roadside`, `response.help_called`, `operator_confirmed` and `inferred_place` state. Roadside is represented by `scene.location_description`; explicit help uses only `incident.help_requested`; location provenance comes from `source`.
- 2026-11-14 [CODE] Added `RUNBOOK.md` with the commands that work now, expected results, live input/output boundaries, and Unity/AWS/Twilio integration responsibilities. `README.md` links to it.
- 2026-11-14 [CODE] Removed server-derived `facts` from the example Unity event request and clarified in `api/openapi.yaml` that the future backend adapter owns transcript extraction before reduction.

## Decisions and blockers
- 2026-11-14 [USER] Meta Unity AI Speech to Text owns audio transcription; this runtime must keep only the downstream transcript-to-call work.
- 2026-11-14 [CODE] Help is explicit app state, never inferred from speech or an LLM. Location comes from operator speech or authorized `companion_phone` / `headset_service` coordinates, never CV background or IP geolocation.
- 2026-11-14 [CODE] Vision remains a separate teammate integration and is not part of the transcript-to-Twilio event contract.
- 2026-11-14 [CODE] The deterministic extractor is intentionally conservative, not general language understanding. Unsupported or multi-patient language stays unresolved; production still requires an ASR/noise/accents corpus and a constrained extraction fallback evaluated against it.
- 2026-11-14 [CODE] The live Unity payload contains final transcript metadata, not trusted patient facts. Server-side extraction must preserve the raw text and attach proposed facts before `incident.py` reduces the event.
- 2026-11-14 [ASSUMPTION] Session audio path uses an allowlisted Twilio test call on a paired phone (`destination_id: "test_dispatcher"`, `simulation_only: true`); real 911 remains out of scope.
- 2026-11-14 [CODE] Clinical guidance entries remain unapproved (`docs/CLINICAL_REVIEW_LOG.md`); emergency clinical playback stays disabled.

## Verification
- 2026-11-14 [TOOL] Ran Python compilation and `python3 scripts/validate.py` — passed the Meta STT boundary, 36 exact transcript cases, explicit-help separation, location fallback, invalid/interim event rejection, provenance, conflicts and Twilio briefing checks.
- 2026-11-14 [TOOL] Ran `python3 scripts/summarize.py` — observed help and location first, retained transcript counts, and no medical recognition/CPR boilerplate.
- 2026-11-14 [TOOL] Simulated Meta STT unavailable with help + device location; output was: “Simulated emergency briefing. Emergency assistance requested. Device location: near 450 Serra Mall, within 12 meters. Patient responsiveness and breathing not confirmed.”
- 2026-11-14 [TOOL] Validated `dispatch/summary.example.json` against its Draft 2020-12 schema, parsed `api/openapi.yaml`, and checked edited files with IDE diagnostics; all passed.
- 2026-11-14 [TOOL] Re-ran compilation, 36 transcript cases, schema validation and demo output after cleanup; behavior was unchanged.
- 2026-11-14 [TOOL] Re-ran `python3 scripts/validate.py` and `python3 scripts/summarize.py` while preparing `RUNBOOK.md`; both passed under Python 3.12.2.
- 2026-11-14 [TOOL] Parsed the updated API request fixture and checked `RUNBOOK.md`, `README.md`, `LEDGER.md`, and API contract files with IDE diagnostics; no errors were found.

## Next steps
- [ ] 2026-11-14 [CODE] Unity teammate: connect Meta `SpeechToTextAgent` final-result callback to `speech_transcript` in `api/openapi.yaml`; include provider ID and confidence if exposed.
- [ ] 2026-11-14 [CODE] Build a controlled Meta STT corpus from simulated operator/dispatcher audio, including ASR errors, accents, corrections, questions and multiple people; measure exact-field precision/recall and unsupported-fact rate.
- [ ] 2026-11-14 [CODE] Add a constrained extraction fallback for utterances that deterministic rules leave unresolved; require the same `incident.py` validation and never let model output bypass source/value checks.
- [ ] 2026-11-14 [CODE] Build the AWS HTTP handlers (or local staging server) matching `api/openapi.yaml` (`POST /v1/sessions`, `POST /v1/sessions/{id}/events`, `POST /v1/sessions/{id}/calls/test`, `GET /v1/sessions/{id}`, `GET /v1/sessions/{id}/summary`) using `scripts/incident.py` and `scripts/dispatcher.py`.
- [ ] 2026-11-14 [CODE] Wire the allowlisted Twilio test-call adapter to speak `summary.spoken_text` via `<Say>` only after the call reaches `connected`, with `Idempotency-Key` deduplication.
- [ ] 2026-11-14 [CODE] Keep the vision teammate's Quest passthrough work on a separate interface; do not add CV observations to `spoken_text`.
