"""Tests for qrs_detector.py — ECG QRS Detector (stdlib only).

Run with: python -m pytest test_qrs_detector.py -v
"""
import csv
import math
import os
import tempfile
import pytest
from qrs_detector import (
    bandpass_filter, derivative_filter, squaring, moving_window_integration,
    pan_tompkins_pipeline, detect_r_peaks, compute_hrv_metrics,
    detect_arrhythmia, generate_synthetic_ecg, load_ecg_csv,
    _local_maxima, _convolve,
)


# ── Signal processing primitives ────────────────────────────────────

class TestConvolve:
    def test_identity_kernel(self):
        # Convolution with [1] should return the same signal
        signal = [1.0, 2.0, 3.0, 4.0]
        result = _convolve(signal, [1.0])
        assert result == pytest.approx(signal)

    def test_averaging(self):
        # Convolution with [0.5, 0.5] gives running average
        signal = [1.0, 3.0, 5.0, 7.0]
        result = _convolve(signal, [0.5, 0.5])
        assert result[0] == pytest.approx(0.5)
        assert result[1] == pytest.approx(2.0)
        assert result[2] == pytest.approx(4.0)


class TestBandpassFilter:
    def test_preserves_length(self):
        signal = [math.sin(2 * math.pi * 10 * i / 250) for i in range(500)]
        filtered = bandpass_filter(signal, 250.0)
        assert len(filtered) == len(signal)

    def test_removes_dc(self):
        # Constant signal should be removed by high-pass component
        signal = [5.0] * 500
        filtered = bandpass_filter(signal, 250.0)
        # After filtering, the middle portion should be near zero
        mid = filtered[100:400]
        assert all(abs(v) < 1.0 for v in mid)


class TestDerivativeFilter:
    def test_constant_signal_zero(self):
        signal = [5.0] * 100
        result = derivative_filter(signal, 250.0)
        # Derivative of constant should be zero (except at edges)
        for i in range(10, 90):
            assert abs(result[i]) < 0.01

    def test_linear_ramp_constant(self):
        # Linear ramp should give constant derivative
        signal = [i * 0.01 for i in range(100)]
        result = derivative_filter(signal, 250.0)
        # Middle values should be approximately constant
        mid_vals = [result[i] for i in range(20, 80)]
        assert max(mid_vals) - min(mid_vals) < 0.01


class TestSquaring:
    def test_positive_values(self):
        assert squaring([1, -2, 3, -4]) == [1, 4, 9, 16]

    def test_zeros(self):
        assert squaring([0, 0, 0]) == [0, 0, 0]


class TestMovingWindowIntegration:
    def test_preserves_length(self):
        signal = [1.0] * 100
        result = moving_window_integration(signal, 250.0)
        assert len(result) == len(signal)

    def test_constant_input(self):
        signal = [2.0] * 100
        result = moving_window_integration(signal, 250.0)
        # Middle values should be approximately 2.0
        for i in range(20, 80):
            assert abs(result[i] - 2.0) < 0.1


class TestLocalMaxima:
    def test_simple_peak(self):
        assert _local_maxima([0, 1, 0]) == [1]

    def test_two_peaks(self):
        assert _local_maxima([0, 1, 0, 2, 0]) == [1, 3]

    def test_no_peaks(self):
        assert _local_maxima([1, 2, 3, 4, 5]) == []

    def test_flat(self):
        assert _local_maxima([1, 1, 1]) == []


# ── R-peak detection ────────────────────────────────────────────────

