# XR-AED

This repository takes a finished transcript and keeps two results: the exact words, and a short spoken briefing for a simulated dispatcher.

A laptop can also turn a wav file or a microphone clip into that transcript. The Quest app is what hears the headset. This code starts once the words exist. It keeps every finished line in the transcript, pulls out a few explicit facts such as “unconscious” or “gasping,” and turns those facts into a spoken briefing for dispatch.

## Run it on a new machine

You need Python 3 and a terminal opened in this folder. These two commands use only the Python standard library.

```bash
python3 scripts/validate.py
python3 scripts/summarize.py
```

`validate.py` should end with:

```text
PASS: Meta STT boundary, 36 exact transcript cases, explicit help, location fallback, event rejection, provenance and Twilio briefing.
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

## What this folder does not run

- Putting on a Quest does not start this program. There is no Unity project here.
- The camera is not read, and video is not summarized.
- CPR clips are not played. `knowledge-base/media.json` lists clip names, and the video files are absent. Clinical text in `knowledge-base/clinical.json` is draft-only and turned off.
- No phone call is placed. `api/openapi.yaml` describes a future test-call API. Nothing in this folder listens for HTTP requests, dials Twilio, or contacts 911.
- The briefing does not invent medical instructions. It repeats recognized facts and the dispatcher’s own words.

Later, the Quest app sends finished text into this same path. Headset speech is `operator_report`. Dispatcher speech, once that call audio can be heard, is `dispatcher_confirmed`. The event shape and the Unity, AWS, and Twilio split are in `RUNBOOK.md` and `docs/TEAM_HANDOFF.md`.

## Where to look

- `scripts/`: fact extraction, incident state, the spoken briefing, checks, and the optional recording transcriber.
- `runtime/events.example.json`: the sample incident behind the first briefing.
- `dispatch/`: the briefing format.
- `api/`: the proposed HTTP contract. It is not a running service.
- `knowledge-base/`: draft clinical text, media placeholders, and sources.
- `RUNBOOK.md`: expected command output and the live input and output boundary.

## Safety

Keep this prototype off real emergency numbers. A future test call is limited to an allowlisted `test_dispatcher`. Clinical text and CPR media stay off until a reviewer approves them. Camera observations stay out of the briefing.
