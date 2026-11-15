# Run the project now

This repository currently runs as a local Python validation and briefing demo. It does not yet
receive data from a Quest headset, host an AWS endpoint, or place a Twilio call.

## Requirements

- Python 3
- A terminal opened at the repository root

The current runtime uses only the Python standard library. No package installation is required
for the commands below.

## Validate the runtime

```sh
python3 scripts/validate.py
```

Expected result:

```text
PASS: Meta STT boundary, 36 exact transcript cases, explicit help, location fallback, event rejection, provenance and Twilio briefing.
IMPORTANT: This is not an STT accuracy test, clinical approval, API integration test, or proof of headset performance.
```

This checks transcript extraction, event validation, source authority, conflict handling, location
fallback, and deterministic spoken briefings.

## Run the briefing demo

```sh
python3 scripts/summarize.py
```

The command prints two simulated dispatcher briefings. The first uses an operator-reported
roadside location. The second uses device coordinates and reports an adult male who is
unresponsive and breathing normally.

The command does not make a network request or phone call.

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
3. `scripts/dispatcher.py` builds a deterministic, evidence-labeled `spoken_text` briefing.
4. `scripts/summarize.py` composes the complete structured summary.

The LLM, if one is added, belongs before the reducer as a constrained proposal generator. Its
output must pass the same validation and provenance rules; it must not write the final Twilio
script directly.

## What is outgoing

Running the project now writes only to the terminal. The composed summary includes:

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
  stable session/event IDs. Do not infer help from speech.
- **AWS:** authenticate and validate requests, extract transcript facts, reduce events, persist
  session state, and return the deterministic summary.
- **Twilio:** accept only allowlisted simulation destinations, report call status, and speak the
  validated `spoken_text` after connection.

The remaining integration work is listed in `docs/TEAM_HANDOFF.md`.

