# Vision plan

**Stage 2 of the Quest pipeline.**
**Date:** November 14, 2026
**Status:** The look, the one-second cutoff, and corroboration are implemented. Not clinically approved. A model sentence is still not a patient fact.

The code is `ai/vision-contract.json`, `scripts/vision.py`, and `scripts/assess_still.py`. YOLOv9 itself stays on the Quest. This repository accepts the detector's person count and, when that count is not zero, runs moondream2. `spoken_text` is unchanged.

Stage 1 is already specified: the Quest microphone becomes a final transcript (`operator_report` or `dispatcher_confirmed`), `scripts/transcriber.py` proposes a few explicit facts, and `scripts/dispatcher.py` speaks only those facts plus the dispatcher’s own words. This document is the next stage. The headset camera is used to look at the scene quickly. The look-up is a hypothesis. It becomes support for a fact only when a finished operator or dispatcher line already says the same thing.

This plan supplements `DESIGN.md` section 9. It does not change the audio contract in `api/openapi.yaml`, and it does not put camera wording into `spoken_text`.

## Decision

Use two models, with different jobs.

1. **YOLOv9 person detection, on the Quest, every few frames.** This is the fast check: is a person in view, where, and did the count change. Meta already publishes a Quest sample for this. It returns boxes, not sentences, and it is fast enough to run beside passthrough and speech-to-text.
2. **A small vision-language model on a selected still, off the headset, at most one call at a time.** This is the situation read: a short closed-vocabulary description of that still. The model to prototype is **moondream2**. **KOSMOS-2** is the alternate if the useful output is a box tied to a phrase. **Qwen-VL** is an offline accuracy check on the same stills, not the live path.

The call, the microphone, and `spoken_text` do not wait on either model. A late or failed vision result is dropped. A vision result never creates `incident.help_requested`, a breathing value, a responsiveness value, a location, or a diagnosis.

## What “assess the situation” means

The situation read answers a short list of visual questions. It does not answer clinical ones.

Allowed claims, each with value `yes`, `no`, or `unclear` unless noted:

| Claim | Meaning | May be marked corroborated |
|---|---|---|
| `person_visible` | At least one person is in the still. | Only by speech that a person is there. `no` does not mean there is no patient. |
| `person_count` | Integer, or `unclear`. Cap stored value at 5; above that store `many`. | Only by speech that states a count. |
| `posture` | `upright`, `seated`, `reclined`, or `unclear`. A visual description of the body in the still. | Only by speech that describes the same posture, such as “lying down.” |
| `aed_like_object` | A boxy device with pads or a typical AED shape is visible. | `yes` can support `aed.available=true` after someone says an AED is there. `no` supports nothing. |
| `smoke_visible` | Smoke or heavy haze is visible. | `yes` can support `scene.visible_smoke=true` after speech says smoke is visible. `no` supports nothing. |

Forbidden claims, rejected if the model emits them:

- consciousness, responsiveness, breathing, gasping, pulse, cardiac arrest, “dead,” “alive”
- age, sex, weight, identity
- injury, bleeding, trauma, overdose, drowning, electrocution
- shock advice, pad placement quality, CPR depth or rate
- address, coordinates, “this is a car crash”
- any sentence that is not one of the keys above

`posture=reclined` is not `patient.responsive=false`. A person lying down may be resting, injured, or in arrest. The transcript is what decides responsiveness. Water in the background does not set `scene.witnessed_submersion`. A dark object is not an AED until the claim is `aed_like_object=yes` and a person has said an AED is present.

Absence is not a negative fact. `person_visible=no`, `aed_like_object=no`, and `smoke_visible=no` mean “not seen in this still.” They must not clear a fact the operator or dispatcher already stated.

## Which model, from the vision-language model survey

