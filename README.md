# ECG QRS Detector

R-peak detection in single-lead ECG signals using a simplified Pan-Tompkins algorithm, with heart rate and time-domain HRV analysis.

## Algorithm Pipeline

```
Raw ECG → Bandpass Filter (5-15 Hz) → Derivative → Squaring → Moving Window Integration → Adaptive Thresholding → R-peaks
```

Based on: Pan J, Tompkins WJ. "A Real-Time QRS Detection Algorithm." IEEE Trans Biomed Eng. 1985.

## Features

- **Pan-Tompkins QRS detection** with adaptive dual-threshold scheme
- **Heart rate** calculation from R-R intervals
- **HRV metrics**: SDNN, RMSSD, pNN50
- **Arrhythmia detection**: tachycardia, bradycardia, irregular rhythm
- **Synthetic ECG generator** for testing and demonstration
- **Stdlib only** — no numpy/scipy required

## HRV Metrics

| Metric | Description | Normal Range |
|--------|-------------|-------------|
| **SDNN** | Std deviation of R-R intervals | 50-100 ms (5-min) |
| **RMSSD** | Root mean square of successive differences | 20-50 ms |
| **pNN50** | % of successive R-R diffs > 50 ms | 5-25% |

## Quick Start

```bash
# Detect R-peaks in ECG CSV
python cli.py detect ecg_data.csv --fs 250

# Run demo with synthetic ECG
python cli.py demo --duration 30 --hr 70

# Save R-peak data to CSV
python cli.py detect ecg_data.csv --fs 250 --out-csv peaks.csv
```

## Python API

```python
from qrs_detector import detect_r_peaks, compute_hrv_metrics, detect_arrhythmia, generate_synthetic_ecg

# Generate synthetic ECG
ecg, true_peaks = generate_synthetic_ecg(duration_sec=30, fs=250, heart_rate_bpm=70)

# Detect R-peaks
r_peaks, pipeline = detect_r_peaks(ecg, fs=250)

# Compute HRV
metrics = compute_hrv_metrics(r_peaks, fs=250)
print(f"Mean HR: {metrics['mean_hr_bpm']:.1f} bpm")
print(f"SDNN: {metrics['sdnn_ms']:.1f} ms")

# Arrhythmia detection
arrhythmia = detect_arrhythmia(metrics)
print(f"Rhythm: {arrhythmia['rhythm']}")
```

## Dependencies

Python standard library only. No external packages required.

## License

MIT License.
