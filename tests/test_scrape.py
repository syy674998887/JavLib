from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest
import requests

from javlib import scrape as scrape_module


class MovieFetcher:
    def __init__(self):
        self.begin_calls = 0

    def begin_movie(self):
        self.begin_calls += 1

    def post(self, *args, **kwargs):
        return 0, None


def metadata(code):
    return {
        "source": "javbus",
        "code": code,
        "dvdid": code,
        "title": "Title",
        "genres": [],
        "actors": [],
        "samples": [],
        "cover": "https://img.test/fanart.jpg",
    }


def test_movie_nfo_is_committed_only_after_full_workflow(monkeypatch, tmp_path):
    folder = tmp_path / "TEST-001"
    folder.mkdir()
    video = folder / "TEST-001.mp4"
    video.write_bytes(b"")
    fetcher = MovieFetcher()
    args = SimpleNamespace(force=False)

    monkeypatch.setattr(
        scrape_module, "fetch_javbus", lambda current_fetcher, code: metadata(code)
    )
    monkeypatch.setattr(scrape_module, "fetch_javdb", lambda current_fetcher, code: None)
    monkeypatch.setattr(
        scrape_module,
        "download_with_alt",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("image failure")),
    )

    with pytest.raises(RuntimeError, match="image failure"):
        scrape_module.scrape_one(folder, fetcher, args)

    assert not (folder / "movie.nfo").exists()
    assert not video.with_suffix(".nfo").exists()

    monkeypatch.setattr(scrape_module, "download_with_alt", lambda *args, **kwargs: False)
    status, detail = scrape_module.scrape_one(folder, fetcher, args)

    assert status == "OK"
    assert detail == "TEST-001 [javbus] nfo×2"
    assert (folder / "movie.nfo").exists()
    assert video.with_suffix(".nfo").exists()


def test_movie_video_cannot_commit_completion_marker_early(monkeypatch, tmp_path):
    folder = tmp_path / "TEST-001"
    folder.mkdir()
    (folder / "movie.mp4").write_bytes(b"")
    later_video = folder / "zzz.mp4"
    later_video.write_bytes(b"")

    monkeypatch.setattr(
        scrape_module, "fetch_javbus", lambda current_fetcher, code: metadata(code)
    )
    monkeypatch.setattr(scrape_module, "fetch_javdb", lambda current_fetcher, code: None)
    monkeypatch.setattr(scrape_module, "download_with_alt", lambda *args, **kwargs: False)
    real_atomic_write = scrape_module.atomic_write_bytes

    def fail_on_later_sidecar(path, payload):
        if path == later_video.with_suffix(".nfo"):
            raise OSError("simulated sidecar failure")
        real_atomic_write(path, payload)

    monkeypatch.setattr(scrape_module, "atomic_write_bytes", fail_on_later_sidecar)

    with pytest.raises(OSError, match="simulated sidecar failure"):
        scrape_module.scrape_one(
            folder, MovieFetcher(), SimpleNamespace(force=False)
        )

    assert not (folder / "movie.nfo").exists()
    assert not later_video.with_suffix(".nfo").exists()


def test_vr_final_artwork_uses_atomic_writes(monkeypatch, tmp_path):
    folder = tmp_path / "IPVR-256"
    folder.mkdir()
    data = metadata("IPVR-256")
    data["samples"] = ["https://img.test/1.jpg", "https://img.test/2.jpg"]

    monkeypatch.setattr(scrape_module, "fetch_javbus", lambda *args: data)
    monkeypatch.setattr(scrape_module, "fetch_javdb", lambda *args: None)

    def fake_download(fetcher, primary, alternate, destination):
        if destination.name == "fanart.jpg":
            return False
        destination.write_bytes(b"sample image")
        return True

    monkeypatch.setattr(scrape_module, "download_with_alt", fake_download)
    monkeypatch.setattr(
        scrape_module,
        "pick_sample_poster",
        lambda fetcher, candidates, *args: (candidates[0], "selected"),
    )
    real_atomic_write = scrape_module.atomic_write_bytes
    atomic_destinations = []

    def record_atomic_write(path, payload):
        atomic_destinations.append(path)
        real_atomic_write(path, payload)

    monkeypatch.setattr(scrape_module, "atomic_write_bytes", record_atomic_write)

    status, _ = scrape_module.scrape_one(
        folder, MovieFetcher(), SimpleNamespace(force=False)
    )

    assert status == "OK"
    assert folder / "poster.jpg" in atomic_destinations
    assert folder / "Samples" / "sample1.jpg" in atomic_destinations


def test_existing_completion_marker_skips_before_network(monkeypatch, tmp_path):
    folder = tmp_path / "TEST-001"
    folder.mkdir()
    marker = folder / "movie.nfo"
    marker.write_bytes(b"existing")
    fetcher = MovieFetcher()

    monkeypatch.setattr(
        scrape_module,
        "fetch_javbus",
        lambda *args, **kwargs: pytest.fail("network source should not be called"),
    )

    assert scrape_module.scrape_one(
        folder, fetcher, SimpleNamespace(force=False)
    ) == ("SKIP", "movie.nfo exists; skipped (--force to override)")
    assert fetcher.begin_calls == 0
    assert marker.read_bytes() == b"existing"


