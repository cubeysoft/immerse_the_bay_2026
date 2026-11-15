#!/usr/bin/env python3
"""Read one still with moondream2, or keep the audio briefing if that look is late.

The model is local. This script does not send the image to a hosted inference API.
A result that misses the one-second budget is not written into the session.
"""

import argparse
import json
import sys
from pathlib import Path

from session import append_event, load_events, utc_now
from summarize import summarize_events
from vision import (
    BUDGET_SECONDS,
    CONTRACT,
    IMAGE_SIZE,
    PROMPT,
    hypothesis_event,
    look_at,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SESSION = ROOT / "runtime" / "session.json"


def _install_load_compat():
    """Transformers 5 asks every checkpoint for all_tied_weights_keys. This revision still uses the older name."""
    from transformers import PreTrainedModel

    if isinstance(getattr(PreTrainedModel, "all_tied_weights_keys", None), property):
        return

    def all_tied_weights_keys(self):
        legacy = getattr(type(self), "_tied_weights_keys", None)
        if isinstance(legacy, dict):
            return legacy
        if isinstance(legacy, (list, set, tuple)):
            return {name: [name] for name in legacy}
        return {}

    PreTrainedModel.all_tied_weights_keys = property(all_tied_weights_keys)


def _keep_pool_on_input_device(model):
    """The checkpoint sends one pooling result to MPS whenever MPS exists.

    On this Mac that tensor then no longer matches a CPU model, and an MPS
    model returned NaN logits. Keep the pooled tensor on the same device as
    its input.
    """
    import sys
    import torch.nn.functional as F

    package = type(model.model).__module__.rsplit(".", 1)[0]
    vision_module = sys.modules[package + ".vision"]

    def adaptive_avg_pool2d(tensor, output_size):
        return F.adaptive_avg_pool2d(tensor.to("cpu"), output_size).to(tensor.device)

    vision_module.adaptive_avg_pool2d = adaptive_avg_pool2d


def load_moondream():
    try:
        import torch
        from transformers import AutoModelForCausalLM
    except ImportError as exc:
        raise SystemExit(
            "moondream2 dependencies are missing. From the repository root, run: "
            "python3 -m pip install -r requirements-vision.txt"
        ) from exc

    _install_load_compat()
    if torch.cuda.is_available():
        device = "cuda"
    else:
        device = "cpu"
    model = AutoModelForCausalLM.from_pretrained(
        CONTRACT["model_id"],
        revision=CONTRACT["model_revision"],
        trust_remote_code=True,
    )
    model.eval()
    if device != "cpu":
        model = model.to(device)
    _keep_pool_on_input_device(model)
    return model, device


def _load_and_ask(image):
    """Load and query inside the one-second look. A cold start that misses the limit is audio."""
    try:
        model, _device = load_moondream()
    except SystemExit as exc:
        raise RuntimeError(str(exc)) from exc
    return ask(model, image)


def ask(model, image):
    settings = {
        "max_tokens": CONTRACT["max_new_tokens"],
        "temperature": 0,
        "variant": None,
    }
    result = model.query(image, PROMPT, settings=settings)
    if isinstance(result, dict):
        return result.get("answer", "")
    return str(result)


def _open_still(path):
    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit(
            "Pillow is not installed. From the repository root, run: "
            "python3 -m pip install -r requirements-vision.txt"
        ) from exc
    image = Image.open(path).convert("RGB")
    return image.resize((IMAGE_SIZE, IMAGE_SIZE))


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Assess one still. The one-second limit includes loading the weights. A miss leaves the audio briefing unchanged."
    )
    parser.add_argument("image", nargs="?", help="Still to assess. Omitted only with --person-count 0.")
    parser.add_argument("--frame-id", default="frame_001")
    parser.add_argument("--observed-at", help="Capture time. Defaults to now.")
    parser.add_argument("--person-count", type=int, help="YOLO person count. 0 skips moondream2.")
    parser.add_argument("--detector-confidence", type=float)
    parser.add_argument("--session", default=str(DEFAULT_SESSION))
    parser.add_argument("--session-id", default="sim_audio_001")
    parser.add_argument("--no-session", action="store_true", help="Print the look and do not write a session file.")
    return parser.parse_args(argv)


