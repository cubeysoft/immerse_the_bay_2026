# Run the project now

This repository currently runs as a local Python validation and briefing demo. It does not yet
receive data from a Quest headset, host an AWS endpoint, or place a Twilio call.

## Requirements

- Python 3
- A terminal opened at the repository root

The checks and briefing demo below use only the Python standard library. No package
installation is required for those two commands. Transcribing a wav or the microphone
uses the separate install in [Transcribe a recording](#transcribe-a-recording).

## Validate the runtime

```sh
python3 scripts/validate.py
```

Expected result:

```text
PASS: Meta STT boundary, 36 exact transcript cases, explicit help, location fallback, event rejection, provenance, vision corroboration, one-second audio fallback and Twilio briefing.
IMPORTANT: This is not an STT accuracy test, clinical approval, API integration test, or proof of headset performance.
```

This checks transcript extraction, event validation, source authority, conflict handling, location
fallback, vision corroboration, the one-second audio fallback, and deterministic spoken briefings.
It does not load moondream2.

## Run the briefing demo

```sh
python3 scripts/summarize.py
```

The command prints two simulated dispatcher briefings. The first uses an operator-reported
roadside location. The second uses device coordinates and reports an adult male who is
unresponsive and breathing normally.

The command does not make a network request or phone call.

To print the briefing for a session file written by the audio tool:

```sh
python3 scripts/summarize.py runtime/session.json
```

## Transcribe a recording

This is the laptop stand-in for Quest speech-to-text. It is separate from the commands above and needs one package install. Quest still sends finished text from Meta speech-to-text. This script fills the same `speech_transcript` event from a file or the computer microphone.

```sh
python3 -m pip install -r requirements-audio.txt
```

The first run downloads the English `small` faster-whisper model (about 460 MB) and caches it outside the repository. Later runs reuse the cache.

At the start of the call, label the recording as the operator:

```sh
python3 scripts/transcribe_audio.py operator.wav --source operator_report
```

After the dispatcher is on the line, transcribe that audio separately and keep the operator on `operator_report`:

```sh
python3 scripts/transcribe_audio.py dispatcher.wav --source dispatcher_confirmed
```

Each command appends one final transcript to `runtime/session.json`, with `stt_provider` set to `faster-whisper` and word confidence when the model returns it, then prints the transcript list and the spoken briefing. Run the command again to add another line. The speaker is the `--source` argument. The script does not guess who is talking.

To record from this computer's microphone for 8 seconds:

```sh
python3 scripts/transcribe_audio.py --mic --seconds 8 --source operator_report
```

`--seconds` must be from 1 to 60. macOS may ask for microphone permission the first time.

`transcripts` keeps every finished operator and dispatcher line. `spoken_text` is a separate natural-language briefing for dispatch. A dispatcher instruction that matches no fact is included in that briefing, for example: “The dispatcher said, push hard in the center of the chest.”

`runtime/session.json` is local session state and is gitignored. Delete it to start a new session. Pass `--session path.json` and `--session-id your_id` to write somewhere else. A file that already belongs to another session id is left unchanged.

## Assess one still

Optional. The demo commands above do not run this, and they do not load moondream2. Leave it out of a laptop demo: on this Mac the vision path does not finish inside its limit.

The command needs the packages in `requirements-vision.txt` and the local moondream2 weights, revision `2025-06-21`.

```sh
python3 -m pip install -r requirements-vision.txt
python3 scripts/assess_still.py scene.jpg --frame-id frame_88
```

The one-second limit includes loading the weights. The first load is the overhead before any answer. On this Mac, November 14, 2026, that load took about 5 seconds from the local Hugging Face cache. One 378 px look then took about 25 seconds and did not return a usable answer. Because the load itself is past one second, the command returns audio in about one second and exits. It does not wait for the weights to finish loading, and it does not write the session file.

Expected result on this machine:

```text
{"mode": "audio", "reason": "timeout", "latency_ms": 1000, "claims": []}
Vision took longer than one second. The spoken briefing stays on the transcript.
```

`--person-count 0` records that the detector saw nobody and does not start the load.

A stored claim is not a fact. It becomes support for something a person already said only when a final operator or dispatcher line states the same allowlisted thing. The phone briefing does not gain a sentence from the still.

## What is incoming

The intended live boundary starts after Meta Unity AI Speech to Text. Unity sends final
transcripts and explicit app/device events to a future AWS adapter.

- `help_request`: an explicit user action from the app UI.
- `speech_transcript`: verbatim final operator or dispatcher text, `stt_provider`,
  `is_final: true`, and optional confidence.
- `location_update`: an operator description or authorized device coordinates with source and
  accuracy.
- `aed_telemetry`: optional observations from an AED integration.
- `call_status`: requested, ringing, connected, completed, or failed status from the phone server.

Unity should not extract or send patient facts. The future backend adapter must preserve the raw
transcript, call `scripts/transcriber.py`, attach the extracted proposed facts to a canonical
event, and then pass that event to `scripts/incident.py`.

The local demo currently supplies those canonical events from `runtime/events.example.json`.
Example client requests are in `api/request-examples.json`.

## What happens to the input

1. `scripts/transcriber.py` extracts only supported, explicitly stated facts from final speech.
2. `scripts/incident.py` validates events, rejects unauthorized sources, tracks conflicts, and
   reduces accepted events into incident state.
3. `scripts/dispatcher.py` keeps every final line in `transcripts` and writes a separate
   natural-language `spoken_text` briefing for dispatch. Dispatcher instructions that
   match no fact are included in that briefing.
4. `scripts/summarize.py` composes the complete structured summary.

The LLM, if one is added, belongs before the reducer as a constrained proposal generator. Its
output must pass the same validation and provenance rules; it must not write the final Twilio
script directly.

## What is outgoing

The standard-library commands write only to the terminal. The audio command also writes
`runtime/session.json`. The composed summary includes:

- whether help was explicitly requested;
- location and location provenance;
- supported patient and scene facts;
- unknown fields and conflicts;
- preserved transcripts;
- deterministic `spoken_text`;
- call status.

The shape is defined by `dispatch/summary-schema.json`; an example is in
`dispatch/summary.example.json`.

In the intended integration, AWS stores or returns this structured summary. After the test call
is confirmed connected, the Twilio adapter reads only the validated `spoken_text` for `<Say>`.
No current code performs that handoff.

## Teammate integration boundaries

- **Unity:** send final Meta STT text, explicit help requests, authorized location updates, and
  stable session/event IDs. Label headset speech `operator_report`. After the dispatcher is on
  the line, send that audio as `dispatcher_confirmed`. Do not infer help from speech. The laptop
  `faster-whisper` script is only a stand-in for the same event.
- **AWS:** authenticate and validate requests, extract transcript facts, reduce events, persist
  session state, and return the deterministic summary.
- **Twilio:** accept only allowlisted simulation destinations, report call status, and speak the
  validated `spoken_text` after connection.

The remaining integration work is listed in `docs/TEAM_HANDOFF.md`.