def test_unrecognized_folder_skips_without_starting_network(tmp_path):
    folder = tmp_path / "not-a-code"
    folder.mkdir()
    fetcher = MovieFetcher()

    assert scrape_module.scrape_one(
        folder, fetcher, SimpleNamespace(force=False)
    ) == ("SKIP", "Catalog number not recognized")
    assert fetcher.begin_calls == 0


def test_force_replaces_generated_nfo_but_not_video_bytes(monkeypatch, tmp_path):
    folder = tmp_path / "TEST-001-C"
    folder.mkdir()
    video = folder / "original-name.mp4"
    video.write_bytes(b"video bytes")
    (folder / "movie.nfo").write_bytes(b"old movie nfo")
    sidecar = video.with_suffix(".nfo")
    sidecar.write_bytes(b"old sidecar")

    monkeypatch.setattr(
        scrape_module, "fetch_javbus", lambda current_fetcher, code: metadata(code)
    )
    monkeypatch.setattr(scrape_module, "fetch_javdb", lambda current_fetcher, code: None)
    monkeypatch.setattr(scrape_module, "download_with_alt", lambda *args, **kwargs: False)

    status, detail = scrape_module.scrape_one(
        folder, MovieFetcher(), SimpleNamespace(force=True)
    )

    assert status == "OK"
    assert "tags:中文字幕" in detail
    assert video.read_bytes() == b"video bytes"
    assert sidecar.read_bytes() != b"old sidecar"
    assert (folder / "movie.nfo").read_bytes() != b"old movie nfo"


def test_dual_source_tag_reflects_sources_used(monkeypatch, tmp_path):
    folder = tmp_path / "TEST-001"
    folder.mkdir()
    bus = metadata("TEST-001")
    db = {
        "source": "javdb",
        "code": "TEST-001",
        "dvdid": "TEST-001",
        "title": "中文标题",
        "genres": [],
        "actors": [],
        "samples": [],
    }
    monkeypatch.setattr(scrape_module, "fetch_javbus", lambda *args: bus)
    monkeypatch.setattr(scrape_module, "fetch_javdb", lambda *args: db)
    monkeypatch.setattr(scrape_module, "download_with_alt", lambda *args, **kwargs: False)

    status, detail = scrape_module.scrape_one(
        folder, MovieFetcher(), SimpleNamespace(force=False)
    )

    assert status == "OK"
    assert "[javbus+javdb]" in detail
    assert b"<source>javbus+javdb</source>" in (folder / "movie.nfo").read_bytes()


def test_inspect_reports_results_without_writing(tmp_path, capsys):
    recognized = tmp_path / "SONE-035"
    unrecognized = tmp_path / "not-a-code"
    recognized.mkdir()
    unrecognized.mkdir()
    before = sorted(path.name for path in tmp_path.rglob("*"))

    scrape_module.do_inspect([recognized, unrecognized])

    output = capsys.readouterr().out
    assert "Recognized 1 / Unrecognized 1 / Total 2" in output
    assert "No network requests or file writes were performed" in output
    assert sorted(path.name for path in tmp_path.rglob("*")) == before


@pytest.mark.parametrize("result", ["match", "mismatch", "empty", "blocked", "timeout"])
def test_default_plot_enrichment_preserves_primary_metadata(
    monkeypatch, tmp_path, controlled_fetcher, result
):
    folder = tmp_path / "TEST-001"
    folder.mkdir()
    (folder / "original.mp4").write_bytes(b"video")
    page_id = "TEST-002" if result == "mismatch" else "TEST-001"
    plot = "" if result == "empty" else "Example &amp; synopsis."
    response = SimpleNamespace(
        status_code=403 if result == "blocked" else 200, headers={},
        text=f'<div class="panel-body"><b>品番:</b> {page_id}<br>'
             f'<div class="row"><div class="col-md-12">{plot}</div></div></div>',
    )
    if result == "timeout":
        response = requests.Timeout()
    fetcher, _, _ = controlled_fetcher([response])
    monkeypatch.setattr(scrape_module, "fetch_javbus", lambda f, c: metadata(c))
    monkeypatch.setattr(scrape_module, "fetch_javdb", lambda *args: None)
    monkeypatch.setattr(scrape_module, "download_with_alt", lambda *args: False)

    status, _ = scrape_module.scrape_one(folder, fetcher, SimpleNamespace(force=False))

    assert status == "OK"
    assert fetcher.s.calls == 1
    for filename in ("movie.nfo", "original.nfo"):
        root = ET.parse(folder / filename)
        assert root.findtext("title") == "TEST-001 Title"
        assert root.findtext("num") == "TEST-001"
        assert root.findtext("plot") == ("Example & synopsis." if result == "match" else None)
        assert root.findtext("source") == ("javbus+jav321" if result == "match" else "javbus")
    assert (folder / "original.mp4").read_bytes() == b"video"


def test_plot_source_is_not_queried_without_primary_metadata(monkeypatch, tmp_path):
    folder = tmp_path / "TEST-001"
    folder.mkdir()
    monkeypatch.setattr(scrape_module, "fetch_javbus", lambda *args: None)
    monkeypatch.setattr(scrape_module, "fetch_javdb", lambda *args: None)
    monkeypatch.setattr(
        scrape_module, "fetch_jav321", lambda *args: pytest.fail("no primary metadata")
    )

    status, _ = scrape_module.scrape_one(folder, MovieFetcher(), SimpleNamespace(force=False))

    assert status == "MISS"
    assert not (folder / "movie.nfo").exists()
