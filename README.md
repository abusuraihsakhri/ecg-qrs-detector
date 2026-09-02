# ECG Qrs Detector

> **Domain:** Cardiovascular Medicine & Hemodynamic Analytics  
> **Reference Guidelines & Standards:** `AHA/ACC Practice Guidelines & ESC Clinical Standards`

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB.svg?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg?logo=fastapi&logoColor=white)
![Audit Trail](https://img.shields.io/badge/Audit-HMAC--SHA256_Tamper--Evident-brightgreen.svg)
![Zero-PHI Guard](https://img.shields.io/badge/Guard-Zero--PHI_Outbound-blue.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker&logoColor=white)

</div>

---

## 📖 What It Does

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

---

## ⚙️ Key Capabilities & Algorithmic Modules

### 🔬 Analytical Functions

- **`load_ecg_csv()`**: Load a single-lead ECG waveform from a CSV file.

Accepted formats (auto-detected from the header row):
  - two columns: time_seconds, amplitude  -> fs derived from time column
  - one column: amplitude                 -> fs must be supplied

Returns (samples_list, fs).
- **`bandpass_filter()`**: Bandpass filter using Pan-Tompkins cascaded low-pass + high-pass.

The LP filter removes high-frequency noise; the HP filter removes
baseline wander and DC offset. Together they isolate the 5-15 Hz
band where QRS energy is concentrated.

Uses the original Pan-Tompkins integer-coefficient difference equations:
  LP: y[n] = 2*y[n-1] - y[n-2] + x[n] - 2*x[n-6] + x[n-12]
  HP: y[n] = y[n-1] - x[n]/32 + x[n-16] - x[n-17] + x[n-32]/32
- **`lowpass_filter()`**: Pan-Tompkins low-pass filter (integer coefficients).

Difference equation: y[n] = 2*y[n-1] - y[n-2] + x[n] - 2*x[n-6] + x[n-12]
- **`highpass_filter()`**: Pan-Tompkins high-pass filter (integer coefficients).

Difference equation: y[n] = y[n-1] - x[n]/32 + x[n-16] - x[n-17] + x[n-32]/32
- **`derivative_filter()`**: 5-point derivative approximation from Pan-Tompkins:
y[n] = (1/8T)(-x[n-2] - 2x[n-1] + 2x[n+1] + x[n+2])

---

## 📐 Mathematical Formulation & Logic

```text
  Time-domain HRV formulas:
```

---

## 💻 CLI Quickstart & Usage

### 1. Guided Interactive Mode
```bash
python cli.py
```

### 2. Direct Parameterized Evaluation
```bash
python cli.py --fs <value> --refractory <value> --out-csv <value> --duration <value>
```

### Parameter Reference
- `--fs`: Specifies input measurement or parameter value.
- `--refractory`: Specifies input measurement or parameter value.
- `--out-csv`: Specifies input measurement or parameter value.
- `--duration`: Specifies input measurement or parameter value.
- `--hr`: Specifies input measurement or parameter value.

### Input Data Schema

| Field | Description | Requirement |
|:------|:------------|:------------|
| `suite_name` | Parameter / observation metric | Required |
| `system_slug` | Parameter / observation metric | Required |
| `standard_reference` | Parameter / observation metric | Required |
| `test_cases` | Parameter / observation metric | Required |

---

## 🛡️ Security & Enterprise Architecture

* **Zero-PHI Outbound Interceptor:** Active AST and regex inspection blocking SSNs, MRNs, phone numbers, and patient identifiers.
* **Tamper-Evident HMAC-SHA256 Audit Trail:** Chained, cryptographically signed logs for every evaluation and state transition.
* **Air-Gapped LLM Reasoning Adapter:** Agnostic integration for local Ollama instances (`llama3`, `mistral`), Claude 3.5 Sonnet, GPT-4o, and deterministic test mocks.
* **Active Learning Bayesian Calibration:** Dynamic tracker updating worker reliability weights and monitoring Brier calibration drift.
* **FastAPI & Prometheus Telemetry:** Exposes OpenAPI 3.1 REST endpoints and operational Prometheus metrics (`/metrics`).

---

## 🧪 Testing & Verification

Run the automated test suite:

```bash
pytest -v
```

Execute high-throughput batch simulation benchmarks:

```bash
python simulator.py --tasks 1000 --concurrency 8
```

---

## 🐳 Container Deployment

```bash
docker build -t ecg-qrs-detector .
docker run -p 8000:8000 ecg-qrs-detector
```
