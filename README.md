# ALMFirst-Pipeline

Sales targeting and pipeline tool for ALM First's Southeast territory
(credit unions). It answers three questions every morning:

1. **Who should I work today?** Follow-ups that are due, then the highest-value untouched targets.
2. **What should I pitch them?** Product fit per credit union, scored from its public balance sheet, with the reasons listed.
3. **Where are they?** A map of every credit union in the territory, sized by total assets.

## Run it

**Mac:** double-click `RUN_ME_MAC.command`. **Windows:** double-click `RUN_ME_WINDOWS.bat`.
It installs what it needs and opens <http://localhost:8501>.

By hand:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Refresh the data when NCUA publishes a new quarter (about 60 days after quarter end):

```bash
python scripts/build_data.py            # newest quarter
python scripts/build_data.py --quarter 2026-09
```

## HTML report (no install)

`docs/report.html` is a single file with the map, ranked targets, per-CU detail and the scoring rules.
Double-click it to open in any browser. Rebuild it after editing `config/*.yaml`:

```bash
python scripts/build_report.py
```

## Tabs

| Tab | What it does |
|---|---|
| 📋 Today | Ranked call list: due or overdue follow-ups first, then top new targets, each with a pitch and the reasons |
| 🗺️ Map | Every CU in the filters. Bubble = assets. Color = top product, priority or pipeline stage |
| 🎯 Targets | Sortable ranked table with fit per product and key ratios. Export to CSV |
| 🏦 Credit union | One-CU view: metrics, product fit and reasons, national peer percentiles, pipeline form |
| 🧭 Pipeline & import | Your stages and next actions. Upload a Salesforce CSV to match accounts to NCUA charters |
| 📊 Territory | State summary and revenue pool |

## Data (all public)

* **NCUA 5300 Call Report**, quarterly bulk file: every federally insured credit union's profile and full balance sheet.
  The dataset keeps all ~4,300 US credit unions so peer comparisons are national. The app filters to `config/territory.yaml`.
* **Census 2024 Gazetteer** (ZIP + place centroids) for map locations. No API keys.

## Where the logic lives

* `config/territory.yaml`: states and minimum asset size.
* `config/products.yaml`: **the targeting brain.** Size gates, signals, points, reasons and *placeholder* fees per product.
  Edit a threshold and the app re-scores on the next refresh.
* `src/almpipe/`: loader (`ncua.py`), ratios (`metrics.py`), scoring (`scoring.py`), pipeline and Salesforce matching (`pipeline.py`).

## Privacy rule

`data/private/` is git-ignored: the pipeline, the ALM First client list and anything from Salesforce go there.
**Never commit contact names, emails, phone numbers or Salesforce exports.** The repo holds code and public data only.

## Tests

```bash
pytest -q
```

See `docs/PLAN.md` for the roadmap and open questions.
