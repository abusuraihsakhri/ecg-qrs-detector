"""Regression tests for numerical correctness, browser analysis and audit integrity."""
import csv
import json
import math
from pathlib import Path

import pytest

from agents.base import AuditTrail
from qrs_detector import (
    compute_hrv_metrics, detect_r_peaks, generate_synthetic_ecg, load_ecg_csv,
)
from web.analysis import analyze_csv, analyze_demo


def test_heart_rate_uses_mean_rr_interval():
    # Intervals 500 ms and 1500 ms -> 60 bpm, not mean(120, 40) = 80 bpm.
    result = compute_hrv_metrics([0, 500, 2000], fs=1000)
    assert result["mean_hr_bpm"] == pytest.approx(60.0)
    assert result["instantaneous_hr_bpm"] == pytest.approx([120.0, 40.0])


@pytest.mark.parametrize("fs", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_sampling_rate_rejected(fs):
    with pytest.raises(ValueError, match="Sampling rate"):
        detect_r_peaks([0.1, 0.2], fs)
    with pytest.raises(ValueError, match="Sampling rate"):
        compute_hrv_metrics([0, 10], fs)


def test_non_finite_ecg_samples_rejected():
    with pytest.raises(ValueError, match="finite"):
        detect_r_peaks([0.0, float("nan"), 1.0], 250)


def test_non_increasing_timestamps_rejected(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("time,amplitude\n0.0,0.0\n0.02,0.2\n0.01,0.1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="strictly increasing"):
        load_ecg_csv(path)


def test_ragged_csv_rejected(tmp_path):
    path = tmp_path / "ragged.csv"
    path.write_text("time,amplitude\n0.0,0.0\n0.01\n", encoding="utf-8")
    with pytest.raises(ValueError, match="consistent"):
        load_ecg_csv(path)


@pytest.mark.parametrize("value", ["NaN", "Infinity"])
def test_non_finite_csv_value_rejected(tmp_path, value):
    path = tmp_path / "bad.csv"
    path.write_text("time,amplitude\n0,0.1\n0.004," + value + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="non-finite"):
        load_ecg_csv(path)


def test_browser_demo_produces_real_peaks_and_json():
    result = json.loads(analyze_demo(duration=8.0, fs=250.0, heart_rate=70.0))
    assert result["sample_count"] == 2000
    assert len(result["peaks"]) == result["metrics"]["n_beats"]
    assert 5 <= len(result["peaks"]) <= 14
    assert len(result["plot"]) <= 1400
    assert all(len(point) == 2 for point in result["peak_points"])


def test_browser_csv_roundtrip():
    samples, _ = generate_synthetic_ecg(duration_sec=6, fs=250.0)
    text = "time_s,amplitude_mV\n" + "".join(
        f"{index/250:.4f},{value:.8f}\n" for index, value in enumerate(samples)
    )
    result = json.loads(analyze_csv(text))
    assert result["sample_count"] == len(samples)
    assert result["fs"] == pytest.approx(250.0)
    assert len(result["peaks"]) >= 4


def test_browser_csv_rejects_invalid_inputs():
    with pytest.raises(ValueError, match="non-empty"):
        analyze_csv(" ")
    with pytest.raises(ValueError, match="positive"):
        analyze_csv("amplitude\n1.0\n", fs_override=0)


def test_audit_hmac_detects_metadata_tampering():
    audit = AuditTrail(secret_key="test-key")
    audit.log("actor", "tier", "event", {"status": "PASS"})
    assert audit.verify_integrity() is True
    audit.logs[0]["actor"] = "tampered"
    assert audit.verify_integrity() is False


def test_audit_hmac_detects_signature_tampering():
    audit = AuditTrail(secret_key="test-key")
    audit.log("actor", "tier", "event", {"status": "PASS"})
    audit.logs[0]["current_hash"] = "0" * 64
    assert audit.verify_integrity() is False


def test_browser_assets_and_no_backend_dependency():
    page = (Path(__file__).parent.parent / "web" / "index.html").read_text(encoding="utf-8")
    script = (Path(__file__).parent.parent / "web" / "app.js").read_text(encoding="utf-8")
    assert "./app.js" in page and "pyodide.js" in page
    assert "analysis.analyze_csv" in script
    assert "fetch('/api/audit'" not in script
    assert "Offline / Simulation Output" not in script
