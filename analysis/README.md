# IRT analysis (MRKT341 quiz)

## Setup

Create and activate a virtual environment, then install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r analysis/requirements.txt
```

## Run

```bash
python analysis/irt_run.py \
  --input "Data/De-identified MRKT341 Results.csv" \
  --out_dir "analysis/out"
```

Outputs are written to a timestamped folder under `analysis/out/`.

## What the script expects

- **Student identifier**: `Study ID`
- **GPA**: `Cum GPA` (0–4.0)
- **Major**: `Major`
- **Items**: 16 score columns named like `0.25`, `0.25.1`, ... (values are `0` or `0.25`)

The script converts each item to binary: `0.25 → 1` and `0 → 0`.

## Note on duplicate `Study ID`

This dataset contains repeated `Study ID` values (multiple rows per ID). The script keeps **one row per `Study ID`** by selecting the row with the **highest total score** across the 16 scored items.

