import json

import discover
from conftest import reel


def tagged(who, code, views, tag, posted="2026-11-05"):
    return reel(who, code, views, posted, ownerFullName=who.title(), inputUrl=f"https://www.instagram.com/explore/tags/{tag}")


def test_clean_tags():
    assert discover.clean_tags("#Shayari, hindi poetry ,,#Urdu") == ["shayari", "hindipoetry", "urdu"]


def test_group_prefers_repeat_creators_then_median():
    items = [tagged("one", "a", 900000, "shayari"),
             tagged("steady", "b", 20000, "shayari"), tagged("steady", "c", 30000, "urdu", "2026-11-09"),
             tagged("small", "d", 2000, "shayari"), tagged("small", "e", 3000, "shayari"),
             {"error": "no_items"}, tagged("steady", "b", 20000, "shayari")]          # duplicate row
    g = discover.group(items)
    assert [c["handle"] for c in g] == ["steady", "small", "one"]
    s = g[0]
    assert s["reels"] == 2 and s["median"] == 25000 and s["best"] == 30000
    assert s["last_post"] == "2026-11-09" and s["hashtags"] == ["shayari", "urdu"]
    assert s["best_url"] == "https://www.instagram.com/p/c/"


def test_main_with_raw_writes_candidates(tmp_path, capsys):
    raw = tmp_path / "h.json"
    raw.write_text(json.dumps([tagged("steady", "b", 20000, "shayari"), tagged("steady", "c", 30000, "shayari")]))
    discover.main([str(tmp_path / "poetry"), "--raw", str(raw)])
    got = json.loads((tmp_path / "poetry" / "candidates.json").read_text())
    assert got[0]["handle"] == "steady"
    assert "@steady" in capsys.readouterr().out