The comparison set is the open models in [Vision Language Models Explained](https://huggingface.co/blog/vlms) (Hugging Face, 11 April 2024). That post is an overview, not a medical benchmark. It also points at a later update. Before anyone downloads weights, re-read the model card for license, size, and prompt format. The choice below uses only the models named on that page, judged against this emergency loop: one still, a tiny JSON answer, a hard time limit, and no license that blocks a student prototype.

| Model | Size and resolution on that page | Why it does or does not fit |
|---|---|---|
| [moondream2](https://huggingface.co/vikhyatk/moondream2) | about 2B, 378×378, permissive | **Use this first.** Smallest practical model on the page, so it is the only one with a chance of returning a short answer inside an emergency time budget on a laptop. The page does not list grounding. We do not need grounding if YOLOv9 already supplies the box. |
| [KOSMOS-2](https://huggingface.co/microsoft/kosmos-2-patch14-224) | about 2B, 224×224, permissive, grounding and zero-shot detection | **Alternate, not the default.** Grounding is useful because the model points at a region instead of only talking. 224 px is a poor fit for a small AED or smoke in a Quest frame. Switch to it only if moondream2’s answers cannot be pinned to the YOLO person box. |
| [Qwen-VL](https://huggingface.co/Qwen/Qwen-VL) | 4B, 448×448, permissive, zero-shot detection | **Offline comparison.** Higher resolution and detection support make it the right model to score against moondream2 on saved stills. Too large to sit on the live deadline. The chat checkpoint is unnecessary if the live prompt is one fixed JSON question. |
| [DeepSeek-VL](https://huggingface.co/deepseek-ai/deepseek-vl-7b-chat) and the base checkpoint | 7B, 384×384, permissive | Out. Several times the weight of moondream2 for the same kind of caption. Chat does not add the corroboration rule; code does. |
| [CogVLM](https://huggingface.co/THUDM/cogvlm-chat-hf) | 17B, 490×490, permissive, grounding and chat | Out for the live path. Grounding is already covered, more cheaply, by KOSMOS-2 plus YOLO. |
| [LLaVA 1.6 34B](https://huggingface.co/llava-hf/llava-v1.6-34b-hf) and [Yi-VL-34B](https://huggingface.co/01-ai/Yi-VL-34B) | 34B, permissive | Out. The page lists them as high-capacity models. A 34B generate step will miss the time budget and will not fit beside the rest of the demo. English-only is enough here; Yi-VL’s Chinese support is unused. |
| [Fuyu-8B](https://huggingface.co/adept/fuyu-8b) | 8B, 300×300, **not** marked permissive, text inside the image | Out. The page marks the license as not permissive. Reading text in the scene is also the wrong feature: it invites the model to transcribe shirt logos, phone screens, or device labels and treat them as facts. |

The page’s leaderboards (Vision Arena, Open VLM Leaderboard, MMMU, MMBench) rank general visual question answering. They do not measure “did this model falsely say the person is unconscious.” A high leaderboard score is not a reason to move a larger model onto the live path. The acceptance test for this project is the unsupported-claim rate on our own stills, plus the time to a schema-valid answer.

## Where it runs

Quest 3 is already responsible for passthrough, Unity, and Meta speech-to-text. `knowledge-base/device.json` still says the headset needs hardware benchmarks. Do not put moondream2 on the Quest for this stage.

```text
Quest passthrough
    → YOLOv9 person box on device (fast, local)
    → keep the newest person box
    → every so often, downscale one still to 378 px
    → send that JPEG plus frame id and time to the laptop running this repo
    → moondream2 returns JSON claims
    → corroboration joins those claims to final transcripts
    → spoken_text stays on the stage-1 path
```

The laptop is the same machine that already stands in for speech with `scripts/transcribe_audio.py`. Run moondream2 locally. Do not send emergency or demo frames to a hosted Hugging Face inference API. `DESIGN.md` already forbids silently sending the camera stream to a general-purpose provider.

YOLOv9 stays on the headset because a box is cheap and the decision to spend a VLM call depends on it. BlazePose stays out of this stage. Landmarks are not needed for the five claims above, and they are easy to misread as breathing or pulse.

## Speed

These are budgets to measure, not numbers already observed.

| Step | Budget | If it misses |
|---|---|---|
| YOLO person box on Quest | under 100 ms per processed frame | Skip frames. Never block the render thread or the microphone. |
| Choose a still, downscale to 378 px, JPEG | under 100 ms | Send nothing this cycle. |
| One still across a local network | under 100 ms | Drop it. Do not retry a stale still. |
| moondream2, one image, at most 80 new tokens | 1 second, then the audio briefing stands | Drop the still. Do not queue it. |
| Corroboration in Python | under 20 ms | This is table lookup, not a model. |

The implemented budget is **1 second**, and `scripts/assess_still.py` counts weight loading inside it. If the weights are still loading at 1 second, `look_at` returns `mode: audio`, nothing is written into the session, and the process exits without waiting for the load. A newer still is not started while that call is still running; it also stays on the audio briefing.

Measured on this Mac on November 14, 2026, with torch 2.5.1 and transformers 5.0.0. moondream2 revision `2025-06-21` (Apache-2.0) loaded on CPU in about 5 seconds. One 378 px still took about 25 seconds and did not return a schema-valid answer: CPU bfloat16 attention produced a non-finite first logit. With the load inside the budget, `scripts/assess_still.py` on a 32 px stand-in still returned `audio` / `timeout` at `latency_ms` 1000 and the process exited in about 1.2 seconds. MPS was not used. The checkpoint moves one pooled tensor onto MPS whenever MPS exists, and an MPS run produced non-finite sampling probabilities. CUDA is used when it exists. This machine has none, so a live look here keeps the transcript. The demo commands never start this load.

Rules that keep the loop fast:

- At most one VLM call in flight. A newer still cancels the older one.
- Do not run the VLM on every camera frame. Send a still when emergency mode starts and a person box has been stable for about 300 ms. Send another only if the person count changes, or 5 seconds have passed, whichever comes first.
- If YOLO sees no person, do not spend a VLM call. Store `person_visible=no` from the detector, with the detector’s name, and leave the other claims unset.
- Downscale before the image leaves the headset. The model’s input is 378 px. Shipping a full passthrough frame adds delay and retains more of the scene than the model can use.
- Fixed prompt, fixed keys, tiny `max_new_tokens`. A paragraph caption is a failed call.
- The test-call request is already allowed to proceed with no vision result. Keep it that way.

## Corroboration

A model sentence is not a fact. The only statements that can support a fact are final transcript lines whose speaker is `operator_report` or `dispatcher_confirmed`, and whose extracted fact is the same field and a compatible value. Alignment is a table in code. A second model must not judge whether the image and the sentence “seem to match.”

### What the camera is allowed to support

| Vision claim | Transcript fact that can corroborate it | Compatible values |
|---|---|---|
| `aed_like_object=yes` | `aed.available` | speech value `true` |
| `smoke_visible=yes` | `scene.visible_smoke` | speech value `true` |
| `person_visible=yes` | no patient field | only a future explicit “a person is here” phrase, if one is added to `scripts/transcriber.py` |
| `posture=reclined` (or `upright`, `seated`) | no patient field | only speech that uses the same posture words (“lying down,” “on the ground,” “sitting,” “standing”) |
| `person_count` | no patient field | only speech that states the same count |

`patient.responsive`, `patient.breathing`, age, sex, location, help, CPR, and every other field in `ai/transcriber-contract.json` have **no** vision row. Speech fills them exactly as it does today. Vision cannot confirm “unconscious,” and it cannot contradict it.

Negative vision values never corroborate a negative speech value. “I do not see an AED” plus the operator saying nothing leaves `aed.available` unknown. “I do not see an AED” plus the operator saying “there’s an AED in the lobby” leaves the operator’s fact in place and marks the vision claim as a conflict, not as a correction.

### When a claim’s status changes

Every claim starts as `uncorroborated`.

On each new final transcript, and when a hypothesis arrives after speech already exists, run this check:

1. The transcript event has `is_final=true` and source `operator_report` or `dispatcher_confirmed`.
2. `scripts/transcriber.py` has already extracted a fact from that exact line, or the line contains an allowlisted posture phrase. Interim speech is ignored.
3. The fact’s field and value are a row in the table above, and the vision value is the positive or matching one.
4. The still is not stale: its `observed_at` is within 15 seconds before the transcript, or the transcript is still the latest line and the still is newer than the previous hypothesis. A still from a minute ago cannot confirm a sentence just spoken.
5. The human fact and the claim do not disagree.

If all five pass, set the claim to `corroborated` and store the transcript `event_id`. The incident fact keeps the human source and the human certainty (`reported` for the operator, `verified` for the dispatcher, which is what `scripts/incident.py` already assigns). The camera does not become the source of the fact. Corroboration means “the picture agrees with what this person said,” and the summary may say that in the structured vision section only.

If the human said the opposite, set the claim to `conflict`. Keep the human fact. Do not let the model win. `SOURCE_PRIORITY` in `scripts/incident.py` has no `cv_model` entry today; if one is added later it must sit below `operator_report`.

If no line aligns, the claim stays `uncorroborated`. It is stored. It is not copied into `facts`. It is not spoken.

### What the dispatcher hears

`scripts/dispatcher.py` already refuses to speak the words `camera`, `passthrough`, `cv_model`, `yolov9`, `blazepose`, `object detection`, and `in frame`. Leave that guard in place.

- Uncorroborated and conflicting claims are omitted from `spoken_text`.
- A corroborated claim does not add a new spoken sentence. The spoken sentence remains the one built from the human fact (“The bystander reports that an AED is available”). The agreement is metadata on the summary, for a person reading the dashboard, not a second voice in the phone call.
- Do not prompt the operator with the model’s guess (“I think they are unresponsive”). A fixed prompt that asks the operator to describe the scene is out of scope until someone writes the exact words and a clinical reviewer accepts them. This stage does not add prompts.

### Examples

**Operator: “They’re gasping.”** The extractor sets `patient.breathing=gasping` from `operator_report`. The still shows a person reclined. Posture may be stored as `reclined` / `uncorroborated`. Breathing is untouched by the still. `spoken_text` says the bystander reports gasping. It does not say the camera confirmed it.

**Operator: “There is an AED on the wall.”** The extractor sets `aed.available=true`. The still’s `aed_like_object=yes` within the time window becomes `corroborated` and points at that transcript event. `spoken_text` still attributes the AED to the bystander.

**Operator: “There is an AED on the wall.” The still has `aed_like_object=no`.** The operator fact stands. The claim is `conflict`. The phone briefing does not say the AED is missing.

**Nobody has spoken. The still shows a person on the ground.** Store `person_visible=yes`, `posture=reclined`, both `uncorroborated`. `patient.responsive` stays unknown. The briefing does not mention the person.

**Dispatcher: “You said they are on the ground.”** That line can corroborate `posture=reclined` if the words match the posture list. It still does not set responsiveness.

## Event shape

Use the same envelope as every other event: `event_id`, `session_id`, `type`, `source`, `observed_at`, `received_at`, `payload`.

```json
{
  "event_id": "evt_vision_001",
  "session_id": "sim_demo_001",
  "type": "vision_hypothesis",
  "source": "cv_model",
  "observed_at": "2026-11-14T19:00:04Z",
  "received_at": "2026-11-14T19:00:05Z",
  "payload": {
    "frame_id": "frame_88",
    "image_width": 378,
    "image_height": 378,
    "detector": {"name": "yolov9", "person_count": 1, "confidence": 0.86},
    "vlm": {"name": "moondream2", "revision": "UNSET", "latency_ms": 0},
    "claims": [
      {
        "claim": "posture",
        "value": "reclined",
        "status": "uncorroborated",
        "transcript_event_id": null
      }
    ]
  }
}
```

`source` is `cv_model` for the hypothesis event. After corroboration, `status` and `transcript_event_id` update on the claim. The linked speech event keeps its own source. Do not invent a blended source.

Store the claim record. Do not store the JPEG in the incident log or in DynamoDB. The frame id and timestamp are enough to audit which still was used. Raw frames, if kept at all for a later error review, need a separate consent decision; this plan does not grant one.

`scripts/incident.py` should reject a `vision_hypothesis` that contains a forbidden claim, a value outside the table, or a fact field from `ai/transcriber-contract.json`. A hypothesis must not be reducible into `context["facts"]`.

## How to build it

The audio path stays as it is. Vision is a new input beside it.

### 1. Contract and tests, no model yet

Add `ai/vision-contract.json` with the claim names, allowed values, the corroboration rows, the stale window, and the forbidden list. Extend `scripts/validate.py` with cases that do not load a model:

- reclined posture leaves `patient.responsive` unknown
- `aed_like_object=yes` does nothing until a final transcript extracts `aed.available=true`
- the same pair inside 15 seconds marks the claim `corroborated` and leaves the fact source as `operator_report`
- a dispatcher line can corroborate; an interim line cannot
- `aed_like_object=no` against a spoken AED sets `conflict` and keeps the spoken fact
- a hypothesis that says “unconscious” or sets `patient.breathing` is rejected
- `spoken_text` for all of the above contains none of `FORBIDDEN_SPOKEN_TERMS` and does not gain a sentence from the still
- a still older than 15 seconds does not corroborate a new line

### 2. One still on the laptop

Add a small script, separate from `scripts/transcribe_audio.py`, that reads one image, runs moondream2, and prints schema-valid claims or a structured error. Pin the revision after the model card is re-checked. Parse JSON only. If the model adds a sentence or an unknown key, drop the call and record `status: invalid_model_output`. Do not ask the model to retry in prose.

Time this on the demo laptop before wiring it to a session. Record GPU or CPU, load time, and seconds per still in this file’s verification section once the measurement exists.

### 3. Join to the transcript

Add the join next to `scripts/incident.py`, not inside the prompt. It reads hypotheses and final transcript facts and writes claim status. `scripts/dispatcher.py` does not read hypotheses when it builds `spoken_text`. A later dashboard may show a separate “not confirmed” list; that list is not the phone briefing.

### 4. Quest stills

The Unity teammate owns `PassthroughCameraAccess`, camera permission, and the YOLO sample. This repository should accept a still only as an explicit upload tied to a session id: frame id, capture time, 378 px JPEG, detector person count. The Quest app must keep working when this upload fails. Camera permission denied, YOLO down, or the laptop model down all produce the same user-visible result: no vision claims, stage-1 briefing unchanged.

### 5. Only then, compare models

On a folder of stills captured in a consented practice scene (a person on the floor, a training AED, no real patient), run moondream2 and, offline, Qwen-VL and KOSMOS-2. Score three things: fraction of answers that validate against the schema, fraction that include a forbidden clinical word, and seconds per still. Keep moondream2 unless it fails the schema often enough that KOSMOS-2 is both cleaner and still inside the 2 second budget. Do not switch to Qwen-VL or any 7B-plus model for the live call based on accuracy alone.

## Failure behavior

| What happened | What to store | What the operator and dispatcher get |
|---|---|---|
| Camera permission refused | no vision events | stage-1 briefing |
| YOLO sees nobody | `person_visible=no` from the detector, other claims unset | no spoken change |
| VLM times out or returns junk | `invalid_model_output` or nothing; do not keep a partial sentence | no spoken change |
| VLM says “unconscious” or fills a patient field | event rejected | no spoken change |
| Speech and vision disagree | human fact kept, claim `conflict` | spoken line follows the human |
| Speech and vision agree on an allowlisted row | claim `corroborated`, fact source unchanged | spoken line follows the human |
| Newer speech arrives | old still cannot override it | latest human fact wins, as today |
| Model process crashes | stop vision updates | call and transcripts continue |

## What this stage does not do

- It does not diagnose, and it does not decide CPR or a shock.
- It does not change `spoken_text` except by leaving it alone.
- It does not send frames to a cloud VLM.
- It does not run BlazePose, read text in the scene, or estimate compression rate.
- It does not turn the live path into a 7B, 17B, or 34B model from the survey.
- It does not replace Meta speech-to-text or the deterministic extractor.

## Implementation checklist

- [x] Re-read the moondream2 model card. Revision `2025-06-21`, Apache-2.0, `query(image, question)`, local weights only.
- [x] Add `ai/vision-contract.json` and the validator cases in section “How to build it.”
- [x] Time one moondream2 still. On this Mac the query took about 25 seconds, so the live look keeps the audio briefing.
- [x] Corroboration is derived from the event log. A claim cannot enter `facts` or `spoken_text`.
- [ ] Quest app: send a 378 px still only after YOLO has a stable person box. Until then, `scripts/assess_still.py` is the stand-in. `--person-count 0` skips moondream2.
- [ ] Score moondream2 against KOSMOS-2 and Qwen-VL on consented practice stills. Not started. No practice stills are in this repository, and those models are not installed.
