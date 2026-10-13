# ECG QRS Detector

### [Open the Live Application →](https://abusuraihsakhri.github.io/ecg-qrs-detector/)

Analyze digitized **single-lead ECG** signals with a simplified Pan–Tompkins-style R-peak detector. Outputs include detected peak indices/times, estimated heart rate, RR intervals, and exploratory time-domain variability metrics (SDNN, RMSSD, pNN50).

The **browser application runs the same Python algorithm locally through Pyodide**. No Python server is required for GitHub Pages.

## Features

- Load one-column amplitude CSV (sampling rate required), or two-column time-in-seconds/amplitude CSV (rate inferred from timestamps).
- Detect R-peaks; view an ECG plot with peak markers; export peak indices, times, RR intervals and instantaneous heart rate.
- Try a deterministic synthetic ECG demonstration without uploading data.
- Run the detector directly from Python or the command line.
- Optionally run a separate FastAPI demonstration service offering audit/worker and mock-chat endpoints; these are **not** ECG analysis endpoints.

## Use the browser app

1. Open the live application and allow Pyodide to load (a network connection is required on first load).
2. Choose an ECG CSV file, optionally enter its sampling rate, and select **Analyze CSV**.
3. Review the waveform and computed metrics, then select **Export detected peaks (CSV)**.
4. Alternatively, select **Try synthetic ECG** to exercise the detector without a file.

Browser limits: **3 MB / 250,000 samples** per file. Files are processed in browser memory; the application does not transmit ECG samples to a server. Pyodide runtime files are loaded from a third-party CDN. The browser interface does not rely on the FastAPI backend.

## Command line

The core Python detector uses only Python's standard library (Python 3.10+).

~~~bash
git clone https://github.com/abusuraihsakhri/ecg-qrs-detector.git
cd ecg-qrs-detector

python cli.py demo --duration 12 --fs 250 --hr 72
python cli.py detect sample_ecg.csv --out-csv peaks.csv
python cli.py detect single_column.csv --fs 250 --refractory 0.2
python qrs_detector.py sample_ecg.csv --out-csv peaks.csv
~~~

One-column CSVs require a sampling rate; two-column CSVs must contain strictly increasing timestamps. Inputs with non-finite values are rejected.

### Python API

~~~python
from qrs_detector import load_ecg_csv, detect_r_peaks, compute_hrv_metrics

samples, sampling_rate = load_ecg_csv("sample_ecg.csv")
peaks, intermediate_signals = detect_r_peaks(samples, sampling_rate)
metrics = compute_hrv_metrics(peaks, sampling_rate)
print(metrics["n_beats"], metrics["mean_hr_bpm"])
~~~

## Separate FastAPI demonstration

The optional agent/audit service is independent of the ECG browser application. It requires FastAPI, Uvicorn and Pydantic.

~~~bash
python -m pip install -r requirements.txt
uvicorn agents.api:app --host 127.0.0.1 --port 8000
~~~

The service offers /health, /metrics, /api/audit, /api/chat and /api/audit/logs. Its chat adapter is a **deterministic mock**, not clinical reasoning or a live language-model connection. The audit record is an in-memory HMAC chain. Set AUDIT_SECRET_KEY to a strong environment secret if signatures must remain reproducible across restarts; persistence of the log itself is not implemented.

The API has **no authentication** and should be bound to localhost only. Do not publish it to the internet or submit clinical identifiers. Its pattern-based PHI guard cannot establish de-identification or HIPAA compliance.

For Docker Compose, set AUDIT_SECRET_KEY in your shell or private .env file before starting:

~~~bash
docker compose up --build
~~~

Compose maps the service to 127.0.0.1:8000 by default; no audit key is embedded in configuration.

## Development and tests

~~~bash
python -m pip install -r requirements.txt pytest
python -m pytest -q
python -m compileall -q qrs_detector.py cli.py agents enrichment.py web/analysis.py
node --check web/app.js
~~~

GitHub Actions tests Python 3.10–3.12 plus browser/Pyodide CSV export and Docker health checks. GitHub Pages publishes the web directory with the detector module copied into the deployment artifact.

## Methodological limitations

The detector uses fixed Pan–Tompkins-inspired integer filter coefficients, derivative, squaring, moving-window integration and adaptive thresholds. **These filter coefficients are not rescaled for arbitrary sampling rates.** Peak detection has not been clinically validated against annotated ECG databases; neither sensitivity nor positive predictive value should be inferred from synthetic tests.

Heart rate is calculated as 60 divided by the mean RR interval. SDNN, RMSSD and pNN50 here are calculated from detected RR intervals; **they are not necessarily normal-to-normal (NN) metrics** without artifact and ectopic-beat review. The rate/regularity flags returned by the detector are heuristic descriptions, not ECG diagnoses.

**Research and education only. Not a medical device or a tool for clinical decisions, monitoring, or emergencies.**

## Browser compatibility and license

Use a modern Chrome, Firefox, Safari or Edge with WebAssembly enabled and connectivity to the Pyodide CDN. See [LICENSE](LICENSE) for the MIT license.
