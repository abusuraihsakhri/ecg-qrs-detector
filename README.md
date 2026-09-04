# ECG QRS Detector

> **Domain:** Cardiovascular Medicine & Hemodynamic Analytics
> **Reference Guidelines & Standards:** AHA/ACC Practice Guidelines & ESC Clinical Standards

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB.svg?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg?logo=fastapi&logoColor=white)
![Audit Trail](https://img.shields.io/badge/Audit-HMAC--SHA256_Tamper--Evident-brightgreen.svg)
![Zero-PHI Guard](https://img.shields.io/badge/Guard-Zero--PHI_Outbound-blue.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker&logoColor=white)

</div>

---

## What It Does

ECG QRS Detector detects R-peaks in a digitized single-lead ECG signal using a
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
- **SDNN**  = standard deviation of all N-N (R-R) intervals
- **RMSSD** = root mean square of successive differences between N-N intervals
- **pNN50** = percentage of successive N-N interval differences > 50 ms

Stdlib only for core detection — no numpy/scipy required.

---

## Installation

```bash
# Clone the repository
git clone https://github.com/abusuraihsakhri/ecg-qrs-detector.git
cd ecg-qrs-detector

# Create virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
pip install fastapi uvicorn pydantic pytest
```

---

## Usage

### Command Line Interface

#### 1. Detect R-peaks from a CSV file
```bash
python cli.py detect sample_ecg.csv
python cli.py detect sample_ecg.csv --fs 250 --refractory 0.200 --out-csv peaks.csv
```

#### 2. Run demo with synthetic ECG
```bash
python cli.py demo --duration 30 --fs 250 --hr 70
```

#### 3. Audit commands
```bash
python cli.py audit --task-id MY-TASK-01
python cli.py chat "Explain QRS detection"
python cli.py verify-audit
```

#### 4. Direct module usage
```bash
python qrs_detector.py sample_ecg.csv --fs 250
```

### Python API

```python
from qrs_detector import load_ecg_csv, detect_r_peaks, compute_hrv_metrics, detect_arrhythmia

# Load ECG data
samples, fs = load_ecg_csv("sample_ecg.csv")

# Detect R-peaks
r_peaks, pipeline = detect_r_peaks(samples, fs, refractory_sec=0.200)

# Compute HRV metrics
metrics = compute_hrv_metrics(r_peaks, fs)
print(f"Mean HR: {metrics['mean_hr_bpm']:.1f} bpm")
print(f"SDNN: {metrics['sdnn_ms']:.2f} ms")
print(f"RMSSD: {metrics['rmssd_ms']:.2f} ms")

# Detect arrhythmia
arrhythmia = detect_arrhythmia(metrics)
print(f"Rhythm: {arrhythmia['rhythm']}")
```

### FastAPI Web Server

```bash
uvicorn agents.api:app --reload
```

Endpoints:
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics
- `POST /api/audit` - Process audit task
- `POST /api/chat` - Query supervisory chat
- `GET /api/audit/logs` - View audit trail

---

## Input Data Format

### CSV Format (auto-detected)

**Two columns** (time, amplitude):
```csv
time_s,amplitude_mV
0.000,0.001
0.004,0.003
...
```

**One column** (amplitude only, requires `--fs`):
```csv
amplitude_mV
0.001
0.003
...
```

---

## Key Modules

| Module | Description |
|:-------|:------------|
| `qrs_detector.py` | Core Pan-Tompkins algorithm, filtering, R-peak detection, HRV metrics |
| `cli.py` | Command-line interface with detect, demo, audit, chat commands |
| `agents/base.py` | PHI guard, HMAC-SHA256 audit trail, security utilities |
| `agents/supervisor.py` | Multi-worker orchestration and consensus |
| `agents/workers.py` | QC, safety, and protocol conformance workers |
| `agents/api.py` | FastAPI REST endpoints |
| `enrichment.py` | Domain enrichment and analysis engines |
| `simulator.py` | High-throughput simulation testing |

---

## Security Features

- **Zero-PHI Outbound Interceptor:** AST and regex inspection blocking SSNs, MRNs, phone numbers, and patient identifiers
- **Tamper-Evident HMAC-SHA256 Audit Trail:** Chained, cryptographically signed logs
- **Configurable Audit Key:** Set `AUDIT_SECRET_KEY` environment variable for persistent audit trails

---

## Testing

```bash
# Run all tests
pytest -v

# Run specific test files
pytest test_qrs_detector.py -v
pytest tests/test_ecg_qrs_detector.py -v
pytest tests/test_enrichment.py -v
```

---

## Container Deployment

```bash
docker build -t ecg-qrs-detector .
docker run -p 8000:8000 ecg-qrs-detector
```

---

## License

MIT License - see [LICENSE](LICENSE) for details.
