"""Browser bridge for the existing standard-library ECG detector.

Imported by Pyodide; inputs remain inside the browser.
"""
import json
import math
import os
import tempfile

from qrs_detector import (
    compute_hrv_metrics,
    detect_arrhythmia,
    detect_r_peaks,
    generate_synthetic_ecg,
    load_ecg_csv,
)

MAX_FILE_BYTES = 3_000_000
MAX_SAMPLES = 250_000


def _safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe(item) for item in value]
    return value


def _analyze(samples, fs, refractory):
    if not samples:
        raise ValueError("The ECG file contains no samples.")
    if len(samples) > MAX_SAMPLES:
        raise ValueError("ECG exceeds the 250,000-sample browser processing limit.")
    peaks, _ = detect_r_peaks(samples, fs, refractory_sec=refractory)
    metrics = compute_hrv_metrics(peaks, fs)
    rhythm = detect_arrhythmia(metrics)
    step = max(1, math.ceil(len(samples) / 1400))
    plot = [
        [round(i / fs, 5), round(samples[i], 7)]
        for i in range(0, len(samples), step)
    ]
    peak_points = [
        [round(i / fs, 5), round(samples[i], 7)]
        for i in peaks
    ]
    result = {
        "sample_count": len(samples),
        "fs": fs,
        "duration_sec": len(samples) / fs,
        "metrics": metrics,
        "rhythm": rhythm,
        "peaks": peaks,
        "plot": plot,
        "peak_points": peak_points,
    }
    return json.dumps(_safe(result), allow_nan=False)


def analyze_csv(csv_text, fs_override=None, refractory=0.2):
    """Process user-supplied CSV without uploading it to a server."""
    if not isinstance(csv_text, str) or not csv_text.strip():
        raise ValueError("Select a non-empty CSV file.")
    if len(csv_text.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("CSV exceeds the 3 MB browser file-size limit.")
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".csv", newline="", delete=False,
    ) as handle:
        path = handle.name
        handle.write(csv_text)
    try:
        samples, fs = load_ecg_csv(path, fs=fs_override)
    finally:
        os.unlink(path)
    return _analyze(samples, fs, refractory)


def analyze_demo(duration=12.0, fs=250.0, heart_rate=72.0):
    """Run the actual QRS detector on a deterministic synthetic ECG."""
    if duration > 30 or fs > 500:
        raise ValueError("Demo is limited to 30 seconds and 500 Hz.")
    samples, _ = generate_synthetic_ecg(
        duration_sec=duration, fs=fs, heart_rate_bpm=heart_rate, seed=42,
    )
    return _analyze(samples, fs, 0.2)
