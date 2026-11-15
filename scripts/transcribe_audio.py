#!/usr/bin/env python3
"""Turn one recording into a final transcript event and reprint the briefing.

The speaker label is an argument. This script does not decide whether the
voice is the operator or the dispatcher.
"""

import argparse
import sys
import tempfile
import wave
from pathlib import Path

from session import LOCAL_STT_PROVIDER, append_speech
from summarize import summarize_events


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SESSION = ROOT / "runtime" / "session.json"
DEFAULT_MODEL = "small.en"
SAMPLE_RATE = 16000


def transcribe_wav(wav_path, model_name):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SystemExit(
            "faster-whisper is not installed. From the repository root, run: "
            "python3 -m pip install -r requirements-audio.txt"
        ) from exc

    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(
        str(wav_path),
        language="en",
        vad_filter=True,
        beam_size=5,
        word_timestamps=True,
    )
    segments = list(segments)
    text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
    return text.strip(), _mean_word_confidence(segments)


def _mean_word_confidence(segments):
    probabilities = []
    for segment in segments:
        for word in segment.words or []:
            probability = getattr(word, "probability", None)
            if isinstance(probability, bool):
                continue
            try:
                probability = float(probability)
            except (TypeError, ValueError):
                continue
            if 0 <= probability <= 1:
                probabilities.append(probability)
    if not probabilities:
        return None
    return round(sum(probabilities) / len(probabilities), 2)


def record_microphone(destination, seconds):
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise SystemExit(
            "sounddevice is not installed. From the repository root, run: "
            "python3 -m pip install -r requirements-audio.txt"
        ) from exc

    samples = int(seconds * SAMPLE_RATE)
    print(f"Recording {seconds:g} seconds from the microphone. Speak now.", flush=True)
    audio = sd.rec(samples, samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    sd.wait()
    with wave.open(str(destination), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(audio.tobytes())


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Transcribe one recording into the session briefing."
    )
    parser.add_argument("wav", nargs="?", help="Audio file to transcribe")
    parser.add_argument(
        "--source",
        required=True,
        choices=["operator_report", "dispatcher_confirmed"],
        help="Who spoke. operator_report before the dispatcher joins; dispatcher_confirmed after.",
    )
    parser.add_argument("--session", default=str(DEFAULT_SESSION))
    parser.add_argument("--session-id", default="sim_audio_001")
    parser.add_argument("--mic", action="store_true", help="Record from the microphone instead of a file")
    parser.add_argument("--seconds", type=float, default=8, help="Microphone recording length")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    return parser.parse_args(argv)


def main(argv):
    args = _parse_args(argv)
    if args.mic and args.wav:
        raise SystemExit("Pass either an audio file or --mic, not both.")
    if not args.mic and not args.wav:
        raise SystemExit("Pass an audio file, or pass --mic to record one.")
    if args.mic and not 1 <= args.seconds <= 60:
        raise SystemExit("--seconds must be between 1 and 60.")

    if args.mic:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            wav_path = Path(handle.name)
        try:
            record_microphone(wav_path, args.seconds)
            text, confidence = transcribe_wav(wav_path, args.model)
        finally:
            wav_path.unlink(missing_ok=True)
    else:
        wav_path = Path(args.wav)
        if not wav_path.is_file():
            raise SystemExit(f"Audio file not found: {wav_path}")
        text, confidence = transcribe_wav(wav_path, args.model)

    if not text:
        raise SystemExit("No speech recognized. The session file was not changed.")

    try:
        events = append_speech(
            args.session,
            text,
            args.source,
            args.session_id,
            stt_provider=LOCAL_STT_PROVIDER,
            confidence=confidence,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(f"Transcript ({args.source}): {text}")
    print(f"Session file: {args.session}")
    print()
    try:
        summarize_events(events, "SESSION BRIEFING — NOT A DIAGNOSIS")
    except ValueError as exc:
        print(f"Transcript saved. Briefing rejected: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
