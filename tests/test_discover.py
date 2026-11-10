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


def test_print_says_views_are_of_tag_reels_not_usual(tmp_path, capsys):
    raw = tmp_path / "h.json"
    raw.write_text(json.dumps([tagged("steady", "b", 20000, "shayari")]))
    discover.main([str(tmp_path / "p"), "--raw", str(raw)])
    out = capsys.readouterr().out
    assert "not their usual views" in out and "median " not in out


def profile(user, followers, days_ago_list, views=1000, bio="poet", **extra):
    import datetime as dt
    posts = [{"shortCode": f"{user}{i}", "type": "Video", "likesCount": views,
              "timestamp": (dt.date(2026, 11, 11) - dt.timedelta(days=n)).isoformat() + "T10:00:00.000Z"}
             for i, n in enumerate(days_ago_list)]
    return {"username": user, "fullName": user.title(), "followersCount": followers, "postsCount": 99,
            "biography": bio, "private": False, "verified": False, "latestPosts": posts, **extra}


def test_profile_rows_show_activity_reach_and_repost_hints():
    import datetime as dt
    items = [profile("active", 52000, [1, 3, 5, 9], views=4000),
             profile("quiet", 900, [2, 30, 60]),
             profile("reposter", 300000, [0, 1, 2], bio="Credits to the owners. DM for removal"),
             {"username": "gone", "error": "not_found"}]
    rows = {r["handle"]: r for r in discover.profile_rows(items, dt.date(2026, 11, 11))}
    assert rows["active"]["followers"] == 52000 and rows["active"]["posts_14d"] == 4 and rows["active"]["usual_likes"] == 4000
    assert rows["active"]["active"] is True and rows["active"]["repost_hint"] is False
    assert rows["quiet"]["active"] is False
    assert rows["reposter"]["repost_hint"] is True
    assert rows["gone"]["error"] == "not_found"


def test_check_mode_with_raw_writes_profiles(tmp_path, capsys):
    raw = tmp_path / "p.json"
    raw.write_text(json.dumps([profile("active", 52000, [1, 3, 5])]))
    discover.main([str(tmp_path / "s"), "--check", "active", "--raw", str(raw)])
    got = json.loads((tmp_path / "s" / "profiles.json").read_text(encoding="utf-8"))
    assert got[0]["handle"] == "active"
    assert "@active" in capsys.readouterr().out
