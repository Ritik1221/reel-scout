import datetime as dt, json

import pytest

import scout
from conftest import reel

TODAY = dt.date(2026, 11, 11)
S = dict(scout.DEFAULTS)


def write_cfg(d, **over):
    cfg = {"name": "poetry", "niches": {"main": ["@Alice", "https://www.instagram.com/bob/?hl=en"]}, **over}
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(json.dumps(cfg))
    return d


def test_norm_handle():
    assert scout.norm_handle(" @Foo.Bar ") == "foo.bar"
    assert scout.norm_handle("https://www.instagram.com/foo_1/?hl=en") == "foo_1"
    assert scout.norm_handle("instagram.com/foo/reels/") == "foo"


def test_load_config_normalises_and_fills_defaults(tmp_path):
    cfg = scout.load_config(write_cfg(tmp_path / "s", settings={"min_views": 100}))
    assert cfg["niches"] == {"main": ["alice", "bob"]}
    assert cfg["slots"] == {"main": 10}
    assert cfg["settings"]["min_views"] == 100 and cfg["settings"]["days"] == 14
    assert cfg["news_queries"] == []


def test_load_config_errors(tmp_path):
    with pytest.raises(SystemExit, match="No config"):
        scout.load_config(tmp_path / "missing")
    with pytest.raises(SystemExit, match="no creators"):
        scout.load_config(write_cfg(tmp_path / "e", niches={"main": ["  ", "@"]}))
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "config.json").write_text("{nope")
    with pytest.raises(SystemExit, match="not valid JSON"):
        scout.load_config(tmp_path / "bad")


def test_env_reads_dotfile_and_env_wins(isolated_home, monkeypatch):
    (isolated_home / ".env").write_text('APIFY_TOKEN="from-file"\nEXA_API_KEY=\n')
    assert scout.env("APIFY_TOKEN") == "from-file"
    assert scout.env("EXA_API_KEY") is None
    monkeypatch.setenv("APIFY_TOKEN", "from-env")
    assert scout.env("APIFY_TOKEN") == "from-env"


def test_remember_adds_and_drops_old():
    hist = {"alice": {"OLD": [10, "2026-07-01"], "KEEP": [20, "2026-10-01"]}}
    out = scout.remember(hist, [reel("Alice", "NEW", 30), reel("stranger", "X", 99)], {"alice": "main"}, TODAY)
    assert out == {"alice": {"KEEP": [20, "2026-10-01"], "NEW": [30, "2026-11-05"]}}


def test_rank_uses_stored_median_when_5_or_more():
    hist = {"alice": {f"h{i}": [1000, "2026-11-01"] for i in range(5)}}
    items = [reel("alice", "A", 9000), reel("alice", "B", 1200)]
    w = scout.rank(items, {"alice": "main"}, hist, {**S, "min_views": 0})
    assert [x["code"] for x in w] == ["A"] and w[0]["median"] == 1000 and w[0]["ratio"] == 9.0
    assert w[0]["niche"] == "main" and w[0]["audio"] == "https://cdn/A.mp4"


def test_rank_thresholds_and_junk_items():
    items = [reel("alice", c, v) for c, v in [("a", 100), ("b", 100), ("c", 100), ("d", 900), ("e", 800), ("f", 700), ("g", 600)]]
    items += [{"error": "not_found", "url": "x"}, reel("alice", "z", 0), reel("", "q", 5000)]
    w = scout.rank(items, {"alice": "main"}, {}, {**S, "min_ratio": 1.1, "min_views": 650, "per_creator": 2})
    assert [x["code"] for x in w] == ["d", "e"]          # median 600 from this run; d/e/f pass, g is 1.0x; capped at 2


def test_pick_new_respects_slots_and_seen():
    ws = [{"code": c, "niche": n} for c, n in [("a", "main"), ("b", "main"), ("c", "main"), ("d", "insp")]]
    got = scout.pick_new(ws, {"a"}, {"main": 1, "insp": 5})
    assert [w["code"] for w in got] == ["b", "d"]
