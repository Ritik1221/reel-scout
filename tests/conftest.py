import pathlib, sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills" / "reel-scout" / "scripts"))


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Every test gets an empty ~/reel-scout and no real keys."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("REEL_SCOUT_HOME", str(home))
    for k in ("APIFY_TOKEN", "ELEVENLABS_API_KEY", "EXA_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    return home


def reel(who, code, views, posted="2026-11-05", caption="cap", **extra):
    """A fake Apify reel item."""
    return {"ownerUsername": who, "shortCode": code, "videoPlayCount": views, "timestamp": f"{posted}T10:00:00.000Z",
            "url": f"https://www.instagram.com/p/{code}/", "caption": caption, "likesCount": 1, "commentsCount": 1,
            "videoDuration": 30.0, "audioUrl": f"https://cdn/{code}.mp4", **extra}
