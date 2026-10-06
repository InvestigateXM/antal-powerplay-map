# Antal Powerplay Map: plan

A website with a 3D galaxy map of the Elite Dangerous systems held, contested and targeted by
Pranav Antal in Powerplay 2.0, built on the Canonn ED3D map engine.

Status: 2026-10-06. The first prototype (step 1 to 3 below, Antal systems only) is built.

## 1. What the Canonn map gives us

Source: https://github.com/canonn-science/CanonnED3D-Map (commit `1425548`, May 2026). MIT licensed,
so we can copy and change it as long as we keep their copyright notice.

- **A static website with no build step.** Everything lives in `Source/`. Each map is one HTML
  page plus one `data/MapData-*.js` file. A GitHub Action force-pushes `Source/` to `gh-pages`,
  which serves map.canonn.tech.
- **The engine is `js/ed3dmap.js` plus `js/components/*.class.js`**: galaxy backdrop, grid, systems,
  routes, heatmap, and a HUD with category filters, system search and journal-file upload.
  It uses jQuery 2.1 and three.js r75 (from 2016) loaded from cdnjs.
- **Data goes in through one call**, `Ed3d.init({ container, json, ... })`, where `json` has:
  - `categories`: groups of `{ id: { name, color } }`, which become the HUD filters and colours
  - `systems`: `{ name, coords: {x,y,z}, cat: [ids], infos: "<html>" }`
  - optional `routes`, `heatmap` and `position`

  The repo's `JSON_SCHEMA.md` documents this. So an Antal map is "build that JSON, call init".
- **`MapData-*.js` files fetch their own data in the browser**, from the Canonn API, Canonn cloud
  functions, EliteBGS or Spansh dumps (`MapData-multifaction.js` reads
  `downloads.spansh.co.uk/factions.json.gz`).
- **A warning:** the faction (BGS) pages and several others are switched off at the moment with
  "This page is temporarily out of order, external API unavailable". Pages that call a third-party
  API live from the browser break when that API goes away. We should not repeat that.
- **No Powerplay map exists in the repo.** We are adding something new, not reskinning a page.

## 2. Approach

Keep the Canonn engine almost unchanged and add our own page and data around it.

```
antal-powerplay-map/
  site/                       # what gets deployed (like Canonn's Source/)
    index.html                # the Antal map page
    js/ed3dmap.js, js/components/   # copied from Canonn, MIT notice kept
    css/, vendor/, textures/, img/  # only the assets the engine needs
    js/antal-map.js           # our code: load the data file and call Ed3d.init
    data/antal-systems.json   # generated Antal systems in ED3D format (committed by the Actions)
  data/populated-systems.jsonl  # every populated system, the sync state
  tools/spansh_sync.py        # seed / update / build from the Spansh dumps
  .github/workflows/
    seed.yml                  # by hand: full seed from the populated dump
    update.yml                # every 6 hours: merge the 1-day dump
    deploy.yml                # publish site/ to GitHub Pages
  LICENSE                     # MIT, with Canonn's copyright and ours
```

Decisions:

1. **Fetch data on a schedule, not in the visitor's browser.** A GitHub Action fetches the data,
   writes one static `antal-systems.json` and commits it. The page only reads that file. That avoids CORS
   problems, avoids hammering community APIs, keeps the map working when a source is down (it shows
   the last snapshot plus its date), and gives us history in git for free.
2. **Copy only what we need.** Canonn's `Source/` is 16 MB, mostly other maps' data and images.
   We take the engine, its CSS, vendor libs and textures (about 2 MB) and drop the rest, including
   Canonn's Google Analytics tag, branding and nav menu.
3. **Leave three.js r75 alone at first.** Upgrading it is a rewrite of the engine. We revisit only
   if it gets in the way (mobile, performance, something we can't draw).
4. **Host on GitHub Pages** from the new repo, the same way Canonn does. A custom domain can be
   added later.

## 3. Data

**Decided for the prototype (2026-10-06):** seed once from Spansh's `galaxy_populated.json.gz`,
keeping every system with population >= 1 (all are eligible for Powerplay). Every 6 hours, merge
`galaxy_1day.json.gz` (systems changed in the last day) and drop systems whose population is now 0.
The full populated set is kept in `data/populated-systems.jsonl` so later features (neighbouring
powers, acquisition targets) don't need a new pipeline. The map itself shows only systems where
`controllingPower` is Pranav Antal, whatever their state. Dump schema:
https://docs.spansh.co.uk/galaxy.schema.json

What we want per system: name, coordinates, controlling power, Powerplay state (Stronghold,
Fortified, Exploited, or contested/unoccupied with Antal acquisition progress), and where available
reinforcement and undermining progress, plus when the data was last updated.

Candidate sources (to confirm in step 1 of the build; this sandbox could not reach them, so the
details below are from memory, not checked):

| Source | What it offers | Notes |
|---|---|---|
| Spansh system search API (`spansh.co.uk/api/systems/search`) | Filter on controlling power and power state, returns coords and Powerplay fields | Best first choice: one query for all Antal systems |
| Spansh dumps (`downloads.spansh.co.uk/galaxy_populated.json.gz`) | Every populated system with Powerplay fields | Large download; good fallback, fine inside an Action |
| EDDN live feed | FSDJump/Location events carry ControllingPower, PowerplayState and progress values | Freshest data; needs a small always-on listener, so a later phase |
| Inara | Good Powerplay pages | No public bulk API; link to it from the info panel instead |
| EDSM | Older Powerplay data | Not reliable for Powerplay 2.0 |

Data quality to handle: snapshots are only as fresh as the last commander who visited a system,
so every system shows its "last updated" time and old entries can be dimmed.

## 4. Map features

First version:
- Systems coloured by Antal state: Stronghold, Fortified, Exploited, and contested or acquisition
  targets. Each state is a HUD filter.
- HQ (Polevnic) marked and used as the starting camera position.
- Info panel per system: state, progress, last updated, links to Inara and Spansh.
- System search (already in the engine).
- A "data as of" line and an Antal-themed header instead of Canonn's nav.

Later, roughly in order of value:
- Acquisition range bubbles (Fortified and Stronghold systems project a range in which new systems
  can be acquired) shown as spheres or a heatmap.
- Neighbouring powers' systems, greyed out, to show borders and contested space.
- "Needs attention" filter: systems being undermined, low reinforcement, about to be lost.
- Squadron priorities or targets overlaid from a list we maintain (a JSON file or a sheet).
- Changes since last week, using the git history of `antal-systems.json`.
- Live updates from EDDN.

## 5. Build steps

1. **Set up the repo**: copy the engine from Canonn with its MIT notice, strip the extras, add
   `index.html` with hand-written sample Antal data, enable GitHub Pages. Result: a live map with
   fake data.
2. **Confirm the data source**: call the Spansh API for Antal systems, check which Powerplay fields
   come back and how fresh they are. Pick Spansh search or the dump.
3. **Write the fetch script and the scheduled Action**: produce `site/data/antal-systems.json` in the
   engine's format. Run it a few times a day.
4. **Antal features**: state colours and filters, HQ, info panel, "data as of", theming.
5. **Ranges and neighbours**: acquisition bubbles and other powers' systems.
6. **Polish**: mobile layout check, performance with a few thousand systems, README for contributors.

## 6. Open questions

- Which data matters most to the people using it: who holds what, or what needs reinforcing
  and undermining right now?
- Should other powers' systems appear on the map, or only Antal's?
- Is there an existing list of squadron targets or priorities (for example a Google Sheet) that
  the map should show?
- Custom domain, or the default `investigatexm.github.io/antal-powerplay-map`?
