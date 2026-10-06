#!/usr/bin/env python3
"""Keep a local copy of every populated system from the Spansh galaxy dumps,
and build the Pranav Antal map data from it.

    python tools/spansh_sync.py seed      # full rebuild from galaxy_populated.json.gz
    python tools/spansh_sync.py update    # merge galaxy_1day.json.gz into the state
    python tools/spansh_sync.py build     # only regenerate site/data/antal-systems.json

`seed` and `update` accept --url to override the dump URL, or --file to read a
local (optionally gzipped) dump instead of downloading. Only the standard
library is used, so the GitHub Action needs no installs.

Dump schema: https://docs.spansh.co.uk/galaxy.schema.json
"""

import argparse
import gzip
import html
import io
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(ROOT, "data", "populated-systems.jsonl")
META_PATH = os.path.join(ROOT, "data", "sync-meta.json")
SITE_DATA_PATH = os.path.join(ROOT, "site", "data", "antal-systems.json")

SEED_URL = "https://downloads.spansh.co.uk/galaxy_populated.json.gz"
UPDATE_URL = "https://downloads.spansh.co.uk/galaxy_1day.json.gz"

POWER = "Pranav Antal"
HQ_SYSTEM = "Polevnic"

# Fields copied from each dump system into the state file.
KEEP_FIELDS = (
    "id64",
    "name",
    "coords",
    "population",
    "allegiance",
    "controllingPower",
    "powerState",
    "powers",
    "powerStateControlProgress",
    "powerStateReinforcement",
    "powerStateUndermining",
    "date",
)

# HUD categories for the map, keyed by Powerplay state.
STATE_CATEGORIES = {
    "Stronghold": ("1", "ff4f3d"),
    "Fortified": ("2", "ffb52e"),
    "Exploited": ("3", "ffee8c"),
}
OTHER_CATEGORY = ("9", "9aa4b2")


# --------------------------------------------------------------------------
# Reading dumps
# --------------------------------------------------------------------------

def open_dump(url=None, path=None):
    """Return a text stream over a (possibly gzipped) dump."""
    if path:
        raw = open(path, "rb")
    else:
        req = urllib.request.Request(url, headers={"User-Agent": "antal-powerplay-map (github.com/InvestigateXM/antal-powerplay-map)"})
        raw = io.BufferedReader(urllib.request.urlopen(req, timeout=120), 1 << 20)
    gzipped = raw.peek(2)[:2] == b"\x1f\x8b"
    stream = gzip.GzipFile(fileobj=raw) if gzipped else raw
    return io.TextIOWrapper(stream, encoding="utf-8")


def iter_systems(text_stream, chunk_size=1 << 20):
    """Yield each object of a top-level JSON array without loading it whole.

    Spansh writes one system per line, but this does not rely on it: it
    decodes objects one at a time from a sliding buffer.
    """
    decoder = json.JSONDecoder()
    buf = ""
    pos = 0
    eof = False

    def fill():
        nonlocal buf, pos, eof
        chunk = text_stream.read(chunk_size)
        if not chunk:
            eof = True
        buf = buf[pos:] + chunk
        pos = 0

    fill()
    # Skip to the opening bracket.
    while True:
        while pos < len(buf) and buf[pos] in " \t\r\n":
            pos += 1
        if pos < len(buf):
            break
        if eof:
            return
        fill()
    if buf[pos] != "[":
        raise ValueError("dump does not start with a JSON array")
    pos += 1

    while True:
        # Skip whitespace and commas between objects.
        while True:
            while pos < len(buf) and buf[pos] in " \t\r\n,":
                pos += 1
            if pos < len(buf) or eof:
                break
            fill()
        if pos >= len(buf):
            raise ValueError("dump ended before the closing bracket")
        if buf[pos] == "]":
            return
        try:
            obj, end = decoder.raw_decode(buf, pos)
        except json.JSONDecodeError:
            if eof:
                raise
            fill()
            continue
        if end == len(buf) and not eof:
            # A number or similar could be cut off at the buffer edge; re-read.
            fill()
            continue
        pos = end
        yield obj


