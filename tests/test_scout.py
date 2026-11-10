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


def setup_scout(tmp_path, **over):
    d = write_cfg(tmp_path / "poetry", settings={"min_views": 0}, **over)
    hist = {"alice": {f"h{i}": [1000, "2026-11-01"] for i in range(5)}}
    (d / "topics.json").write_text(json.dumps({"scraped": "2026-10-01", "views": hist, "reels": [], "news": [], "pool": []}))
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps([reel("alice", "WIN", 8000, caption="दिल की बात"), reel("alice", "MEH", 900), reel("bob", "B1", 50)]))
    return d, raw


@pytest.fixture
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network call")
    monkeypatch.setattr(scout.requests, "post", boom)
    monkeypatch.setattr(scout.requests, "get", boom)


def test_run_with_raw_writes_pack_and_skips_missing_keys(tmp_path, no_network, capsys):
    d, raw = setup_scout(tmp_path)
    pack = scout.cmd_run(d, raw=raw, today=TODAY)
    out = capsys.readouterr().out
    assert "No ELEVENLABS_API_KEY" in out
    assert [r["code"] for r in pack["reels"]] == ["WIN"]
    assert pack["reels"][0]["used"] is False and "audio" not in pack["reels"][0]
    assert pack["rule"] == scout.RULE and pack["scraped"] == "2026-10-01"
    text = (d / "topics.json").read_text()
    assert "दिल की बात" in text                          # readable UTF-8
    assert {r["code"] for r in pack["pool"]} == {"WIN", "MEH", "B1"}
    again = scout.cmd_run(d, raw=raw, today=TODAY)       # same scrape twice: no duplicates
    assert [r["code"] for r in again["reels"]] == ["WIN"]
    assert "WIN" in again["views"]["alice"]


