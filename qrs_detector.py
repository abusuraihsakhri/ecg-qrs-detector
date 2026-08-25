#!/usr/bin/env python3
"""
ECG QRS Detector
================

Detects R-peaks in a digitized single-lead ECG signal using a
simplified Pan-Tompkins (1985) real-time QRS detection algorithm,
then derives heart rate and standard time-domain heart-rate-variability
(HRV) metrics from the resulting R-R interval series.

Pipeline (Pan, J. & Tompkins, W.J., IEEE Trans. Biomed. Eng., 1985):

    raw ECG
      -> bandpass filter (~5-15 Hz)
      -> derivative filter
      -> squaring
      -> moving-window integration
      -> adaptive thresholding

Time-domain HRV formulas:
    SDNN  = standard deviation of all N-N (R-R) intervals
    RMSSD = root mean square of successive differences between N-N intervals
    pNN50 = percentage of successive N-N interval differences > 50 ms

Stdlib only — no numpy/scipy required.
"""

import argparse
import csv
import math
import sys


# ── Data loading ─────────────────────────────────────────────────────

def load_ecg_csv(path, fs=None):
    """Load a single-lead ECG waveform from a CSV file.

    Accepted formats (auto-detected from the header row):
      - two columns: time_seconds, amplitude  -> fs derived from time column
      - one column: amplitude                 -> fs must be supplied

    Returns (samples_list, fs).
    """
    with open(path, "r", newline="") as f:
        reader = csv.reader(f)
        rows = [row for row in reader if row and any(cell.strip() for cell in row)]

    if not rows:
        raise ValueError(f"No data found in {path}")

    # Detect header
    first_cell = rows[0][0].strip()
    try:
        float(first_cell)
        has_header = False
    except ValueError:
        has_header = True

    data_rows = rows[1:] if has_header else rows
    if not data_rows:
        raise ValueError(f"No numeric data rows found in {path}")

    ncols = len(data_rows[0])

    if ncols >= 2:
        times = [float(r[0]) for r in data_rows]
        amps = [float(r[1]) for r in data_rows]
        # Derive fs from median time step
        diffs = [times[i + 1] - times[i] for i in range(len(times) - 1)]
        diffs.sort()
        dt = diffs[len(diffs) // 2]  # median
        if dt <= 0:
            raise ValueError("Non-increasing timestamps in ECG file")
        derived_fs = 1.0 / dt
        out_fs = fs if fs is not None else derived_fs
        return amps, out_fs
    else:
        samples = [float(r[0]) for r in data_rows]
        if fs is None:
            raise ValueError(
                "Single-column CSV has no time information; supply --fs explicitly"
            )
        return samples, fs


# ── Filtering primitives (pure Python) ───────────────────────────────

def _convolve(signal, kernel):
    """Simple 1D convolution (full mode)."""
    n = len(signal)
    k = len(kernel)
    result_len = n + k - 1
    result = [0.0] * result_len
    for i in range(result_len):
        s = 0.0
        for j in range(max(0, i - n + 1), min(k, i + 1)):
            s += kernel[j] * signal[i - j]
        result[i] = s
    return result


def _convolve_same(signal, kernel):
    """Convolution trimmed to same length as signal (centered)."""
    full = _convolve(signal, kernel)
    k = len(kernel)
    offset = k // 2
    return full[offset:offset + len(signal)]


def bandpass_filter(ecg, fs, low=5.0, high=15.0):
    """Bandpass filter using Pan-Tompkins cascaded low-pass + high-pass.

    The LP filter removes high-frequency noise; the HP filter removes
    baseline wander and DC offset. Together they isolate the 5-15 Hz
    band where QRS energy is concentrated.

    Uses the original Pan-Tompkins integer-coefficient difference equations:
      LP: y[n] = 2*y[n-1] - y[n-2] + x[n] - 2*x[n-6] + x[n-12]
      HP: y[n] = y[n-1] - x[n]/32 + x[n-16] - x[n-17] + x[n-32]/32
    """
    lp = lowpass_filter(ecg)
    bp = highpass_filter(lp)
    return bp


def lowpass_filter(x):
    """Pan-Tompkins low-pass filter (integer coefficients).

    Difference equation: y[n] = 2*y[n-1] - y[n-2] + x[n] - 2*x[n-6] + x[n-12]
    """
    n = len(x)
    y = [0.0] * n
    for i in range(n):
        y[i] = (2 * y[i - 1] if i >= 1 else 0) \
               - (y[i - 2] if i >= 2 else 0) \
               + x[i] \
               - 2 * (x[i - 6] if i >= 6 else 0) \
               + (x[i - 12] if i >= 12 else 0)
    return y


def highpass_filter(x):
    """Pan-Tompkins high-pass filter (integer coefficients).

    Difference equation: y[n] = y[n-1] - x[n]/32 + x[n-16] - x[n-17] + x[n-32]/32
    """
    n = len(x)
    y = [0.0] * n
    for i in range(n):
        y[i] = (y[i - 1] if i >= 1 else 0) \
               - x[i] / 32.0 \
               + (x[i - 16] if i >= 16 else 0) \
               - (x[i - 17] if i >= 17 else 0) \
               + (x[i - 32] if i >= 32 else 0) / 32.0
    return y


def derivative_filter(x, fs):
    """5-point derivative approximation from Pan-Tompkins:
    y[n] = (1/8T)(-x[n-2] - 2x[n-1] + 2x[n+1] + x[n+2])
    """
    n = len(x)
    result = [0.0] * n
    scale = fs / 8.0
    for i in range(2, n - 2):
        result[i] = scale * (-x[i - 2] - 2 * x[i - 1] + 2 * x[i + 1] + x[i + 2])
    return result


def squaring(x):
    """Point-wise squaring: makes the signal positive and emphasizes
    higher (QRS-like) frequencies non-linearly."""
    return [v * v for v in x]


def moving_window_integration(x, fs, window_sec=0.150):
    """Moving-window integrator. Window width is approximately the
    widest expected QRS complex duration (~150 ms)."""
    n = max(1, int(round(window_sec * fs)))
    kernel = [1.0 / n] * n
    return _convolve_same(x, kernel)


# ── Pan-Tompkins pipeline ────────────────────────────────────────────

def pan_tompkins_pipeline(ecg, fs):
    """Run the full Pan-Tompkins signal processing pipeline.

    Returns dict with intermediate signals: filtered, derivative,
    squared, integrated.
    """
    filtered = bandpass_filter(ecg, fs)
    deriv = derivative_filter(filtered, fs)
    sq = squaring(deriv)
    integ = moving_window_integration(sq, fs)
    return {
        "filtered": filtered,
        "derivative": deriv,
        "squared": sq,
        "integrated": integ,
    }


# ── Local maxima detection ───────────────────────────────────────────

def _local_maxima(x):
    """Indices of all local maxima (strict) in list x."""
    if len(x) < 3:
        return []
    indices = []
    for i in range(1, len(x) - 1):
        if x[i] > x[i - 1] and x[i] > x[i + 1]:
            indices.append(i)
    return indices


# ── Adaptive thresholding / R-peak detection ─────────────────────────

def detect_r_peaks(ecg, fs, refractory_sec=0.200):
    """Run the full Pan-Tompkins pipeline and adaptive thresholding to
    locate R-peaks in the original ECG signal.

    Implements the classic Pan-Tompkins adaptive dual-threshold scheme:
      SPKI = running estimate of signal (QRS) peak level
      NPKI = running estimate of noise peak level
      THRESHOLD_I1 = NPKI + 0.25 * (SPKI - NPKI)

    A refractory period (default 200 ms) prevents double-detection.

    Returns (r_peak_indices, pipeline_dict).
    """
    pt = pan_tompkins_pipeline(ecg, fs)
    integ = pt["integrated"]

    candidate_idx = _local_maxima(integ)
    if not candidate_idx:
        return [], pt

    refractory_samples = int(round(refractory_sec * fs))

    # Initialize thresholds from the first 2 seconds
    init_n = min(len(integ), int(round(2.0 * fs)))
    init_window = integ[:init_n] if init_n > 0 else integ
    spki = max(init_window) * 0.25 if init_window else 0.0
    npki = (sum(init_window) / len(init_window)) * 0.5 if init_window else 0.0

    r_peaks = []
    last_peak_sample = -refractory_samples - 1

    for idx in candidate_idx:
        peak_val = integ[idx]
        threshold_i1 = npki + 0.25 * (spki - npki)

        if idx - last_peak_sample <= refractory_samples:
            continue

        if peak_val > threshold_i1:
            r_peaks.append(idx)
            last_peak_sample = idx
            spki = 0.125 * peak_val + 0.875 * spki
        else:
            npki = 0.125 * peak_val + 0.875 * npki

    # Refine to local max of the filtered ECG
    refined = _refine_to_local_max(pt["filtered"], r_peaks, fs)

    pt["r_peak_indices"] = refined
    return refined, pt


def _refine_to_local_max(filtered_ecg, approx_idx, fs, search_sec=0.10):
    """Snap each approximate R-peak index to the true local maximum of
    the bandpass-filtered ECG within +/- search_sec."""
    if not approx_idx:
        return approx_idx
    half_win = max(1, int(round(search_sec * fs)))
    n = len(filtered_ecg)
    refined = []
    for idx in approx_idx:
        lo = max(0, idx - half_win)
        hi = min(n, idx + half_win + 1)
        segment = filtered_ecg[lo:hi]
        if not segment:
            refined.append(idx)
            continue
        local_max = lo + segment.index(max(segment))
        refined.append(local_max)
    # Deduplicate
    return sorted(set(refined))


# ── Heart rate and HRV metrics ───────────────────────────────────────

def compute_hrv_metrics(r_peak_indices, fs):
    """Compute instantaneous/average heart rate and standard
    time-domain HRV metrics (SDNN, RMSSD, pNN50) from R-peak sample
    indices.

    Returns a dict with:
        n_beats, mean_hr_bpm, instantaneous_hr_bpm (list),
        rr_intervals_ms (list), sdnn_ms, rmssd_ms, pnn50_pct
    """
    n_beats = len(r_peak_indices)
    nan = float("nan")

    if n_beats < 2:
        return {
            "n_beats": n_beats,
            "mean_hr_bpm": nan,
            "instantaneous_hr_bpm": [],
            "rr_intervals_ms": [],
            "sdnn_ms": nan,
            "rmssd_ms": nan,
            "pnn50_pct": nan,
        }

    rr_samples = [r_peak_indices[i + 1] - r_peak_indices[i]
                  for i in range(len(r_peak_indices) - 1)]
    rr_sec = [s / fs for s in rr_samples]
    rr_ms = [s * 1000.0 for s in rr_sec]

    instantaneous_hr = [60.0 / s for s in rr_sec]
    mean_hr = sum(instantaneous_hr) / len(instantaneous_hr)

    # SDNN
    if len(rr_ms) > 1:
        mean_rr = sum(rr_ms) / len(rr_ms)
        variance = sum((v - mean_rr) ** 2 for v in rr_ms) / (len(rr_ms) - 1)
        sdnn = math.sqrt(variance)
    else:
        sdnn = nan

    # RMSSD
    successive_diffs = [rr_ms[i + 1] - rr_ms[i] for i in range(len(rr_ms) - 1)]
    if successive_diffs:
        rmssd = math.sqrt(sum(d * d for d in successive_diffs) / len(successive_diffs))
    else:
        rmssd = nan

    # pNN50
    if successive_diffs:
        nn50_count = sum(1 for d in successive_diffs if abs(d) > 50.0)
        pnn50 = 100.0 * nn50_count / len(successive_diffs)
    else:
        pnn50 = nan

    return {
        "n_beats": n_beats,
        "mean_hr_bpm": mean_hr,
        "instantaneous_hr_bpm": instantaneous_hr,
        "rr_intervals_ms": rr_ms,
        "sdnn_ms": sdnn,
        "rmssd_ms": rmssd,
        "pnn50_pct": pnn50,
    }


# ── Arrhythmia detection ─────────────────────────────────────────────

def detect_arrhythmia(metrics):
    """Classify rhythm from HRV metrics.

    Returns a dict with rhythm classification and flags.
    """
    mean_hr = metrics["mean_hr_bpm"]
    n_beats = metrics["n_beats"]

    if n_beats < 2:
        return {"rhythm": "insufficient_data", "flags": []}

    flags = []

    if mean_hr > 100:
        rhythm = "tachycardia"
    elif mean_hr < 60:
        rhythm = "bradycardia"
    else:
        rhythm = "normal_rate"

    # Check for irregularity using coefficient of variation of RR intervals
    rr_ms = metrics["rr_intervals_ms"]
    if len(rr_ms) > 1:
        mean_rr = sum(rr_ms) / len(rr_ms)
        std_rr = math.sqrt(sum((v - mean_rr) ** 2 for v in rr_ms) / (len(rr_ms) - 1))
        cv = std_rr / mean_rr if mean_rr > 0 else 0
        if cv > 0.15:
            flags.append("irregular_rhythm")
            if rhythm == "normal_rate":
                rhythm = "irregular_rhythm"

    if mean_hr > 150:
        flags.append("severe_tachycardia")
    if mean_hr < 40:
        flags.append("severe_bradycardia")

    return {
        "rhythm": rhythm,
        "mean_hr_bpm": round(mean_hr, 1),
        "flags": flags,
    }


# ── Synthetic ECG generator ──────────────────────────────────────────

def generate_synthetic_ecg(duration_sec=30.0, fs=250.0, heart_rate_bpm=70.0,
                           hrv_std_ms=20.0, noise_std=0.01, seed=42):
    """Generate a synthetic single-lead ECG made of repeated QRS-like
    Gaussian-derivative pulses (plus P and T waves), spaced at
    randomized R-R intervals so ground-truth R-peak locations are known.

    Returns (samples_list, true_r_peak_indices).
    """
    # Simple LCG random number generator for reproducibility
    class SimpleRNG:
        def __init__(self, seed):
            self.state = seed
        def random(self):
            self.state = (self.state * 1103515245 + 12345) & 0x7FFFFFFF
            return self.state / 0x7FFFFFFF
        def gauss(self, mu, sigma):
            # Box-Muller transform
            u1 = max(1e-10, self.random())
            u2 = self.random()
            z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
            return mu + sigma * z

    rng = SimpleRNG(seed)
    n_samples = int(round(duration_sec * fs))
    ecg = [0.0] * n_samples

    mean_rr = 60.0 / heart_rate_bpm
    beat_times = []
    current_t = mean_rr / 2.0
    while current_t < duration_sec:
        beat_times.append(current_t)
        jitter = rng.gauss(0.0, hrv_std_ms / 1000.0)
        current_t += max(0.25, mean_rr + jitter)

    def qrs_wave(t_val, center, width=0.02, amp=1.5):
        a = (t_val - center) / width
        return amp * (1 - a ** 2) * math.exp(-(a ** 2) / 2)

    def rounded_wave(t_val, center, width, amp):
        a = (t_val - center) / width
        return amp * math.exp(-(a ** 2) / 2)

    for i in range(n_samples):
        t_val = i / fs
        val = 0.0
        for bt in beat_times:
            val += qrs_wave(t_val, bt)
            val += rounded_wave(t_val, bt - 0.16, 0.035, 0.15)  # P wave
            val += rounded_wave(t_val, bt + 0.28, 0.07, 0.35)   # T wave
        # Baseline wander
        val += 0.05 * math.sin(2 * math.pi * 0.3 * t_val)
        # Noise
        val += rng.gauss(0.0, noise_std)
        ecg[i] = val

    # Compute true R-peak indices
    true_r_peaks = [int(round(bt * fs)) for bt in beat_times]
    true_r_peaks = [idx for idx in true_r_peaks if 0 <= idx < n_samples]

    return ecg, true_r_peaks


# ── CLI ──────────────────────────────────────────────────────────────

def _print_report(metrics, arrhythmia):
    """Print a human-readable report."""
    print(f"Detected R-peaks: {metrics['n_beats']}")
    if metrics["n_beats"] < 2:
        print("Not enough beats detected to compute heart rate / HRV metrics.")
        return
    print(f"Mean heart rate: {metrics['mean_hr_bpm']:.1f} bpm")
    hr_list = metrics["instantaneous_hr_bpm"]
    print(f"Instantaneous HR range: {min(hr_list):.1f}-{max(hr_list):.1f} bpm")
    print("HRV (time-domain):")
    print(f"  SDNN  = {metrics['sdnn_ms']:.2f} ms")
    print(f"  RMSSD = {metrics['rmssd_ms']:.2f} ms")
    print(f"  pNN50 = {metrics['pnn50_pct']:.2f} %")
    print(f"Rhythm: {arrhythmia['rhythm']}")
    if arrhythmia["flags"]:
        print(f"Flags: {', '.join(arrhythmia['flags'])}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Detect R-peaks in a single-lead ECG using Pan-Tompkins, "
        "and report heart rate / time-domain HRV metrics."
    )
    parser.add_argument("input_csv",
                        help="Path to ECG CSV file (time,amplitude or amplitude-only)")
    parser.add_argument("--fs", type=float, default=None,
                        help="Sampling rate in Hz (required for amplitude-only CSVs)")
    parser.add_argument("--refractory", type=float, default=0.200,
                        help="Refractory period in seconds (default: 0.200)")
    parser.add_argument("--out-csv", metavar="CSV_PATH", default=None,
                        help="Write detected R-peak times and R-R intervals to CSV")

    args = parser.parse_args(argv)

    try:
        ecg, fs = load_ecg_csv(args.input_csv, fs=args.fs)
    except (ValueError, OSError) as exc:
        print(f"Error loading ECG file: {exc}", file=sys.stderr)
        return 1

    r_peaks, pt_result = detect_r_peaks(ecg, fs, refractory_sec=args.refractory)
    metrics = compute_hrv_metrics(r_peaks, fs)
    arrhythmia = detect_arrhythmia(metrics)

    print(f"Loaded {len(ecg)} samples at {fs:.2f} Hz ({len(ecg) / fs:.1f} s)")
    _print_report(metrics, arrhythmia)

    if args.out_csv:
        _write_peaks_csv(args.out_csv, r_peaks, fs, metrics)
        print(f"Wrote R-peak/R-R data to {args.out_csv}")

    return 0


def _write_peaks_csv(path, r_peaks, fs, metrics):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["r_peak_index", "r_peak_time_sec", "rr_interval_ms",
                         "instantaneous_hr_bpm"])
        for i, idx in enumerate(r_peaks):
            t = idx / fs
            if i == 0:
                writer.writerow([idx, f"{t:.4f}", "", ""])
            else:
                writer.writerow([
                    idx,
                    f"{t:.4f}",
                    f"{metrics['rr_intervals_ms'][i - 1]:.2f}",
                    f"{metrics['instantaneous_hr_bpm'][i - 1]:.2f}",
                ])


if __name__ == "__main__":
    sys.exit(main())