class TestRPeakDetection:
    def test_detects_beats_at_70bpm(self):
        """Synthetic 30s ECG at 70 bpm should yield ~35 beats."""
        fs = 250.0
        hr_true = 70.0
        ecg, true_peaks = generate_synthetic_ecg(
            duration_sec=30.0, fs=fs, heart_rate_bpm=hr_true,
            hrv_std_ms=15.0, noise_std=0.01, seed=1,
        )
        r_peaks, _ = detect_r_peaks(ecg, fs)
        metrics = compute_hrv_metrics(r_peaks, fs)

        expected_beats = 30.0 / (60.0 / hr_true)
        assert abs(len(r_peaks) - expected_beats) < 5
        assert abs(metrics["mean_hr_bpm"] - hr_true) < 10.0

    def test_detects_beats_at_110bpm(self):
        """Faster ECG at 110 bpm."""
        fs = 360.0
        hr_true = 110.0
        ecg, true_peaks = generate_synthetic_ecg(
            duration_sec=20.0, fs=fs, heart_rate_bpm=hr_true,
            hrv_std_ms=10.0, noise_std=0.015, seed=7,
        )
        r_peaks, _ = detect_r_peaks(ecg, fs)
        metrics = compute_hrv_metrics(r_peaks, fs)

        expected_beats = 20.0 / (60.0 / hr_true)
        assert abs(len(r_peaks) - expected_beats) < 5
        assert abs(metrics["mean_hr_bpm"] - hr_true) < 10.0

    def test_flat_signal_no_beats(self):
        """Flat signal should yield no R-peaks."""
        ecg = [0.0] * 1000
        r_peaks, _ = detect_r_peaks(ecg, 250.0)
        assert len(r_peaks) == 0

    def test_refractory_period(self):
        """Two pulses 80ms apart should be collapsed to one beat."""
        fs = 250.0
        n = 1000
        ecg = [0.0] * n
        # Create two sharp peaks 80ms apart
        for i in range(n):
            t = i / fs
            for center in [1.0, 1.08]:
                a = (t - center) / 0.02
                ecg[i] += 1.5 * (1 - a ** 2) * math.exp(-(a ** 2) / 2)
        r_peaks, _ = detect_r_peaks(ecg, fs, refractory_sec=0.200)
        assert len(r_peaks) == 1


# ── HRV metrics ─────────────────────────────────────────────────────

class TestHRVMetrics:
    def test_known_rr_series(self):
        """Verify SDNN, RMSSD, pNN50 on known R-R series."""
        fs = 1000.0
        rr_ms = [800.0, 810.0, 850.0, 800.0, 900.0]
        r_peak_indices = [0]
        for rr in rr_ms:
            r_peak_indices.append(r_peak_indices[-1] + int(rr))

        metrics = compute_hrv_metrics(r_peak_indices, fs)

        # SDNN
        mean_rr = sum(rr_ms) / len(rr_ms)
        expected_sdnn = math.sqrt(sum((v - mean_rr) ** 2 for v in rr_ms) / (len(rr_ms) - 1))
        assert abs(metrics["sdnn_ms"] - expected_sdnn) < 0.1

        # RMSSD
        diffs = [rr_ms[i + 1] - rr_ms[i] for i in range(len(rr_ms) - 1)]
        expected_rmssd = math.sqrt(sum(d * d for d in diffs) / len(diffs))
        assert abs(metrics["rmssd_ms"] - expected_rmssd) < 0.1

        # pNN50: diffs are [10, 40, -50, 100] -> only |100| > 50 -> 1/4 = 25%
        assert abs(metrics["pnn50_pct"] - 25.0) < 0.1

    def test_constant_rr(self):
        """Perfectly regular 1000ms R-R → HR=60, SDNN=0, RMSSD=0."""
        fs = 1000.0
        r_peak_indices = list(range(0, 10000, 1000))
        metrics = compute_hrv_metrics(r_peak_indices, fs)

        assert abs(metrics["mean_hr_bpm"] - 60.0) < 0.01
        assert abs(metrics["sdnn_ms"]) < 0.01
        assert abs(metrics["rmssd_ms"]) < 0.01
        assert abs(metrics["pnn50_pct"]) < 0.01

    def test_single_beat_nan(self):
        """Single beat should return NaN for all metrics."""
        metrics = compute_hrv_metrics([100], 250.0)
        assert metrics["n_beats"] == 1
        assert math.isnan(metrics["mean_hr_bpm"])
        assert math.isnan(metrics["sdnn_ms"])

    def test_empty_peaks(self):
        """No beats should return NaN."""
        metrics = compute_hrv_metrics([], 250.0)
        assert metrics["n_beats"] == 0