def test_run_not_due_does_not_scrape(tmp_path, monkeypatch):
    d, _ = setup_scout(tmp_path)
    t = json.loads((d / "topics.json").read_text()); t["scraped"] = "2026-11-05"
    (d / "topics.json").write_text(json.dumps(t))
    monkeypatch.setattr(scout, "apify_run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("scraped")))
    pack = scout.cmd_run(d, today=TODAY, do_news=False)
    assert pack["reels"] == [] and pack["scraped"] == "2026-11-05"


def test_run_due_scrapes_with_caps(tmp_path, monkeypatch):
    d, _ = setup_scout(tmp_path)
    seen = {}
    def fake(actor, payload, max_usd, usd_per_item):
        seen.update(actor=actor, payload=payload, max_usd=max_usd)
        return [reel("alice", "NEW", 5000)], 0.03
    monkeypatch.setattr(scout, "apify_run", fake)
    pack = scout.cmd_run(d, today=TODAY, do_transcribe=False, do_news=False)
    assert seen["actor"] == scout.REEL_ACTOR and seen["max_usd"] == 1.0
    assert seen["payload"]["username"] == ["alice", "bob"] and seen["payload"]["onlyPostsNewerThan"] == "14 days"
    assert pack["scraped"] == "2026-11-11" and (d / "topics.raw.json").exists()


def test_dry_run_spends_and_writes_nothing(tmp_path, no_network, capsys):
    d, _ = setup_scout(tmp_path, news_queries=["a", "b"])
    before = (d / "topics.json").read_text()
    assert scout.cmd_run(d, today=TODAY, dry_run=True) is None
    out = capsys.readouterr().out
    assert "Dry run" in out and "$" in out
    assert (d / "topics.json").read_text() == before


def test_apify_without_token_is_plain_message():
    with pytest.raises(SystemExit, match="APIFY_TOKEN is missing"):
        scout.apify_run(scout.REEL_ACTOR, {}, 1.0, scout.USD_PER_REEL)


def test_apify_rejected_token(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "bad")
    class R:
        status_code, text = 401, '{"error":{"type":"user-or-token-not-found"}}'
    monkeypatch.setattr(scout.requests, "post", lambda *a, **k: R())
    with pytest.raises(SystemExit, match="Apify refused the request \\(401\\)"):
        scout.apify_run(scout.REEL_ACTOR, {}, 1.0, scout.USD_PER_REEL)


def test_status_and_mark_used(tmp_path, no_network):
    d, raw = setup_scout(tmp_path)
    scout.cmd_run(d, raw=raw, today=TODAY)
    st = scout.cmd_status(d, today=TODAY)
    assert st["unused_reels"] == 1 and st["next_scrape"] == "due now"
    missing = scout.cmd_mark_used(d, ["https://www.instagram.com/p/WIN/", "NOPE"])
    assert missing == ["NOPE"]
    assert scout.cmd_status(d, today=TODAY)["unused_reels"] == 0


def test_scripts_always_pass_utf8():
    """Windows defaults to cp1252: every file read/write must name utf-8 (Hindi captions, config 'about')."""
    import pathlib, re
    for f in pathlib.Path(scout.__file__).parent.glob("*.py"):
        for m in re.finditer(r"\.(read_text|write_text)\(([^()]*(\([^()]*\))?[^()]*)\)", f.read_text(encoding="utf-8")):
            assert 'encoding="utf-8"' in m.group(2), f"{f.name}: {m.group(0)[:60]}"


def test_dry_run_survives_a_cp1252_console(tmp_path):
    import os, subprocess, sys
    d, _ = setup_scout(tmp_path, news_queries=["a"])
    envs = {**os.environ, "PYTHONIOENCODING": "cp1252", "REEL_SCOUT_HOME": str(tmp_path / "home"), "EXA_API_KEY": "x"}
    r = subprocess.run([sys.executable, scout.__file__, "run", str(d), "--dry-run"], capture_output=True, env=envs)
    assert r.returncode == 0, r.stderr.decode(errors="replace")[-300:]


def test_same_reel_twice_in_one_scrape_is_saved_once(tmp_path, no_network):
    d, raw = setup_scout(tmp_path)
    raw.write_text(json.dumps([reel("alice", "WIN", 8000), reel("alice", "WIN", 8000)]))
    pack = scout.cmd_run(d, raw=raw, today=TODAY)
    assert [r["code"] for r in pack["reels"]] == ["WIN"]


def test_apify_token_goes_in_header_not_url(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "secret-tok")
    seen = {}
    class R:
        status_code, text = 401, "nope"
    def post(url, **k):
        seen.update(url=url, **k)
        return R()
    monkeypatch.setattr(scout.requests, "post", post)
    with pytest.raises(SystemExit):
        scout.apify_run(scout.REEL_ACTOR, {}, 1.0, scout.USD_PER_REEL)
    assert "secret-tok" not in seen["url"] + json.dumps(seen.get("params", {}))
    assert seen["headers"]["Authorization"] == "Bearer secret-tok"


def test_apify_network_error_is_plain_and_hides_token(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "secret-tok")
    def post(*a, **k):
        raise scout.requests.ConnectionError("https://api.apify.com/v2/acts/x/runs?token=secret-tok refused")
    monkeypatch.setattr(scout.requests, "post", post)
    with pytest.raises(SystemExit) as e:
        scout.apify_run(scout.REEL_ACTOR, {}, 1.0, scout.USD_PER_REEL)
    assert "Couldn't reach Apify" in str(e.value) and "secret-tok" not in str(e.value)


def test_check_keys_never_prints_keys(monkeypatch, capsys):
    monkeypatch.setenv("APIFY_TOKEN", "secret-tok")
    monkeypatch.setenv("EXA_API_KEY", "exa-secret")
    class R:
        status_code = 200
        def json(self):
            return {"data": {"username": "poet", "plan": {"id": "FREE"}, "email": "a@b.c"}}
    monkeypatch.setattr(scout.requests, "get", lambda *a, **k: R())
    got = scout.cmd_check_keys()
    out = capsys.readouterr().out
    assert got == {"APIFY_TOKEN": "ok (poet, FREE plan)", "ELEVENLABS_API_KEY": "missing", "EXA_API_KEY": "set (checked on the first news search)"}
    assert "secret" not in out and "a@b.c" not in out


def test_dry_run_prices_transcripts(tmp_path, no_network, monkeypatch, capsys):
    d, _ = setup_scout(tmp_path, slots={"main": 4})
    monkeypatch.setenv("ELEVENLABS_API_KEY", "x")
    scout.cmd_run(d, today=TODAY, dry_run=True)
    out = capsys.readouterr().out
    assert "transcripts: up to 4 reels" in out and "$0.04" in out


def test_run_warns_about_quiet_creators(tmp_path, no_network, capsys):
    d, raw = setup_scout(tmp_path)                      # bob has 1 reel, no stored history
    scout.cmd_run(d, raw=raw, today=TODAY)
    assert "@bob" in capsys.readouterr().out.split("Too few reels")[1]


def test_pool_has_median_and_skips_zero_views(tmp_path, no_network):
    d, raw = setup_scout(tmp_path)
    raw.write_text(json.dumps([reel("alice", "WIN", 8000), reel("alice", "ZERO", 0)]))
    pack = scout.cmd_run(d, raw=raw, today=TODAY)
    assert {r["code"] for r in pack["pool"]} == {"WIN"}
    assert pack["pool"][0]["median"] == 1000


def test_check_keys_checks_elevenlabs(monkeypatch, capsys):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-secret")
    class R:
        status_code = 401
        def json(self):
            return {}
    monkeypatch.setattr(scout.requests, "get", lambda *a, **k: R())
    got = scout.cmd_check_keys()
    assert got["ELEVENLABS_API_KEY"] == "refused or unreachable"
    assert got["EXA_API_KEY"] == "missing"
