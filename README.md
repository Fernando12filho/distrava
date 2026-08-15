# Distrava

A local-first, open-source desktop app that replicates Strava's paid run-analysis
features — best efforts, HR zones, splits, training load, race predictions — with
no accounts, no subscriptions, and no GPS tracking. Everything runs on your own
machine against a local SQLite database.

## Requirements

- Python 3.11+
- Windows, macOS, or Linux (desktop window via PyWebView)

## Setup

```bash
pip install -r requirements.txt
```

## Running the app

```bash
python run.py
```

This starts a local Flask server in the background and opens the app in a native
desktop window (no browser chrome). Your data is stored in `./data/fitness.db`.

## Using it

1. Go to **Import** and choose an Apple Health `export.zip` (Settings → your name
   → Export All Health Data on iPhone), or a `.gpx` / `.csv` file.
2. Browse imported runs under **Activities**, click into one for HR/pace/elevation
   charts and auto-splits.
3. Set your resting/max heart rate under **Settings** — this feeds the TRIMP,
   CTL/ATL (fitness/fatigue), and HR zone calculations. If you don't set a max HR,
   it falls back to `220 - age` using your birth year.
4. Check **Dashboard** for weekly summary, monthly trend, current fitness/fatigue,
   and personal bests across the standard race distances.

## Running the tests

```bash
pytest
pytest tests/test_analytics.py -v   # run one module
pytest -k "best_effort"              # run tests matching a name
```

## Project layout

See `CLAUDE.md` for architecture decisions and `plan.md` for the full feature
scope and TDD build order.

## License

MIT
