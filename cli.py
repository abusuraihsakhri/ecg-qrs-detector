#!/usr/bin/env python3
"""CLI for ECG QRS Detector."""
import argparse
import json
import sys

from qrs_detector import (
    detect_r_peaks,
    compute_hrv_metrics,
    detect_arrhythmia,
    load_ecg_csv,
    generate_synthetic_ecg,
    main as detector_main,
)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ecg-qrs-detector",
        description="ECG QRS Detector — Pan-Tompkins R-peak detection with HRV analysis",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Detect from CSV
    detect = subparsers.add_parser("detect", help="Detect R-peaks in ECG CSV file")
    detect.add_argument("input_csv", help="Path to ECG CSV file")
    detect.add_argument("--fs", type=float, default=None, help="Sampling rate in Hz")
    detect.add_argument("--refractory", type=float, default=0.200, help="Refractory period (s)")
    detect.add_argument("--out-csv", default=None, help="Write R-peak data to CSV")

    # Demo with synthetic ECG
    demo = subparsers.add_parser("demo", help="Run detection on synthetic ECG")
    demo.add_argument("--duration", type=float, default=30.0, help="Duration in seconds")
    demo.add_argument("--fs", type=float, default=250.0, help="Sampling rate in Hz")
    demo.add_argument("--hr", type=float, default=70.0, help="Heart rate in bpm")

    args = parser.parse_args(argv)

    if args.command == "detect":
        # Delegate to the main module's CLI
        detect_argv = [args.input_csv]
        if args.fs:
            detect_argv.extend(["--fs", str(args.fs)])
        detect_argv.extend(["--refractory", str(args.refractory)])
        if args.out_csv:
            detect_argv.extend(["--out-csv", args.out_csv])
        return detector_main(detect_argv)

    if args.command == "demo":
        ecg, true_peaks = generate_synthetic_ecg(
            duration_sec=args.duration, fs=args.fs, heart_rate_bpm=args.hr,
        )
        r_peaks, _ = detect_r_peaks(ecg, args.fs)
        metrics = compute_hrv_metrics(r_peaks, args.fs)
        arrhythmia = detect_arrhythmia(metrics)

        result = {
            "duration_sec": args.duration,
            "sampling_rate_hz": args.fs,
            "target_hr_bpm": args.hr,
            "true_beats": len(true_peaks),
            "detected_beats": metrics["n_beats"],
            "mean_hr_bpm": round(metrics["mean_hr_bpm"], 1) if metrics["n_beats"] > 1 else None,
            "sdnn_ms": round(metrics["sdnn_ms"], 2) if metrics["n_beats"] > 1 else None,
            "rmssd_ms": round(metrics["rmssd_ms"], 2) if metrics["n_beats"] > 1 else None,
            "pnn50_pct": round(metrics["pnn50_pct"], 2) if metrics["n_beats"] > 1 else None,
            "rhythm": arrhythmia["rhythm"],
            "flags": arrhythmia["flags"],
        }
        print(json.dumps(result, indent=2))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