def _detector(args):
    if args.person_count is None:
        return None
    detector = {"name": "yolov9", "person_count": args.person_count}
    if args.detector_confidence is not None:
        detector["confidence"] = args.detector_confidence
    return detector


def _print_existing_briefing(path):
    if not path.exists():
        print("No session file. The spoken briefing stays on whatever speech is already stored.")
        return 0
    try:
        events = load_events(path)
    except ValueError as exc:
        print(str(exc))
        return 1
    if not events:
        print("Session file has no events. Nothing was added.")
        return 0
    try:
        summarize_events(events, "SESSION BRIEFING — NOT A DIAGNOSIS")
    except ValueError as exc:
        print(f"Briefing rejected: {exc}")
        return 1
    return 0


def main(argv):
    args = _parse_args(argv)
    if args.person_count is not None and args.person_count < 0:
        raise SystemExit("--person-count cannot be negative.")
    if args.detector_confidence is not None and not 0 <= args.detector_confidence <= 1:
        raise SystemExit("--detector-confidence must be between 0 and 1.")
    if args.person_count != 0 and not args.image:
        raise SystemExit("Pass an image, or pass --person-count 0 when the detector sees nobody.")
    if not args.frame_id.strip():
        raise SystemExit("--frame-id is required.")

    session_path = Path(args.session)
    if not args.no_session and session_path.exists():
        try:
            existing = load_events(session_path)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        if existing and existing[0]["session_id"] != args.session_id:
            raise SystemExit(
                f"{session_path} belongs to session {existing[0]['session_id']}, not {args.session_id}"
            )

    observed_at = args.observed_at or utc_now()
    if args.person_count == 0:
        look = look_at(None, None, person_count=0)
    else:
        image_path = Path(args.image)
        if not image_path.is_file():
            raise SystemExit(f"Image not found: {image_path}")
        image = _open_still(image_path)
        print(
            f"The {BUDGET_SECONDS:g}-second limit includes loading {CONTRACT['model_name']}. "
            "If the weights are still loading at that limit, the briefing stays on the transcript.",
            file=sys.stderr,
        )
        look = look_at(image, _load_and_ask, person_count=args.person_count)

    print(json.dumps(look.as_dict()))
    if look.mode != "vision":
        if look.reason == "timeout":
            print("Vision took longer than one second. The spoken briefing stays on the transcript.")
        else:
            print(
                f"Vision returned nothing usable ({look.reason}). "
                "The spoken briefing stays on the transcript."
            )
        if args.no_session:
            return 0
        return _print_existing_briefing(session_path)

    vlm = None
    if look.reason == "model":
        vlm = {
            "name": CONTRACT["model_name"],
            "revision": CONTRACT["model_revision"],
            "latency_ms": look.latency_ms,
        }
    try:
        event = hypothesis_event(
            args.session_id,
            args.frame_id,
            observed_at,
            look.claims,
            detector=_detector(args),
            vlm=vlm,
        )
    except ValueError as exc:
        print(json.dumps({"mode": "audio", "reason": "invalid_model_output", "latency_ms": look.latency_ms, "claims": []}))
        print(str(exc), file=sys.stderr)
        return 0 if args.no_session else _print_existing_briefing(session_path)

    if args.no_session:
        print("Look accepted. Session file not written.")
        return 0
    try:
        events = append_event(session_path, event, args.session_id)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Session file: {session_path}")
    try:
        summarize_events(events, "SESSION BRIEFING — NOT A DIAGNOSIS")
    except ValueError as exc:
        print(f"Look saved. Briefing rejected: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
