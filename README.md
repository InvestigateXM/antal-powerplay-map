# Antal Powerplay Map

A 3D galaxy map of every system controlled by Pranav Antal in Elite Dangerous Powerplay,
built on the [Canonn ED3D map](https://github.com/canonn-science/CanonnED3D-Map) engine (MIT).
System data comes from the [Spansh galaxy dumps](https://spansh.co.uk/dumps).

See [PLAN.md](PLAN.md) for where this is going.

## How it works

```
Spansh dumps ──> tools/spansh_sync.py ──> data/populated-systems.jsonl   (every system with population >= 1)
                                     └──> site/data/antal-systems.json   (Antal systems, in ED3D map format)
                                                    │
                                     site/index.html + Canonn engine  ──> GitHub Pages
```

- **Seed** (`.github/workflows/seed.yml`, run by hand): streams `galaxy_populated.json.gz` and keeps
  every system with population of at least 1.
- **Update** (`.github/workflows/update.yml`, every 6 hours): streams `galaxy_1day.json.gz` (systems
  changed in the last day) and merges it in. Systems whose population is now 0 are removed, and an
  entry older than what we already have is ignored.
- **Deploy** (`.github/workflows/deploy.yml`): publishes `site/` to GitHub Pages after a data change
  or a push to `site/`.

The map shows Stronghold, Fortified and Exploited systems as separate filters.

## Running locally

```sh
python tools/spansh_sync.py seed --file galaxy_populated.json.gz   # or without --file to download
python tools/spansh_sync.py update --file galaxy_1day.json.gz
cd site && python -m http.server 8000                               # open http://localhost:8000
python -m unittest discover -s tests
```

Only the Python standard library is used.

## Credits

Map engine by [Canonn Research](https://canonn.science), MIT licensed. Data by
[Spansh](https://spansh.co.uk). Elite Dangerous is a trademark of Frontier Developments plc.