# --------------------------------------------------------------------------
# State file
# --------------------------------------------------------------------------

def slim(system):
    rec = {k: system[k] for k in KEEP_FIELDS if system.get(k) is not None}
    c = rec.get("coords")
    if c:
        rec["coords"] = {a: round(float(c[a]), 5) for a in ("x", "y", "z")}
    return rec


def load_state():
    state = {}
    if not os.path.exists(STATE_PATH):
        return state
    with open(STATE_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rec = json.loads(line)
                state[rec["id64"]] = rec
    return state


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for id64 in sorted(state):
            f.write(json.dumps(state[id64], ensure_ascii=False, separators=(",", ":"), sort_keys=True))
            f.write("\n")
    os.replace(tmp, STATE_PATH)


def load_meta():
    if os.path.exists(META_PATH):
        with open(META_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_meta(meta):
    with open(META_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, indent=2, sort_keys=True)
        f.write("\n")


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_date(value):
    """Spansh dates look like '2024-11-05 12:34:56+00'. Return a sortable datetime."""
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    v = value.strip().replace("T", " ").replace("Z", "+00:00")
    if len(v) >= 3 and v[-3] in "+-" and ":" not in v[-3:]:
        v += ":00"
    try:
        d = datetime.fromisoformat(v)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def cmd_seed(args):
    source = args.file or args.url or SEED_URL
    state = {}
    seen = 0
    for system in iter_systems(open_dump(url=args.url or SEED_URL, path=args.file)):
        seen += 1
        if (system.get("population") or 0) >= 1 and system.get("coords"):
            state[system["id64"]] = slim(system)
        if seen % 10000 == 0:
            print(f"  read {seen} systems, kept {len(state)}", flush=True)
    print(f"seed: read {seen} systems, kept {len(state)} with population >= 1")
    if not state:
        sys.exit("seed: no populated systems found, refusing to write an empty state")
    save_state(state)
    meta = load_meta()
    meta["seed"] = {"at": now_iso(), "source": source, "read": seen, "kept": len(state)}
    save_meta(meta)
    build(state, meta)


def merge(state, systems):
    """Apply changed systems to the state. Returns counts of what happened."""
    counts = {"read": 0, "added": 0, "updated": 0, "removed": 0, "stale": 0, "skipped": 0}
    for system in systems:
        counts["read"] += 1
        id64 = system.get("id64")
        if id64 is None:
            counts["skipped"] += 1
            continue
        current = state.get(id64)
        if current and parse_date(system.get("date")) < parse_date(current.get("date")):
            counts["stale"] += 1
            continue
        population = system.get("population")
        if population is None:
            # Population missing from the dump entry: keep what we know, if anything.
            if not current:
                counts["skipped"] += 1
                continue
            population = current.get("population", 0)
        if population < 1:
            if current:
                del state[id64]
                counts["removed"] += 1
            else:
                counts["skipped"] += 1
            continue
        rec = slim(system)
        rec["population"] = population
        if "coords" not in rec:
            if not current:
                counts["skipped"] += 1
                continue
            rec["coords"] = current["coords"]
        state[id64] = rec
        counts["updated" if current else "added"] += 1
    return counts


def cmd_update(args):
    source = args.file or args.url or UPDATE_URL
    if not os.path.exists(STATE_PATH):
        sys.exit("update: no state yet, run the seed first")
    state = load_state()
    counts = merge(state, iter_systems(open_dump(url=args.url or UPDATE_URL, path=args.file)))
    print("update: " + ", ".join(f"{k} {v}" for k, v in counts.items()) + f"; state now {len(state)}")
    save_state(state)
    meta = load_meta()
    meta["lastUpdate"] = dict(counts, at=now_iso(), source=source, total=len(state))
    save_meta(meta)
    build(state, meta)


def cmd_build(args):
    build(load_state(), load_meta())


# --------------------------------------------------------------------------
# Map data
# --------------------------------------------------------------------------

def fmt_number(value):
    return f"{value:,}" if isinstance(value, int) else f"{value:,.0f}"


def info_html(rec):
    name = rec["name"]
    rows = [("State", rec.get("powerState") or "Unknown"), ("Population", fmt_number(rec.get("population", 0)))]
    if rec.get("powerStateReinforcement") is not None:
        rows.append(("Reinforcement", fmt_number(rec["powerStateReinforcement"])))
    if rec.get("powerStateUndermining") is not None:
        rows.append(("Undermining", fmt_number(rec["powerStateUndermining"])))
    if rec.get("powerStateControlProgress") is not None:
        rows.append(("Control progress", f'{rec["powerStateControlProgress"] * 100:.1f}%'))
    others = [p for p in rec.get("powers", []) if p != POWER]
    if others:
        rows.append(("Other powers present", ", ".join(others)))
    rows.append(("Last updated", (rec.get("date") or "unknown")[:16]))
    body = "".join(f"<b>{html.escape(k)}:</b> {html.escape(str(v))}<br>" for k, v in rows)
    q = urllib.parse.quote(name)
    links = (
        f'<a href="https://inara.cz/elite/starsystem/?search={q}" target="_blank" rel="noopener">Inara</a> · '
        f'<a href="https://spansh.co.uk/system/{rec["id64"]}" target="_blank" rel="noopener">Spansh</a>'
    )
    return body + links


def build(state, meta):
    categories = {POWER: {}}
    used = set()
    systems = []
    latest = None
    hq = None
    for rec in sorted(state.values(), key=lambda r: r["name"].lower()):
        if rec.get("controllingPower") != POWER:
            continue
        cat_id, _ = STATE_CATEGORIES.get(rec.get("powerState"), OTHER_CATEGORY)
        used.add(cat_id)
        systems.append({"name": rec["name"], "coords": rec["coords"], "cat": [cat_id], "infos": info_html(rec)})
        d = rec.get("date")
        if d and (latest is None or parse_date(d) > parse_date(latest)):
            latest = d
        if rec["name"].lower() == HQ_SYSTEM.lower():
            hq = rec["coords"]

    for state_name, (cat_id, color) in STATE_CATEGORIES.items():
        if cat_id in used:
            categories[POWER][cat_id] = {"name": state_name, "color": color}
    if OTHER_CATEGORY[0] in used:
        categories[POWER][OTHER_CATEGORY[0]] = {"name": "Other / unknown state", "color": OTHER_CATEGORY[1]}

    if hq is None and systems:
        n = len(systems)
        hq = {a: round(sum(s["coords"][a] for s in systems) / n, 2) for a in ("x", "y", "z")}

    out = {
        "power": POWER,
        "generated": now_iso(),
        "dataAsOf": latest,
        "sync": meta,
        "counts": {c["name"]: sum(1 for s in systems if s["cat"][0] == cid) for cid, c in categories[POWER].items()},
        "categories": categories,
        "systems": systems,
    }
    if hq:
        out["position"] = hq
    os.makedirs(os.path.dirname(SITE_DATA_PATH), exist_ok=True)
    tmp = SITE_DATA_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, SITE_DATA_PATH)
    print(f"build: {len(systems)} {POWER} systems written to {os.path.relpath(SITE_DATA_PATH, ROOT)}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("seed", "update"):
        s = sub.add_parser(name)
        s.add_argument("--url", help="dump URL to download")
        s.add_argument("--file", help="local dump file instead of downloading")
    sub.add_parser("build")
    args = p.parse_args(argv)
    {"seed": cmd_seed, "update": cmd_update, "build": cmd_build}[args.cmd](args)


if __name__ == "__main__":
    main()
