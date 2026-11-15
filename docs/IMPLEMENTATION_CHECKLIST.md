# Prototype implementation checklist

These are engineering gates, not medical clearance.

## Before integration

- [ ] Freeze `api/openapi.yaml` and the event envelope.
- [ ] Confirm current source documents and the approved clinical content review owner.
- [ ] Confirm a **simulated** operator/test call number is the only backend dial destination.
- [ ] Decide headset audio path: paired phone vs. actual VoIP bridge.
- [ ] Define whether phone or headset supplies location; include source/accuracy/permission.
- [ ] Build mocks for Meta STT unavailable, location unavailable and phone service failure.

## Local Quest app

- [ ] Camera access with correct Meta SDK and permission behavior.
- [ ] YOLOv9 and BlazePose emit time-stamped, typed observations.
- [ ] Meta Unity `SpeechToTextAgent` emits final transcripts with provider metadata.
- [ ] Explicit help control emits `incident.help_requested=true` without STT or LLM.
- [ ] Raw final transcripts retain speaker, provider, confidence and timestamps.
- [ ] Backend context manager builds a snapshot from accepted events.
- [ ] Rules-only emergency/call path is accessible without LLM.
- [ ] SLM outputs strict schema; validator rejects clinical prose and invalid fields.
- [ ] A source-backed local KB can be queried by stable response ID.
- [ ] Unapproved clinical entries cannot be spoken during emergency mode.
- [ ] Training assets are locally playable only with proper approval/rights.
- [ ] Training playback immediately interrupts on emergency activation.
- [ ] Combined performance benchmark: camera + CV + Meta STT + optional extractor + network + render.

## AWS / test dispatcher

- [ ] Authenticated API Gateway endpoint with input validation/rate limiting.
- [ ] Lambda creates session + append-only events with idempotency.
- [ ] DynamoDB stores source and timestamp, not just model-generated narrative.
- [ ] Location retains source/accuracy/time and `unknown` fields.
- [ ] Twilio briefing starts with explicit help status and location before optional patient facts.
- [ ] Test-only call request enforced server-side; idempotent duplicate requests.
- [ ] Separate status: requested/ringing/connected/ended/failed.
- [ ] Two-way call audio actually works; never just assume API accepted means connected.
- [ ] Dispatcher summary is generated from fields with provenance, without model diagnosis.
- [ ] Optional authorized WebRTC/video stream independent of the LLM.

## Failure/validation

- [ ] Unknown not conflated with false.
- [ ] Interim Meta STT transcripts are not persisted as final facts.
- [ ] Speech cannot set the explicit app help flag.
- [ ] “Roadside” never promoted to “car crash.”
- [ ] Gasping report is labeled operator-reported; no CV-based breathing diagnosis.
- [ ] No pose landmarks interpreted as actual bones or medical vitals.
- [ ] No AED shock-control inference; real AED guidance is authoritative.
- [ ] No new clinical instructions generated for missing KB topics.
- [ ] With LLM and CV disabled, simulated call still functions.
- [ ] With AWS unreachable, app does not claim a dispatcher connection.
- [ ] With video unavailable/refused, voice call still functions.
- [ ] Duplicate events/call requests are not repeated.
- [ ] Clinical reviewer approves patient-specific content and media before any non-demo use.
- [ ] Human-factors trials assess whether the XR UI delays calling or CPR.
