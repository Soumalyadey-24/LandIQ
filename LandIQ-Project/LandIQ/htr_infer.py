#!/usr/bin/env python3
"""LandIQ handwriting recognition - minimal command-line inference.

    python htr_infer.py image.jpg
    python htr_infer.py image.jpg --script devanagari --allow-candidates
    python htr_infer.py --list-models

Runs a real pretrained checkpoint against a real image and prints the raw
transcription. There is no fallback that invents text: if no verified
recognizer covers the script, the tool says UNSUPPORTED and exits non-zero.

Writes result.txt (UTF-8) and result.json next to the image, or to --out-dir.

Windows note: the console defaults to cp1252 and will raise UnicodeEncodeError
on Devanagari/Bengali output, so stdout is reconfigured to UTF-8 below.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make `ai` importable when this file is run from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# UTF-8 stdout before anything prints. Needed on Windows PowerShell.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from ai.input_validation import InputValidator, ValidationError  # noqa: E402
from ai.recognizers import (RecognizerUnavailable, RoutingDecision,  # noqa: E402
                            build_default_registry, canonical_script,
                            runtime_environment)

EXIT_OK = 0
EXIT_BAD_INPUT = 2
EXIT_UNSUPPORTED = 3
EXIT_UNAVAILABLE = 4
EXIT_FAILED = 5


def _print_models(registry) -> int:
    report = registry.coverage_report()
    print("LandIQ recognizer coverage")
    print("=" * 72)
    print(f"  VERIFIED scripts : {', '.join(report['verified_scripts']) or 'none'}")
    print(f"  CANDIDATE scripts: {', '.join(report['candidate_scripts']) or 'none'}")
    print(f"\n  {report['policy']}\n")
    for spec in report["recognizers"]:
        mark = "OK " if spec["available"] else "-- "
        print(f"{mark}{spec['key']}")
        print(f"     checkpoint  : {spec['checkpoint']}")
        print(f"     revision    : {spec['revision']}")
        print(f"     architecture: {spec['architecture']}")
        print(f"     granularity : {spec['granularity']}   "
              f"scripts verified: {list(spec['scripts_verified']) or 'none'}")
        print(f"     status      : {spec['verification_status']}   "
              f"license: {spec['license']}")
        if spec["confidence_method"]:
            print(f"     confidence  : {spec['confidence_method']} "
                  f"(calibrated={spec['confidence_calibrated']})")
        print(f"     availability: {spec['availability_reason']}")
        if spec["notes"]:
            print(f"     notes       : {spec['notes']}")
        print()
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="htr_infer.py",
        description="Run real pretrained HTR inference on a handwriting image.")
    ap.add_argument("image", nargs="?", help="Path to a JPG or PNG image.")
    ap.add_argument("--script", default=None,
                    help="Script hint (latin, devanagari, ...). Default: the "
                         "single verified script, if there is exactly one.")
    ap.add_argument("--recognizer", default=None,
                    help="Force a recognizer by key (see --list-models).")
    ap.add_argument("--allow-candidates", action="store_true",
                    help="Permit recognizers not yet inference-tested here. "
                         "Output is explicitly marked unvalidated.")
    ap.add_argument("--out-dir", default=None,
                    help="Where to write result.txt / result.json "
                         "(default: alongside the image).")
    ap.add_argument("--max-new-tokens", type=int, default=64)
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    registry = build_default_registry()

    if args.list_models:
        return _print_models(registry)
    if not args.image:
        ap.error("an image path is required (or use --list-models)")

    # ---------------------------------------------------------- validate
    try:
        validated = InputValidator().validate_path(args.image)
    except ValidationError as exc:
        print(f"REJECTED [{exc.code}] {exc.message}", file=sys.stderr)
        if exc.hint:
            print(f"  hint: {exc.hint}", file=sys.stderr)
        return EXIT_BAD_INPUT

    # ------------------------------------------------------------- route
    if args.recognizer:
        recognizer = registry.get(args.recognizer)
        if recognizer is None:
            print(f"No such recognizer: {args.recognizer}", file=sys.stderr)
            return EXIT_BAD_INPUT
        script = canonical_script(
            args.script or (recognizer.spec.scripts_verified
                            or recognizer.spec.scripts_candidate
                            or ("unknown",))[0])
        decision, reason = RoutingDecision.VERIFIED, f"forced: {args.recognizer}"
    else:
        script = args.script
        if script is None:
            verified = registry.verified_scripts()
            if len(verified) == 1:
                script = verified[0]
            else:
                print("Script not specified and it cannot be inferred "
                      "unambiguously.", file=sys.stderr)
                print(f"  verified scripts: {verified}", file=sys.stderr)
                print("  pass --script <name>", file=sys.stderr)
                return EXIT_UNSUPPORTED
        routing = registry.resolve(script, allow_candidates=args.allow_candidates)
        decision, reason, recognizer = routing.decision, routing.reason, routing.recognizer
        script = routing.script

        if not routing.can_recognize:
            payload = {
                "image": str(Path(args.image).resolve()),
                "sha256": validated.sha256,
                "status": decision.value,
                "script": script,
                "transcription": None,
                "reason": reason,
                "verified_scripts": registry.verified_scripts(),
            }
            print(f"{decision.value}: {reason}", file=sys.stderr)
            _write_outputs(args, validated, payload, text=None)
            return (EXIT_UNAVAILABLE if decision is RoutingDecision.UNAVAILABLE
                    else EXIT_UNSUPPORTED)

    # --------------------------------------------------------- recognize
    try:
        result = recognizer.recognize(validated.data, script=script,
                                      max_new_tokens=args.max_new_tokens)
    except RecognizerUnavailable as exc:
        print(f"UNAVAILABLE: {exc.reason}", file=sys.stderr)
        return EXIT_UNAVAILABLE
    except Exception as exc:                       # pragma: no cover
        print(f"INFERENCE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_FAILED

    payload = {
        "image": str(Path(args.image).resolve()),
        "sha256": validated.sha256,
        "image_size": [validated.width, validated.height],
        "media_type": validated.media_type,
        "status": decision.value,
        "routing_reason": reason,
        "model": result.model,
        "revision": result.revision,
        "recognizer": recognizer.spec.key,
        "architecture": recognizer.spec.architecture,
        "granularity": result.granularity,
        "device": result.device,
        "script": result.script,
        "transcription": result.text,
        "confidence": result.confidence,
        "confidence_method": result.confidence_method,
        "confidence_calibrated": result.confidence_calibrated,
        "runtime_seconds": round(result.runtime_seconds, 4),
        "warnings": validated.warnings + result.warnings,
        "verification_status": recognizer.spec.verification_status.value,
        "environment": runtime_environment(),
        "disclaimer": (
            "Raw model output, reproduced verbatim. Not spell-corrected, "
            "normalised or translated. Confidence is a mean token probability "
            "from the model's own logits and is NOT calibrated - it does not "
            "mean the text is correct."),
    }

    if not args.quiet:
        print("-" * 72)
        print(result.text)
        print("-" * 72)
        conf = ("not available" if result.confidence is None
                else f"{result.confidence:.4f} ({result.confidence_method}, "
                     f"uncalibrated)")
        print(f"  model      : {result.model} @ {str(result.revision)[:12]}")
        print(f"  recognizer : {recognizer.spec.key} "
              f"[{recognizer.spec.verification_status.value}]")
        print(f"  script     : {result.script}   granularity: {result.granularity}")
        print(f"  device     : {result.device}   runtime: {result.runtime_seconds:.2f}s")
        print(f"  confidence : {conf}")
        print(f"  sha256     : {validated.sha256}")
        for w in payload["warnings"]:
            print(f"  warning    : {w}")

    _write_outputs(args, validated, payload, text=result.text)
    return EXIT_OK


def _write_outputs(args, validated, payload: dict, text: str | None) -> None:
    out_dir = Path(args.out_dir) if args.out_dir else Path(args.image).resolve().parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(args.image).stem

    txt = out_dir / f"{stem}.result.txt"
    txt.write_text(text if text is not None else
                   f"[{payload['status']}] {payload.get('reason', '')}",
                   encoding="utf-8")
    js = out_dir / f"{stem}.result.json"
    js.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                  encoding="utf-8")
    if not args.quiet:
        print(f"  wrote      : {txt.name}, {js.name}")


if __name__ == "__main__":
    raise SystemExit(main())
