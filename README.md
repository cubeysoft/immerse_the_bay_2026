# XR-AED

This repository takes a finished transcript and keeps two results: the exact words, and a short spoken briefing for a simulated dispatcher.

A laptop can also turn a wav file or a microphone clip into that transcript. The Quest app is what hears the headset. This code starts once the words exist. It keeps every finished line in the transcript, pulls out a few explicit facts such as “unconscious” or “gasping,” and turns those facts into a spoken briefing for dispatch.

The demo stays on that audio path. `validate.py`, `summarize.py`, and `transcribe_audio.py` do not load a vision model. An optional camera still is described in `RUNBOOK.md`. On this Mac that command also stays on the transcript: the first load of the vision weights takes about 5 seconds, and one look takes about 25 seconds. The one-second limit includes the load, so the command returns the audio briefing and does not wait for the weights.

## Run it on a new machine

You need Python 3 and a terminal opened in this folder. These two commands use only the Python standard library.

```bash
python3 scripts/validate.py
python3 scripts/summarize.py
```

`validate.py` should end with:

```text
PASS: Meta STT boundary, 36 exact transcript cases, explicit help, location fallback, event rejection, provenance, vision corroboration, one-second audio fallback and Twilio briefing.
IMPORTANT: This is not an STT accuracy test, clinical approval, API integration test, or proof of headset performance.
```

That checks the sample transcripts, fact rules, and briefing text. It does not listen to a microphone or contact a phone network.

`summarize.py` prints two sample briefings. The first is a roadside report of someone unresponsive and gasping. The second uses a device location and an adult who is unresponsive and breathing normally.

## Transcribe a recording on this computer

This step is optional. Use it to try operator and dispatcher audio before the Quest microphone is connected.

```bash
python3 -m pip install -r requirements-audio.txt
```

The first transcription downloads an English speech model, about 460 MB, and stores it outside this folder.

Label the person wearing the headset as the operator:

```bash
python3 scripts/transcribe_audio.py operator.wav --source operator_report
```

After the dispatcher is on the line, transcribe that audio separately:

```bash
python3 scripts/transcribe_audio.py dispatcher.wav --source dispatcher_confirmed
```

Or record this computer’s microphone for 8 seconds. `--seconds` can be from 1 to 60. macOS may ask for microphone permission.

```bash
python3 scripts/transcribe_audio.py --mic --seconds 8 --source operator_report
```

Each command adds one line to `runtime/session.json` and prints the briefing. `--source` is who spoke. The program does not decide that from the sound. Run it again on another clip to add another line. Delete `runtime/session.json` to start over.

Print a saved session again with:

```bash
python3 scripts/summarize.py runtime/session.json
```

The transcript keeps every finished line. The spoken briefing is a separate natural-language summary for dispatch. A dispatcher instruction that matches no fact is still included, for example: “The dispatcher said, push hard in the center of the chest.”

## A camera still

Optional, and not part of the demo above. The command, the expected audio result, and what a claim is allowed to support are in `RUNBOOK.md` under “Assess one still.”

`scripts/assess_still.py` is the only command that loads moondream2, revision `2025-06-21`. It needs `requirements-vision.txt`. The one-second limit includes loading those weights. On this Mac the first load took about 5 seconds from the local cache, and one 378 px look then took about 25 seconds. Both are past the limit, so the command returns `mode: audio` in about one second, writes nothing, and leaves the spoken briefing on the transcript. It does not wait for the model to finish loading. A later look on the same machine still misses the limit, because the query itself takes about 25 seconds.

A stored claim is not a fact. It can support something a person already said only when a final operator or dispatcher line states the same allowlisted thing. The briefing does not gain a sentence from the still.

## What this folder does not run

- Putting on a Quest does not start this program. There is no Unity project here, and the demo does not read the Quest camera.
- The demo commands never load moondream2. The optional still command is above, and on this Mac it returns the audio briefing.
- CPR clips are not played. `knowledge-base/media.json` lists clip names, and the video files are absent. Clinical text in `knowledge-base/clinical.json` is draft-only and turned off.
- No phone call is placed. `api/openapi.yaml` describes a future test-call API. Nothing in this folder listens for HTTP requests, dials Twilio, or contacts 911.
- The briefing does not invent medical instructions. It repeats recognized facts and the dispatcher’s own words.

Later, the Quest app sends finished text into this same path. Headset speech is `operator_report`. Dispatcher speech, once that call audio can be heard, is `dispatcher_confirmed`. The event shape and the Unity, AWS, and Twilio split are in `RUNBOOK.md` and `docs/TEAM_HANDOFF.md`.

## Where to look

- `scripts/`: fact extraction, incident state, the spoken briefing, checks, the optional recording transcriber, and the optional still command.
- `runtime/events.example.json`: the sample incident behind the first briefing.
- `dispatch/`: the briefing format.
- `api/`: the proposed HTTP contract. It is not a running service.
- `knowledge-base/`: draft clinical text, media placeholders, and sources.
- `RUNBOOK.md`: expected command output, the optional still, and the live input and output boundary.
- `VISION.md`: why the still uses moondream2, which claims are allowed, and the measured load and look times on this Mac.

## Safety

Keep this prototype off real emergency numbers. A future test call is limited to an allowlisted `test_dispatcher`. Clinical text and CPR media stay off until a reviewer approves them. Camera observations stay out of the briefing.