# ── Arrhythmia detection ────────────────────────────────────────────

class TestArrhythmiaDetection:
    def test_tachycardia(self):
        metrics = {
            "n_beats": 30,
            "mean_hr_bpm": 120.0,
            "rr_intervals_ms": [500.0] * 29,
        }
        result = detect_arrhythmia(metrics)
        assert result["rhythm"] == "tachycardia"

    def test_bradycardia(self):
        metrics = {
            "n_beats": 20,
            "mean_hr_bpm": 50.0,
            "rr_intervals_ms": [1200.0] * 19,
        }
        result = detect_arrhythmia(metrics)
        assert result["rhythm"] == "bradycardia"

    def test_normal_rate(self):
        metrics = {
            "n_beats": 35,
            "mean_hr_bpm": 70.0,
            "rr_intervals_ms": [857.0] * 34,
        }
        result = detect_arrhythmia(metrics)
        assert result["rhythm"] == "normal_rate"

    def test_insufficient_data(self):
        metrics = {"n_beats": 1, "mean_hr_bpm": float("nan"), "rr_intervals_ms": []}
        result = detect_arrhythmia(metrics)
        assert result["rhythm"] == "insufficient_data"


# ── CSV loading ─────────────────────────────────────────────────────

class TestInputValidation:
    def test_detect_r_peaks_invalid_fs(self):
        with pytest.raises(ValueError, match="Sampling rate fs must be positive"):
            detect_r_peaks([1.0, 2.0, 3.0], fs=0)
        with pytest.raises(ValueError, match="Sampling rate fs must be positive"):
            detect_r_peaks([1.0, 2.0, 3.0], fs=-100)

    def test_detect_r_peaks_negative_refractory(self):
        with pytest.raises(ValueError, match="Refractory period must be non-negative"):
            detect_r_peaks([1.0, 2.0, 3.0], fs=250, refractory_sec=-0.1)

    def test_detect_r_peaks_empty_signal(self):
        r_peaks, pt = detect_r_peaks([], fs=250)
        assert len(r_peaks) == 0

    def test_compute_hrv_metrics_invalid_fs(self):
        with pytest.raises(ValueError, match="Sampling rate fs must be positive"):
            compute_hrv_metrics([0, 100, 200], fs=0)

    def test_generate_synthetic_ecg_invalid_params(self):
        with pytest.raises(ValueError, match="Duration must be positive"):
            generate_synthetic_ecg(duration_sec=0, fs=250)
        with pytest.raises(ValueError, match="Sampling rate fs must be positive"):
            generate_synthetic_ecg(fs=0)
        with pytest.raises(ValueError, match="Heart rate must be positive"):
            generate_synthetic_ecg(heart_rate_bpm=0)


class TestCSVLoding:
    def test_two_column_csv(self):
        fs_true = 200.0
        n = 500
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["time_s", "amplitude_mV"])
            for i in range(n):
                t = i / fs_true
                amp = math.sin(2 * math.pi * 1.0 * t)
                writer.writerow([f"{t:.6f}", f"{amp:.6f}"])
            path = f.name

        try:
            samples, fs = load_ecg_csv(path)
            assert len(samples) == n
            assert abs(fs - fs_true) < 1.0
        finally:
            os.remove(path)

    def test_single_column_requires_fs(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["amplitude"])
            for v in [0.1, 0.2, 0.15, 0.05]:
                writer.writerow([v])
            path = f.name

        try:
            with pytest.raises(ValueError):
                load_ecg_csv(path)
            samples, fs = load_ecg_csv(path, fs=250.0)
            assert len(samples) == 4
        finally:
            os.remove(path)
