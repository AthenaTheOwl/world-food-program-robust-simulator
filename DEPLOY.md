# Deploy — Streamlit Community Cloud

The Food Relief Simulator is in deployable shape. To put it on a public
URL:

1. Sign in at https://share.streamlit.io with the GitHub account that
   owns `AthenaTheOwl/world-food-program-robust-simulator` (one-time
   browser auth).
2. Click **New app** → **From existing repo**.
3. Fill in:
   - **Repository**: `AthenaTheOwl/world-food-program-robust-simulator`
   - **Branch**: `main`
   - **Main file path**: `app.py`
   - **Advanced settings → Python version**: `3.11`
   - **Secrets**: leave empty — no API keys needed.
4. Click **Deploy**.

> The `requirements.txt` sits next to `app.py` at this repo's root.

## Local dev

```bash
pip install -r requirements.txt
streamlit run app.py
```

## What the app does

A robust-optimization simulator for World-Food-Programme-style food
relief routing in Syria:
- Pick demand-uncertainty parameters.
- Compare nominal vs robust shipment plans.
- See nutrition and cost trade-offs across nodes/edges.

Pure CVXPY; no external services.

## Note on repo layout

The deployed repo (`world-food-program-robust-simulator`) contains only
this `food-relief-simulator` working tree — the textbook PDFs from the
original homework set live in the local clone outside the repo root
and are not committed.
