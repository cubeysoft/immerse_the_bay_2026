# XR-AED / Dispatcher-First CPR Companion

**System architecture, clinical knowledge base, lightweight language routing, media, computer vision, AWS integration and test plan**  
**Date:** November 14, 2026 • **Audience:** Student/prototype engineering team
**Primary rescuer:** Untrained bystander • **Initial region:** United States • **Prototype headset:** Meta Quest 3  
**Status:** **DESIGN DRAFT — NOT CLINICALLY APPROVED OR DEPLOYABLE FOR LIVE EMERGENCIES**

> **The central design decision:** In an emergency, the dispatcher and AED remain the primary sources of live guidance. The AI is a narrow, auditable interface for capturing what the bystander reports, organizing limited camera observations, and preparing an evidence-labeled summary. The AI does **not** diagnose a patient, decide whether a shock is needed, or invent CPR instructions. Outside an emergency, the XR system provides an always-available CPR training library with optional videos and short clips.

## Contents

1. [One-page system overview](#1-one-page-system-overview)
2. [Goals, scope and non-goals](#2-goals-scope-and-non-goals)
3. [Component ownership and integration points](#3-component-ownership-and-integration-points)
4. [Architecture and independent channels](#4-architecture-and-independent-channels)
5. [Full workflow: training, emergency and dispatcher](#5-full-workflow-training-emergency-and-dispatcher)
6. [Knowledge-base format](#6-knowledge-base-format)
7. [Live context, provenance and event logging](#7-live-context-provenance-and-event-logging)
8. [LLM routing and deterministic safety logic](#8-llm-routing-and-deterministic-safety-logic)
9. [YOLOv9 + BlazePose integration](#9-yolov9--blazepose-integration)
10. [Unity → AWS → phone server](#10-unity--aws--phone-server)
11. [Dispatcher summaries and optional video](#11-dispatcher-summaries-and-optional-video)
12. [Media and CPR training in Quest 3](#12-media-and-cpr-training-in-quest-3)
13. [Safety, privacy, failure handling and medical limitations](#13-safety-privacy-failure-handling-and-medical-limitations)
14. [Team deliverables, sequence, testing and acceptance criteria](#14-team-deliverables-sequence-testing-and-acceptance-criteria)
15. [Open decisions](#15-open-decisions)
16. [Reference sources](#16-reference-sources)

---

## 1. One-page system overview

### Product concept

The product is a mixed-reality CPR/AED companion. The first implementation runs in Unity on a Meta Quest 3. The broader design should eventually allow a smaller, glasses-like wearable, but the current build should **not** assume that all Quest APIs or offline video features transfer to Meta glasses.

There are two fundamentally different use cases:

- **Training, available on demand:** The operator can ask to view adult, child, infant and AED lessons; pause, repeat and slow down short demonstrations; and practice on a manikin. The application can supply source-backed explanations when content has been reviewed.
- **Active emergency:** The operator is connected to a human dispatcher using a simulated phone path during development. The XR app collects bystander statements, optional validated video observations and potentially AED status. It builds a factual summary for the dispatcher. Any emergency clinical prompts must be predefined, approved and subordinate to the dispatcher and AED.

### Main end-to-end path

```text
                 META QUEST 3 / UNITY
       ┌──────────────────────────────────────┐
       │ Passthrough camera    Microphone/UI  │
       │        │                  │          │
       │   YOLOv9 + BlazePose      STT        │
       │        │                  │          │
       │  Vision observations   Rules → SLM   │
       │        └────────┬─────────┘          │
       │   Validator + context/event manager  │
       │        │                │            │
       │   Local clinical KB    Media library │
       └────────┼─────────────────────────────┘
                │ HTTPS/JSON events
                ▼
       AWS API Gateway → Lambda → DynamoDB
                │
        ┌───────┴───────────┐
        ▼                   ▼
   Summary/dashboard   Phone-service adapter
                            │
                            ▼
                      Test dispatcher

   Parallel independent channel (optional):
   headset/phone camera → authorized video service → test dispatcher

   Separate voice/media path:
   paired phone OR explicit VoIP/WebRTC bridge ↔ test dispatcher
```

The call path must **not** depend on the language model, on CV inference or on the knowledge base. Creating an AWS call request does **not** automatically connect the headset microphone and speaker to the phone call: a phone or audio bridge is a separate integration.

### Authority and precedence

1. **Patient and scene safety**; the rescuer should not enter an unsafe scene.
2. **Human dispatcher instructions** for emergency assessment and guidance; use approved local emergency dispatch practice.
3. **Actual AED prompts and manufacturer operating instructions** for device-specific analysis, shock decisions and pad/operation guidance.
4. **Preapproved supplemental clinical content**, where permitted and validated, only when it does not conflict or delay care.
5. **LLM output**: strictly non-authoritative proposals about user intent and reported facts.

This precedence is not a license for the software to override any human responder. In a conflict, suppress competing XR guidance and keep human/AED communication usable.

## 2. Goals, scope and non-goals

### Product goals

- Connect the bystander to a **simulated dispatcher** promptly, without waiting for AI inference.
- Send reliable, source-labeled information: location, what the caller said, patient responsiveness/breathing *as reported*, CPR/AED progress, relevant scene hazards.
- Support **independent video sharing** when the test dispatcher and user enable it; it should continue if the model crashes.
- Include a **small, auditable CPR knowledge base** referenced to AHA/AAP 2025, Red Cross and AED manufacturer material.
- Make CPR **learning videos available outside emergencies** even with poor/no connectivity, once local assets have been licensed and approved.
- Let each teammate integrate their code via **defined JSON contracts**, not by coupling models to one another.
- Minimize hallucinations by preferring typed events, fixed response IDs, deterministic formatting and an explicit `unknown` state.

### Non-goals for the first prototype

- Calling or routing to actual 911. Use an **allowlisted test operator/test number only**.
- Diagnosing cardiac arrest, trauma, drowning, poisoning, overdose or electrical injury from images.
- Measuring CPR compression rate or depth from BlazePose without independent validation.
- Reading ECG/rhythm or recommending/delivering a shock; no AED control interface exists yet.
- Replacing dispatcher instructions, first-responder judgment, AED prompts or formal CPR certification.
- General-purpose chat, web browsing, broad medical Q&A or open-ended treatment generation in emergency mode.
- Guaranteed precision GPS from Quest or guaranteed support for live video at real dispatch centers.

### Emergency versus training

| Feature | Training mode | Emergency simulation mode |
|---|---|---|
| Full-length CPR videos | Yes, if available/approved | No |
| Looping short clips | Yes | Disabled until separate clinical + usability approval |
| LLM | Intent/media routing; approved KB explanations | Short fact extraction and intent classification only |
| Clinical output | Source-backed training content, clearly marked | Dispatcher/AED first; approved local prompts only when explicitly enabled |
| AWS | Optional for metrics/content updates | Event storage, location, test call state, dispatcher summary |
| Camera | Optional practice overlays | Limited observational metadata; video requires separate authorization |
| Call | Not normally needed | Manual/explicitly activated independent test-dispatcher path |

The 2025 AHA resuscitation education guideline does **not** recommend cognitive aids for lay rescuers during resuscitation because of evidence of delays, although XR/VR can have value in education. Accordingly, emergency XR UI must never become a required first step before contacting help or beginning indicated care. The team must test actual delays, not only perception of usability. See source `aha_education_2025`.

## 3. Component ownership and integration points

| Teammate/component | Owns | Produces | Consumes | First handoff |
|---|---|---|---|---|
| **Vision teammate** | Quest camera → YOLOv9 → BlazePose | Timestamped person boxes and body landmarks | Camera frames + frame/camera metadata | `vision_observation` event |
| **AI/knowledge-base teammate** | Intent rules/SLM, KB, context merge, factual summary | Validated `intent`, `patient_status` etc., source-aware snapshot | Speech transcripts, typed CV events, operator input | JSON schema + reducer and mock data |
| **AWS/phone teammate** | API Gateway/Lambda/DynamoDB, simulated phone adapter, session storage, dispatcher view | Session IDs, call status, stored events, dispatch summary endpoint | HTTPS requests, authentication | Four test endpoints + test operator |
| **Unity/integration owner** | XR UX, permission flow, shared event bus, audio/media, client HTTPS | Unified on-device experience | Models, backend API, app mode | Local scene with mocked CV/AI/API |
| **Clinical reviewer (required before emergency use)** | Clinical wording, protocols, video approval, human-factors requirements | Signed content approval | KB + training media | Review checklist and approval record |

**Team contract:** every module emits data in a consistent, defined structure; no module reaches into another's private state. In particular, CV does not directly update a clinical diagnosis and the LLM does not directly call the phone service.

## 4. Architecture and independent channels

### Recommended layers

**Layer A — Device input:** camera, microphone, UI taps/voice commands, optional paired phone location, optional future AED telemetry. Timestamp all input and identify its origin.

**Layer B — Local perception:** YOLOv9 identifies person boxes; BlazePose estimates body landmarks; STT transcribes the bystander. These are raw *observations*, not clinical diagnoses.

**Layer C — Reasoning and validation:** start with deterministic rules for obvious app actions, add a tiny local SLM for ambiguous utterances, then validate JSON against a field/value allowlist. A context reducer merges accepted events.

**Layer D — Approved knowledge:** a fixed local registry contains intent IDs, candidate CPR explanations, source IDs, scenario reporting categories, fallback strings and media IDs. Draft entries are **disabled for emergency speech** until approved.

**Layer E — Communication:** Unity sends events over HTTPS to AWS. AWS maintains a canonical incident record and simulated dispatcher summary. The call is started through a **separate, authorized test-call API**. An optional secure video stream is independent.

### Three independent communication paths

```text
DATA:  Unity ── HTTPS/JSON ──> AWS session + event log ──> dispatcher UI
VOICE: paired phone or bridged VoIP ────────────────↔ test dispatcher
VIDEO: user-authorized Quest/phone capture ─ WebRTC/approved media service → test dispatcher
```

None should be represented as successful until its own transport returns a real acknowledgement/state. For example `call_requested` is not `call_connected`; `video_requested` is not `video_streaming`.

### Where to run things

- **Always local:** app mode, safety state, fixed call initiation UI, approved KB bundle, limited context store and rules baseline.
- **Prefer local:** voice intent classification, small SLM, CV (assuming the headset can sustain all concurrent loads), training videos.
- **AWS:** persist session/events, serve dispatcher simulation/dashboard, test-call integration, enforce access/consent policy and summarize verified structured fields.
- **Flexible:** live video can originate from the headset or a paired phone. It must not route through the LLM.

## 5. Full workflow: training, emergency and dispatcher

### A. Startup / normal training

1. Open the Quest Unity application and load local KB manifest, media catalog and checksums/approval flags.
2. Enter `training` mode by default. Allow voice or menu selection of adult, child, infant or AED training.
3. For “Show adult chest compressions,” classify intent `media_request` and look up the selected lesson/clip IDs in `media.json`.
4. Check that the file exists, rights are cleared, the demonstration is clinically approved and Quest can play the format.
5. Play the local clip via Unity `VideoPlayer → RenderTexture → world-space RawImage`; allow pause, replay, step navigation and optional speed controls. For CPR practice, encourage supervised manikin training with feedback where applicable.
6. When emergency mode starts, **interrupt training playback immediately**, including audio. Never require video completion to begin emergency handling.

### B. Example emergency: roadside, unresponsive person, gasping

1. Bystander: “I’m on the side of the highway; someone is unconscious.” The fixed emergency UI makes calling available **immediately**. Independently, STT and the optional SLM extract `scene.location_description = roadside` and `patient.responsive = false` **as operator reports**.
2. Unity creates a local `session_id`, enters `emergency_simulation` mode, and stops training media. The local context starts with *unknown* age group, breathing, CPR, AED and exact location, not guessed values.
3. Unity sends `POST /v1/sessions` to AWS. It can submit a paired-phone location fix with timestamp/accuracy; if none exists, leave location unknown and invite the operator to provide an address or landmark without delaying the call.
4. The user chooses to connect to the **test dispatcher** (or the controlled demonstration explicitly activates it). Unity sends `POST /v1/sessions/{id}/calls/test` with an idempotency key. AWS validates that the destination is on the *test-only allowlist*, requests the simulated call and returns status. **Do not claim actual 911 dialing.**
5. The phone/voice bridge connects the operator and test dispatcher. Neither the model nor pose pipeline is required for the call to operate.
6. The vision teammate's module sees a person and produces image-space bounding box/landmarks. This may support an overlay or a nonclinical observation such as “person detected,” but not “unconscious,” “no pulse,” “gasping,” “trauma” or “cardiac arrest.”
7. Bystander: “They’re gasping.” STT captures the utterance. Rules/SLM extract `patient.breathing = gasping`, with `source = operator_report`, `certainty = reported`, and the original evidence. The validator checks allowed fields; the context reducer adds an event and updates the current snapshot.
8. The clinical rule layer recognizes that **reported unresponsiveness with absent or abnormal breathing including gasping** meets an AHA lay-rescuer *presumed cardiac arrest* recognition trigger. This **does not** establish a cardiac cause and must not be generated from pose alone. The actual emergency treatment remains the dispatcher/AED workflow and any separately approved fixed prompts.
9. AWS receives the new event and updates the dispatcher summary: “Bystander reports an unresponsive person near a highway and now reports gasping. Patient age and cause unknown; CPR/AED status not confirmed. Exact location unknown.” This is a reported-facts summary, not a new diagnosis.
10. The dispatcher can ask additional questions, direct the bystander and—if the simulated system supports it—request an independently enabled live feed. Bystander confirmations such as “compressions started” or “pads attached” become new events.
11. App/device failure must not interrupt an existing independent call or ordinary AED operation. If a model fails, only optional AI summaries stop or fall back to validated rules.

### C. Clinical recognition boundary

- **An unresponsive adult who is absent/abnormally breathing or only gasping:** under the AHA 2025 adult BLS lay-rescuer recommendations, presume cardiac arrest and start the prescribed response; do not ask a layperson to check a pulse. See `aha_adult_2025`.
- **Unresponsive alone:** breathing is still unknown; do not assert cardiac arrest.
- **Gasping alone:** record exactly what the operator said and assess other missing information. Do not conclude a cause.
- **Age unknown:** never silently treat all patients as adults. Select age-specific material only with adequate patient information or validated clinical escalation handling.
- **Roadside location:** may imply a hazard but **not** a confirmed traffic collision or trauma.
- **Drowning/electrocution/overdose/smoke exposure:** report witness testimony and scene evidence, not a diagnosis inferred from proximity/appearance. See `aha_special_2025`.
- **Pulse / shock indication:** a layperson should not be routed to an unsolicited pulse check; only the real AED determines whether it advises a shock.

### D. Workflow event sequencing

Store ordered events with both `observed_at` (when the event was captured) and `received_at` (when it reached the app/backend). Handle events that arrive late. Do not let a stale camera frame override a more recent operator statement. Keep conflicting reports rather than silently replacing history.

## 6. Knowledge-base format

### Recommended repository layout

```text
xr-aed/
├── DESIGN.md                         ← THIS master design document
├── README.md
├── knowledge-base/
│   ├── manifest.json                 ← jurisdiction, approval + policy gates
│   ├── sources.json                  ← URLs and source registry
│   ├── clinical.json                 ← age-specific, source-backed response drafts
│   ├── scenarios.json                ← possible cause categories / evidence rules
│   ├── device.json                   ← Quest 3 / placeholder AED / future glasses
│   ├── media.json                    ← lessons, clip IDs, local assets, rights status
│   └── fallback.json                 ← approved-path failure/unknown responses
├── ai/
│   └── transcriber-contract.json     ← Meta STT input + allowed dispatcher facts
├── runtime/
│   ├── events.example.json           ← help, Meta STT, location and call events
│   └── media-state.example.json      ← separate training player state
├── dispatch/
│   ├── summary-schema.json           ← no clinical diagnosis, provenance required
│   └── summary.example.json
├── api/
│   ├── openapi.yaml                   ← Unity ↔ AWS interface proposal
│   └── request-examples.json
├── tests/
│   ├── routing.json
│   ├── safety.json
│   └── integration-scenarios.json
├── docs/
│   ├── TEAM_HANDOFF.md
│   ├── IMPLEMENTATION_CHECKLIST.md
│   └── CLINICAL_REVIEW_LOG.md
└── scripts/
    ├── transcriber.py
    ├── incident.py
    ├── dispatcher.py
    ├── validate.py
    └── summarize.py
```

**Why five/six clinical JSON modules, not many per-age documents?** With a small prototype, combining adults/children/infants in one `clinical.json` avoids duplicating common CPR concepts. Each entry carries `patient` eligibility. When a clinical owner determines the content is too large, split by age while preserving stable IDs. A vector database is unnecessary here; simple local dictionary lookups by ID/intent will be faster and more auditable.

### `manifest.json`: approval gate

```json
{
  "region": "US",
  "audience": "untrained_bystander",
  "status": "prototype_draft",
  "clinical_approval": {"status": "not_approved", "reviewer": null},
  "safety_policy": {
    "dispatcher_first": true,
    "clinical_generation_allowed": false,
    "clinical_response_playback_enabled": false
  }
}
```

The actual file has additional fields. **A source-backed draft is not an approved clinical response**. Emergency delivery must be blocked until a designated clinical reviewer signs each entry and the full workflow is validated.

### `sources.json`: document registry

Each source should have `id`, `publisher`, `title`, `url`, `kind` and review notes. Sources should be linked from every clinical response and scenario category by ID. The initial registry includes AHA 2025 Adult BLS, Pediatric BLS, Special Circumstances and Resuscitation Education Science; American Red Cross CPR/AED guides; 911.gov; Meta; Unity; AWS.

### `clinical.json`: one intent, context-specific candidate instruction

```json
{
  "id": "cpr.rate",
  "intent": "compression_rate",
  "patient": ["adult", "child", "infant"],
  "stage": "cpr",
  "say": "Aim for 100 to 120 chest compressions per minute. Let the chest rise fully between compressions.",
  "sources": ["aha_adult_2025", "aha_pediatric_2025"],
  "approval": "draft_not_for_emergency_use",
  "emergency_output_enabled": false
}
```

The production authoring process must link precise recommendation sections, region applicability, effective dates and clinical sign-off. The current entries are starting points and should be clinically re-reviewed against the full recommendations; never copy them directly into a live resuscitation device.

**Basic knowledge areas:** scene safety, check responsiveness, normal versus agonal breathing, call for help, adult compression technique, pediatric/infant compressions and breaths, AED on/pad placement/clear/resume, approved escalation rules. Store patient-specific applicability explicitly; do not rely on the LLM to guess.

### `scenarios.json`: support uncertain etiologies

Contains reporting categories for possible cardiac arrest, drowning, electrocution, overdose, smoke inhalation and traumatic injury. Each includes evidence fields and source IDs. The model can **extract a witness statement** (“I saw them fall into the pool”), but it may not assign a confirmed cause. Even if a category is highly plausible, the dispatcher receives *reported/possible*, not *definitely*. Some special-circumstance protocols differ from basic CPR, so only approved clinical rules should offer treatment advice.

### `device.json`: capabilities and limitations

Keep temporary Meta Quest 3 hardware as a separate profile, and leave AED manufacturer/model, telemetry and shock-control fields unset. Do not equate display/camera/hand-tracking support with validated medical sensing. Track headset, SDK and OS build identifiers, permissions, audio path and source of location. Future Meta Ray-Ban Display may require a phone companion app, display SDK or standalone web app, rather than the same Unity runtime.

### `media.json`: lessons versus clips

Store adult, child, infant and AED full lessons plus steps such as hand placement, compressions, rescue breaths, AED pad placement and clearing for analysis. Each clip has a stable ID and placeholder `local_path`, availability, `rights` and `clinical_approval`. **No source videos are bundled.** External links are for reference only, not automatic rights to embed/copy. A clinically approved short demonstration can be connected to a `clinical_entry_id`, but its availability never changes the clinical facts.

### `fallback.json`: explicit no-answer handling

- Unsupported general question → short out-of-scope response.
- Missing/unapproved clinical answer → do not improvise; defer to dispatcher/AED.
- Noisy STT → ask for repetition only if it does not impede the emergency workflow.
- Camera fails → remove vision claims; human reports and voice call remain.
- Local SLM fails → deterministic rules and call path remain.
- Local media missing → show lesson unavailable; no online dependence for emergency use.

## 7. Live context, provenance and event logging

### Why context must be separate from the KB

The KB is relatively static and source-controlled. `context` changes minute to minute during a particular incident: age group, responsiveness, normal breathing status, reported cause clues, whether help has been called, whether CPR has started, AED presence, approximate location, communication status. This should be built by a **context manager** from approved events, not by asking the LLM what the current scene "probably" is.

### The `unknown` rule

`unknown` / `null` is not the same as `false`.

- Unknown `incident.help_requested` means the explicit help control has not been observed.
- Unknown `patient.breathing` ≠ not breathing.
- Unknown `aed.pads_attached` ≠ pads not attached.
- Unknown age ≠ adult.
- Camera does not see the patient's chest ≠ no breathing.

### Event vs. snapshot

**Append-only event** is the source of truth: exactly what arrived, from which sensor/operator, at what time. **Context snapshot** is the current best representation derived from accepted events. Snapshots are rebuildable after a crash, and conflicts are visible in the event log.

Example event (`runtime/events.example.json` contains the full series):

```json
{
  "event_id": "evt_003",
  "session_id": "sim_demo_001",
  "type": "patient_status",
  "source": "operator_report",
  "observed_at": "2026-11-14T19:00:08Z",
  "received_at": "2026-11-14T19:00:08Z",
  "payload": {
    "transcript": "They are gasping.",
    "facts": [{"field": "patient.breathing", "value": "gasping", "evidence": "They are gasping."}]
  }
}
```

Keep evidence spans/transcripts for audit only when authorized and privacy policy permits. Most routine processing can use structured extracted fields. Never send continuous raw images to DynamoDB as ordinary JSON telemetry.

### Provenance tiers

| Source | Examples | Appropriate claim |
|---|---|---|
| `operator_report` | “They are gasping” | “Bystander reports gasping” |
| `dispatcher_confirmed` | Human operator repeats/verifies | “Dispatcher confirmed [reported fact]” |
| `cv_model` | Person box, body landmarks | “CV detected a person in frame” |
| `companion_phone` | Location fix with accuracy | “Phone location fix: lat/lon, ± accuracy” |
| `aed_telemetry` | Future verified connected AED | “AED telemetry reports pads connected” |
| `unknown` | No signal | “Not yet confirmed” |

Do not create `dispatcher_confirmed` automatically from the fact that a summary was sent; confirmation must be a separate explicit event.

### Conflict resolution

If early speech says "breathing normally" and later speech says "only gasping," preserve **both reports**. The latest credible report can drive the snapshot with its timestamp, but the history must show the change and any contradiction. Do not let a CV confidence number automatically outweigh an eyewitness report. Maintain expiry rules for transient CV observations.

## 8. Meta STT handoff and deterministic fact extraction

### Runtime boundary

Meta Unity AI Speech to Text owns microphone audio → final transcript. This repository begins with that final transcript. It preserves the raw text, provider, confidence when supplied, speaker and timestamps, then proposes a small set of dispatcher facts. A lightweight model may help with unresolved phrasing, but it never transcribes audio, activates help, chooses a destination or generates the Twilio briefing.

**Suggested MVP plan:**

1. The explicit help control emits `incident.help_requested=true` without STT or a model.
2. Unity emits only final Meta STT transcripts; interim text stays UI-only.
3. Deterministic rules propose common patient, location, CPR/AED and witnessed-scene facts.
4. An optional constrained model may propose facts for unresolved language.
5. Validate field values, source authority, session and timestamps before reduction.
6. Preserve the raw transcript even when no structured fact is accepted.
7. Compose `spoken_text` from explicit help, location and validated reports; extraction failure cannot block the test call.

### Example: reported uncertainty

**User:** “I don't think he's breathing.”  
**Bad extraction:** `breathing = absent`, `certainty = verified`  
**Correct extraction:** `breathing = uncertain` with the original phrase preserved; dispatcher/approved workflow can clarify immediately if clinically appropriate.

**User:** “Someone's on the side of the highway, unconscious.”  
**Bad:** `confirmed_trauma = true`, `cardiac_arrest = true`, `adult = true`.  
**Correct:** `scene.location_description = roadside` and `patient.responsive = false` **as reported**; age, breathing and cause remain unknown.

### Runtime budget

Quest 3 also runs passthrough, Unity graphics, YOLOv9, BlazePose, Meta STT, networking and UI. Benchmark total RAM, CPU/GPU time, thermals, battery, camera frame rate and end-to-end latency with *all components active*. Do not promise a specific model latency without measurement. Set deadlines per task, prioritize call/audio over inference, skip frames if vision falls behind, and keep the main Unity render thread free.

Meta's current AI Building Block documentation describes STT using cloud providers. Treat it as network-dependent until the selected provider is tested otherwise. If it fails, explicit help, authorized location and the call path still operate.

## 9. YOLOv9 + BlazePose integration

### Pipeline

```text
Quest PassthroughCameraAccess (timestamp / intrinsics / frame)
    → YOLOv9 person detection (bbox, class, confidence)
    → crop / track IDs / suitable input preprocessing
    → BlazePose 33 body landmarks, visibility scores
    → overlay + typed `vision_observation` event
    → (optionally) context fields narrowly allowlisted as CV observations
```

**A pose skeleton is not an X-ray.** BlazePose gives inferred body **landmarks/joints in image coordinates**, not measured bone locations and not medical imaging. Even a visually accurate skeleton cannot certify head/neck/spinal injury, breathing, consciousness, pulse, CPR depth or an electrical shock indication.

A minimal CV output in `runtime/events.example.json` uses a normalized `[xmin, ymin, xmax, ymax]` bounding box and 2D landmark coordinates. Specify the coordinate system and timestamp explicitly to avoid 2D/3D ambiguity. If you later create a 3D overlay, document camera intrinsics/extrinsics, depth estimation method, coordinate transforms and tracking accuracy separately.

### Data sharing policy

Send **metadata and selected observations** to the context manager, not a full frame at every inference. Video sharing uses a separate opt-in streaming path. If a person is not visible, label it as “not detected in this frame,” not “there is no patient.” Suppress observations that are stale, low-confidence, out-of-frame or produced when tracking is lost.

### Practical handoff requirements

The vision teammate should supply:

- Function/interface that ingests a Quest camera frame and returns a typed detection list.
- Timestamp, frame ID, image size, camera identity and coordinate convention.
- YOLO class/box/confidence, BlazePose landmark list with confidence/visibility and stable per-person tracking ID when possible.
- Ability to stop/throttle inference, handle absent person/occlusion and return an explicit error state.
- Profiling results on Quest 3 with Unity plus the other runtime components.

Use Meta's latest Passthrough Camera API guidance for Quest 3, camera permissions, supported camera resolutions and `PassthroughCameraAccess`; do not assume an obsolete `WebCamTexture` example is suitable for a new build.

## 10. Unity → AWS → phone server

### Recommended MVP backend

```text
UnityWebRequest HTTPS client
    → AWS API Gateway (auth, throttling, validation)
    → Lambda (request checks, idempotency, business logic)
    → DynamoDB (sessions, events, location, call status)
    → test-call adapter (Amazon Connect or other approved test provider)
    → test dispatcher operator / dashboard
```

Start with the smallest number of endpoints:

| Method/path | Role | Response semantics |
|---|---|---|
| `POST /v1/sessions` | Create an emergency *simulation* session; send coarse location if available | `201 Created`, returns `session_id` |
| `POST /v1/sessions/{id}/events` | Store a typed event with `event_id`, timestamps and source | `202 Accepted`; retries are idempotent |
| `POST /v1/sessions/{id}/calls/test` | Ask for a **test-only** call to an allowlisted destination | `202 call_requested`, not automatically connected |
| `GET /v1/sessions/{id}` | Retrieve latest simulated status/snapshot | `200 OK` |
| `GET /v1/sessions/{id}/summary` | Retrieve dispatcher-ready evidence-labeled summary | `200 OK` |

`api/openapi.yaml` and `api/request-examples.json` contain the handoff specification. In production engineering, secure requests with short-lived device/user authorization tokens, HTTPS, server-side allowlists, request validation and rate limits; keep all telephony secrets on the backend.

### What the phone server actually does

An Amazon Connect `StartOutboundVoiceContact` request or comparable telephony-provider call can place outbound contact to a configured phone endpoint. **This does not cause the Quest speakers and microphone to join that call automatically.** Choose one audio design explicitly:

1. **Simplest demonstration:** paired phone places or receives simulated dispatcher call; Quest independently submits telemetry to AWS.
2. **More advanced:** WebRTC/VoIP or a provider SDK bridges headset microphone/speaker to the phone service; build and test echo cancellation, call state, Bluetooth/audio focus, permissions and reconnection.

In both cases, do not let the LLM decide whether to connect or dial. The test-call endpoint must accept **only allowlisted simulation destinations**. Never route prototype traffic to 911. A legitimate real 911 integration would require emergency-service carrier/PSAP coordination and regulatory review, not just replacing the dialed number.

### Location and storage

Treat location as **device-supplied evidence**, not as something AWS can determine precisely from an HTTP request. A paired phone's location (subject to permission), an authorized location service, or an operator-reported address can be supplied to Unity/AWS. Store `lat`, `lon`, `accuracy_m`, `source`, `captured_at` and a textual description; leave unknown fields null. For a roadside incident, highway/direction/mile-marker reported by the operator can matter as much as raw coordinates.

DynamoDB can hold one session item, individual immutable event items and a derived summary item. Apply TTL/retention policies according to the pilot consent and security plan. Do not put unencrypted raw medical media in a publicly accessible bucket.

### Idempotency and retries

`event_id` uniquely identifies the logical event, and `Idempotency-Key` uniquely identifies a simulated call request. Retries should not create duplicate incident facts or repeated calls. Queue locally only under an explicit retention/consent policy; if offline, mark dispatch as **not connected** instead of giving a false success indicator.

### Minimal Unity client implementation concept

Use `UnityWebRequest.Post(url, jsonBody, "application/json")` or upload handler with JSON content type. Run asynchronously, set a timeout, check `request.result`, and parse the HTTP response. Do not hardcode API secrets in the mobile client; protect endpoints and keys through an appropriate identity/auth flow. A small code skeleton is in `docs/TEAM_HANDOFF.md`.

## 11. Dispatcher summaries and optional video

### Summarizer should be deterministic

Use `context.json` + a fixed template or schema-driven formatter. The language model is **not needed** to rewrite a medical report; in fact, free-form rewriting risks changing qualifiers such as “maybe,” “I think,” and “reportedly.” Include the source next to clinically significant facts.

Example simulation summary:

```text
[SIMULATED DISPATCHER REPORT]
Location: Roadside (reported). Exact coordinates unknown.
Patient: Bystander reports unresponsive; age unknown.
Breathing: Bystander reports gasping.
CPR: Not confirmed.
AED: Not confirmed.
Cause: Unknown. No witnessed crash or other cause established.
```

Never say “confirmed cardiac arrest” when you only have bystander reports and limited vision. A deterministic clinical engine might separately flag an **AHA recognition criterion** as met for approved workflow gating, but the dispatcher summary should preserve factual wording and evidence.

### Summary update policy

- First summary when a session is created, indicating unknown values plainly.
- Event-driven updates for material changes: breathing report, CPR started/stopped, AED attached, new scene hazard, changed location, dispatcher connection.
- Deduplicate repeated content; do not spam every CV frame or verbal filler.
- Show `reported`, `observed_unverified` and `verified` rather than a synthetic single model “certainty score.”
- Make summary delivery status explicit (`prepared`, `queued`, `sent`, `acknowledged`, `failed`).
- Keep `spoken_text` free of hardware terms (`camera`, `passthrough`, `CV`, `in frame`). Include reported patient demographics (`patient.sex`, `patient.age_group`, `patient.approximate_age`) from human reports only, never CV. When object detection cannot identify the background setting, resolve location from the operator's statement or authorized device geo data (`companion_phone` / `headset_service`), or leave location unconfirmed for the operator to state.

### Video sharing

Live video is **separate** from the LLM, events API and phone call. With proper authorization, Quest passthrough or a paired phone could publish via a compatible WebRTC/media service to the test dispatcher. Maintain explicit user consent, visible capture indicators, transmission encryption, access limits, stop controls and a reasonable retention policy. Do not silently send an emergency stream to any general-purpose AI provider.

Actual US PSAP support for caller video varies. NG911 aims to support multimedia, but **do not claim that every 911 center accepts this application's video or structured data**. Implement only a simulated endpoint until a real agency approves and tests an integration.

## 12. Media and CPR training in Quest 3

### Player design

The learning library should be visible at startup, not behind an emergency session. On Quest 3 use Unity `VideoPlayer` with local MP4 files, an assigned `RenderTexture` and a world-space UI over passthrough. Provide large accessible controls: play/pause, replay current step, previous/next step, speed when the player and encoding support it, and close. Avoid screen clutter or occluding the patient's body/manikin during practice.

**Training videos:** complete lesson, detailed pacing, narration and context.  
**Short clips:** independent approved demonstrations for a specific gesture, e.g., hand placement, compressions, breaths, pad placement. Choose actual clip lengths during instructional/clinical review rather than imposing arbitrary medical timing.

A lesson contains stable `clinical_entry_ids` and `step_clip_ids`; an asset record points to a local file only after the file exists, licensing is cleared and a clinical reviewer has approved current technique. No external YouTube or course footage is automatically licensed for redistribution.

### Availability

“Available all the time” should mean **on-demand while the application is operational**, including no network if the media is bundled locally. It does not imply a permanent OS-level overlay or infinite battery life. If an emergency is activated, stop the video and audio immediately. Any emergency visual aid would need a separate safety review and demonstration that it does not delay care.

### Future glasses

For Meta Ray-Ban Display, investigate the Meta Wearables Device Access Toolkit and/or supported standalone display web apps. Some Meta Ray-Ban glasses have **no display** and therefore cannot show an in-lens CPR video. Design the `media.json` lesson/clip identifiers to be platform-independent; provide platform-specific renderers. Confirm each device's content, offline and SDK constraints experimentally.

## 13. Safety, privacy, failure handling and medical limitations

### Fail-safe matrix

| Condition | Correct behavior |
|---|---|
| LLM is slow/crashes | Test call and AED remain independent; rules-only path and existing voice call continue |
| STT mishears/uncertain | Preserve original, qualify assertion, ask only safe minimal question; do not confirm apnea |
| Vision detects lying person | Report detected person/pose only; do not infer unconsciousness or injury |
| Vision loses tracking | Expire CV observation; do not infer absence of patient |
| Model says “deliver shock” | Reject; AED alone advises shock via its certified workflow |
| Clinical KB has no approved entry | No open-ended LLM answer; fixed fallback and dispatcher |
| User reports “gasping” | Store `operator_report`; reviewed recognition rules may treat it as abnormal breathing in unresponsive person |
| Training video playing when emergency begins | Stop immediately; no required video setup |
| AWS offline | Mark server disconnected; do not claim call created or location transmitted |
| Test call requested twice | Backend idempotency returns existing call reference; no duplicate dial |
| Call connected but model fails | Call remains connected; disable AI summary updates gracefully |
| Dispatcher and XR guidance conflict | Suppress optional XR prompts, keep dispatcher/AED accessible |
| Wrong/unknown age | Do not auto-select adult/infant instructions |
| No exact geo fix | Send `unknown` plus operator-provided landmark, not fabricated coordinates |
| User refuses video permission | Continue call and context reporting without video |

### Privacy/security checklist

- Explicit camera/microphone and media-sharing permissions; separate consent for transmitting video and for saving data.
- Treat patient speech, images, location and incident history as sensitive; minimize collection and avoid including unneeded identity details.
- TLS for network requests; encryption at rest for any retained sensitive information; role-based access, audit logs and short-lived credentials.
- Never put telephony provider keys or AWS administrative credentials in Unity assets.
- Define retention/deletion rules and access policy before any human-subject testing; use synthetic/demo data until approved.
- Have a plan for false reports, denial-of-service, prompt injection (“ignore medical rules”) and server-side duplicate/late events.
- Legal/compliance review is required for real deployment, and integration with an AED may constitute regulated medical-device functionality. Do not claim regulatory clearance from this prototype.

### Clinically sensitive limitations

The 2025 AHA Adult BLS guideline supports presuming cardiac arrest for an unresponsive adult with absent or abnormal breathing, including gasping, and does not require laypersons to check a pulse. Pediatric recommendations differ in technique and ventilation importance. Special-circumstance events can further alter professional care. **These rules must be mapped and signed off by qualified clinical reviewers before being converted into operational software.** For a live incident, follow emergency-service guidance and the AED's own instructions rather than experimental XR prompts.

## 14. Team deliverables, sequence, testing and acceptance criteria

### Recommended implementation phases

**Phase 0 — Agree on interfaces (everyone):** Freeze event field names, Meta STT payload, timestamp semantics, `unknown` behavior, call status enumeration and simulation-only safeguards. Check in test fixtures and validators.

**Phase 1 — Unity ↔ AWS with mocks:** Launch Unity scene, emit explicit help, POST authorized location and a mocked final Meta STT transcript, store events and show the summary. Phone server returns `requested`/`connected` as separate simulated states. Verify failure and idempotency.

**Phase 2 — Working phone audio:** First run a paired-phone call or intentional VoIP bridge, with bidirectional audio independently tested. Do not mark call “connected” based only on POST success.

**Phase 3 — Vision:** Integrate camera permission and latest Meta API, YOLOv9 person detections and BlazePose landmark output to a Unity overlay/event emitter. Use synthetic data until robust inference is ready.

**Phase 4 — AI/KB:** Connect Meta's `SpeechToTextAgent` final-transcript callback to typed fact extraction, provenance-preserving context and the fixed summary formatter. Benchmark any optional extractor under combined load, including negation/uncertainty.

**Phase 5 — Training media:** Attach one licensed, current, clinically approved local demo clip to `media.json`; complete pause/replay and emergency interruption, then add full lessons.

**Phase 6 — Optional live video:** Add authorized video-to-test-dispatcher path, separate from model and telephony, with consent and network-failure handling.

**Phase 7 — Safety/human factors:** Simulated lay-rescuer trials measuring delays, accuracy, workload and false assertions. Clinical/device/regulatory approval is a separate gate before any real emergency use.

### Suggested acceptance criteria (engineering targets, not clinical validation)

| Area | Demo acceptance test |
|---|---|
| Session | `POST /sessions` returns stable ID; no duplicate records from retries |
| Call | User can reach the test operator with LLM and CV disabled |
| Audio | Two-way conversation works using the chosen explicit audio path |
| Events | Explicit help, final Meta STT transcripts and location arrive with IDs, provenance and timestamps |
| Context | Unknown age/breathing/AED state remain unknown unless source reports otherwise |
| Safety | LLM cannot emit new clinical wording or authorize a shock |
| Vision | Overlay uses body landmarks; no claim of actual bone mapping or vital-sign determination |
| Dispatcher | Factual summary can be regenerated from accepted events alone |
| Training | Preapproved local clip opens, pauses, replays and stops on emergency mode transition |
| Video | Authorized stream works even with LLM stopped; refused permission prevents stream |
| Offline | User sees truthful connectivity status; no false “911 called” message |

### Suggested metrics to measure

- Time from user activation to *call UI available*, call requested, actual two-way audio connected.
- Time to initiate indicated CPR in controlled simulation with and without XR, not just inference latency.
- Meta STT + fact extraction accuracy on accents, background noise, partial sentences and negation.
- Factual precision, missing-context rate, unsupported medical-claim rate; ideally **zero unsupported clinical assertions** in validation trials.
- Vision frame timing, tracking loss, false detection rate; total GPU/CPU/RAM, battery/thermal impact with everything active.
- Dispatcher summary correctness and change-detection; duplicate updates and stale-event handling.
- User success completing training media navigation and understanding that videos do not replace supervised skills practice.

### Useful command-line checks

From the project root:

```bash
python scripts/validate.py
python scripts/summarize.py
```

These perform structural consistency checks and generate an example factual briefing only. They are **not** clinical validation or a functional voice/AWS/headset implementation.

## 15. Open decisions

1. **Phone audio path:** Paired phone for first demo, or a fully bridged VoIP/headset audio solution? This is the most important non-AI integration choice.
2. **Location source:** Phone geolocation, operator text, supported headset service or both? Define displayed uncertainty and consent.
3. **Who owns context reducer:** Unity C# service versus a portable local library; AWS should mirror accepted events, not be required for local safety logic.
4. **Meta STT provider:** Select and configure the Unity provider; confirm credentials, latency, transcript metadata and network-failure behavior on Quest 3.
5. **Vision exposure:** Which CV fields (if any) are included in dispatcher summaries, and who validates their operational reliability?
6. **AED vendor/model:** Without it, do not promise live AED phase or pad/shock telemetry.
7. **Dispatcher simulation UI:** Web dashboard only, combined phone UI or both? How does a real operator acknowledge a summary?
8. **Training footage ownership:** Create your own clips, license third-party clips, or use official links only during development? Review updates against 2025 technique.
9. **Data governance:** Who may access incident location/images, and what is the retention/deletion policy?
10. **Clinical review owner:** A designated person must approve response text, age-specific rules, fallback behavior and usability findings before live deployment.

## 16. Reference sources

These official resources were checked for the design, but links are **not** endorsements of this prototype, medical approvals or media-redistribution licenses. The machine-readable list is in [`knowledge-base/sources.json`](knowledge-base/sources.json).

**Clinical / emergency:**

- American Heart Association — [2025 Adult Basic Life Support](https://cpr.heart.org/en/resuscitation-science/cpr-and-ecc-guidelines/adult-basic-life-support).
- American Heart Association / American Academy of Pediatrics — [2025 Pediatric Basic Life Support](https://cpr.heart.org/en/resuscitation-science/cpr-and-ecc-guidelines/pediatric-basic-life-support).
- American Heart Association — [2025 Adult and Pediatric Special Circumstances of Resuscitation](https://cpr.heart.org/en/resuscitation-science/cpr-and-ecc-guidelines/adult-and-pediatric-special-circumstances-of-resuscitation/).
- American Heart Association — [2025 Resuscitation Education Science](https://cpr.heart.org/en/resuscitation-science/cpr-and-ecc-guidelines/resuscitation-education-science).
- American Red Cross — [Adult CPR steps](https://www.redcross.org/take-a-class/cpr/performing-cpr/cpr-steps) and [AED steps](https://www.redcross.org/take-a-class/aed/using-an-aed/aed-steps).
- 911.gov — [Calling 911](https://www.911.gov/calling-911/) and [Next Generation 911](https://www.911.gov/issues/ng911/).

**Technology / integration:**

- Meta — [Passthrough Camera API overview](https://developers.meta.com/vr/documentation/unity/unity-pca-overview/) and [Unity setup](https://developers.meta.com/vr/documentation/unity/unity-pca-documentation/).
- Meta — [YOLOv9 object detection sample](https://developers.meta.com/vr/documentation/unity/unity-sample-camera-object-detection/) and [Unity Inference Engine / local SLM support](https://developers.meta.com/vr/documentation/unity/unity-ai-unity-inference-engine/).
- Meta — [Wearables Developer FAQ](https://developers.meta.com/wearables/faq/).
- Unity — [UnityWebRequest](https://docs.unity3d.com/6000.0/Documentation/ScriptReference/Networking.UnityWebRequest.html) and [VideoPlayer RenderTexture guide](https://docs.unity3d.com/Manual/VideoPlayer-rendertexture.html).
- AWS — [API Gateway, Lambda and DynamoDB HTTP API tutorial](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-dynamo-db.html) and [Amazon Connect outbound voice API](https://docs.aws.amazon.com/connect/latest/APIReference/API_StartOutboundVoiceContact.html).

---

### Bottom line

Keep the clinical KB **small, controlled and approved**, the LLM **small and non-authoritative**, the CV **observational**, the context **evidence-labeled**, the AWS system **event-driven**, and the dispatcher call **independent of AI**. For the prototype, prove this architecture using a **simulated** dispatcher and intentionally restricted test-only telephony before exploring real emergency-service integration.
