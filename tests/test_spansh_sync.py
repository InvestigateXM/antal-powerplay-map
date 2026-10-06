import gzip
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import spansh_sync as sync  # noqa: E402


def system(id64, name, population=None, power=None, state=None, date="2026-10-01 12:00:00+00", **extra):
    s = {"id64": id64, "name": name, "coords": {"x": id64, "y": 0.123456789, "z": -id64}, "date": date, "bodies": []}
    if population is not None:
        s["population"] = population
    if power:
        s["controllingPower"] = power
        s["powers"] = [power]
    if state:
        s["powerState"] = state
    s.update(extra)
    return s


def spansh_dump(systems):
    """Format like Spansh: an array with one system per line."""
    return "[\n" + ",\n".join(json.dumps(s) for s in systems) + "\n]\n"


class IterSystemsTest(unittest.TestCase):
    def test_one_per_line(self):
        items = [system(i, f"S{i}", 5) for i in range(50)]
        got = list(sync.iter_systems(io.StringIO(spansh_dump(items)), chunk_size=64))
        self.assertEqual(got, items)

    def test_pretty_printed_and_tiny_chunks(self):
        items = [system(i, f"S{i}", 5, bodies=[{"name": "x" * 300}]) for i in range(5)]
        text = json.dumps(items, indent=2)
        for chunk in (1, 7, 1000):
            self.assertEqual(list(sync.iter_systems(io.StringIO(text), chunk_size=chunk)), items)

    def test_empty_array(self):
        self.assertEqual(list(sync.iter_systems(io.StringIO("[]"))), [])

    def test_truncated_dump_raises(self):
        with self.assertRaises(ValueError):
            list(sync.iter_systems(io.StringIO('[{"id64": 1}, {"id64"')))

    def test_reads_gzip_file(self):
        items = [system(1, "A", 10)]
        with tempfile.NamedTemporaryFile(suffix=".gz", delete=False) as f:
            f.write(gzip.compress(spansh_dump(items).encode()))
        try:
            with sync.open_dump(path=f.name) as stream:
                self.assertEqual(list(sync.iter_systems(stream)), items)
        finally:
            os.unlink(f.name)


class MergeTest(unittest.TestCase):
    def setUp(self):
        self.state = {
            1: sync.slim(system(1, "Kept", 100, "Pranav Antal", "Fortified")),
            2: sync.slim(system(2, "Depopulated", 100, "Pranav Antal", "Exploited")),
            3: sync.slim(system(3, "Newer", 100, "Pranav Antal", "Stronghold", date="2026-10-05 00:00:00+00")),
        }

    def test_rules(self):
        delta = [
            system(1, "Kept", 100, "Yuri Grom", "Exploited"),      # power changed
            system(2, "Depopulated", 0),                          # population 0 -> removed
            system(3, "Newer", 100, None, None, date="2026-10-01 00:00:00+00"),  # older than state -> ignored
            system(4, "New colony", 3, "Pranav Antal", "Exploited"),  # added
            system(5, "Empty", 0),                                # never stored
            system(6, "No pop field"),                            # unknown and not stored -> skipped
        ]
        no_pop = system(1, "Kept")  # applied after, keeps population
        no_pop["date"] = "2026-10-02 00:00:00+00"
        counts = sync.merge(self.state, delta + [no_pop])
        self.assertEqual(counts, {"read": 7, "added": 1, "updated": 2, "removed": 1, "stale": 1, "skipped": 2})
        self.assertEqual(sorted(self.state), [1, 3, 4])
        self.assertEqual(self.state[1]["population"], 100)
        self.assertEqual(self.state[3]["powerState"], "Stronghold")
        self.assertEqual(self.state[1]["coords"]["y"], 0.12346)


class EndToEndTest(unittest.TestCase):
    def test_seed_update_build(self):
        tmp = tempfile.mkdtemp()
        paths = {
            "STATE_PATH": os.path.join(tmp, "data", "populated-systems.jsonl"),
            "META_PATH": os.path.join(tmp, "data", "sync-meta.json"),
            "SITE_DATA_PATH": os.path.join(tmp, "site", "data", "antal-systems.json"),
        }
        os.makedirs(os.path.join(tmp, "data"))
        seed = os.path.join(tmp, "seed.json.gz")
        delta = os.path.join(tmp, "delta.json.gz")
        with gzip.open(seed, "wt") as f:
            f.write(spansh_dump([
                system(10, "Polevnic", 5000, "Pranav Antal", "Stronghold"),
                system(11, "Fort <b>", 50, "Pranav Antal", "Fortified", powerStateReinforcement=1200),
                system(12, "Grom place", 50, "Yuri Grom", "Exploited"),
                system(13, "Nobody", 0),
            ]))
        with gzip.open(delta, "wt") as f:
            f.write(spansh_dump([
                system(12, "Grom place", 50, "Pranav Antal", "Exploited", date="2026-10-06 00:00:00+00"),
                system(14, "Lost", 0),
            ]))
        with mock.patch.multiple(sync, **paths):
            sync.main(["seed", "--file", seed])
            sync.main(["update", "--file", delta])
            with open(paths["SITE_DATA_PATH"]) as f:
                out = json.load(f)
            with open(paths["STATE_PATH"]) as f:
                self.assertEqual(len(f.readlines()), 3)
        self.assertEqual([s["name"] for s in out["systems"]], ["Fort <b>", "Grom place", "Polevnic"])
        self.assertEqual(out["counts"], {"Stronghold": 1, "Fortified": 1, "Exploited": 1})
        self.assertEqual(out["position"], {"x": 10.0, "y": 0.12346, "z": -10.0})
        self.assertEqual(out["dataAsOf"], "2026-10-06 00:00:00+00")
        fort = out["systems"][0]["infos"]
        self.assertIn("search=Fort%20%3Cb%3E", fort)
        self.assertIn("Reinforcement:</b> 1,200", fort)


if __name__ == "__main__":
    unittest.main()
