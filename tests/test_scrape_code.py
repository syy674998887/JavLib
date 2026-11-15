import io
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest
from PIL import Image

from javlib import cli, scrape


def run_command(monkeypatch, *arguments):
    monkeypatch.setattr(cli.sys, "argv", ["javlib", "get", *arguments])
    return cli.main()


def source_metadata(code):
    return {
        "source": "javbus",
        "code": code,
        "dvdid": code,
        "title": "Example title",
        "genres": [],
        "actors": [],
        "cover": "https://images.example/cover.jpg",
        "samples": ["https://images.example/sample.jpg"],
    }


def test_code_command_needs_no_library_and_normalizes_input(monkeypatch):
    monkeypatch.setenv("JAVLIB_DIR", "/unused/library")

    args = cli.parse_cli_args(
        ["get", "sone00035", "3dsvr_1823", "fc2ppv1234567"]
    )

    assert args.codes == ["SONE-035", "3DSVR-1823", "FC2-PPV-1234567"]
    assert args.output == "output"
    assert not hasattr(args, "dir")
    assert (args.page_delay, args.image_delay, args.delay) == (5.0, 2.0, 10.0)


def test_code_command_accepts_custom_output_and_shared_scrape_options():
    args = cli.parse_cli_args(
        [
            "get", "SONE-035", "-o", "exports", "--force",
            "--page-delay", "8", "--image-delay", "3", "--delay", "15", "-v",
        ]
    )

    assert args.output == "exports"
    assert args.force and args.verbose
    assert (args.page_delay, args.image_delay, args.delay) == (8.0, 3.0, 15.0)


@pytest.mark.parametrize(
    "value", ["not-a-code", "", " ", "../SONE-035", r"..\SONE-035", "SONE-035.mp4"]
)
def test_invalid_code_is_rejected_before_any_output(monkeypatch, tmp_path, value):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as caught:
        run_command(monkeypatch, "SONE-035", value)

    assert caught.value.code == 2
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["SONE-035", "--dir", "library"],
        ["SONE-035", "--only", "SONE-035"],
        ["SONE-035", "--page-delay", "-1"],
        ["SONE-035", "--image-delay", "nan"],
    ],
)
def test_code_command_rejects_missing_codes_and_inapplicable_options(arguments):
    with pytest.raises(SystemExit) as caught:
        cli.parse_cli_args(["get", *arguments])

    assert caught.value.code == 2


def test_code_command_creates_complete_output_without_local_videos(
    monkeypatch, tmp_path, controlled_fetcher
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JAVLIB_DIR", str(tmp_path / "missing-library"))
    buffer = io.BytesIO()
    with Image.new("RGB", (800, 600), "navy") as picture:
        picture.save(buffer, format="JPEG")
    response = SimpleNamespace(
        status_code=200, headers={}, text="", content=buffer.getvalue()
    )
    fetcher, _, _ = controlled_fetcher(
        [response] * 4, page_delay=0, image_delay=0, title_delay=0
    )
    monkeypatch.setattr(cli, "Fetcher", lambda **kwargs: fetcher)
    queried = []

    def fetch_bus(current_fetcher, code):
        queried.append(code)
        return source_metadata(code)

    monkeypatch.setattr(scrape, "fetch_javbus", fetch_bus)
    monkeypatch.setattr(scrape, "fetch_javdb", lambda *args: None)

    assert run_command(monkeypatch, "sone00035", "sone_035", "SSIS-001") == 0

    assert queried == ["SONE-035", "SSIS-001"]
    assert fetcher.s.calls == 4
    output = tmp_path / "output"
    assert sorted(path.name for path in output.iterdir()) == ["SONE-035", "SSIS-001"]
    for code in queried:
        folder = output / code
        assert {path.name for path in folder.iterdir()} == {
            "movie.nfo", "fanart.jpg", "poster.jpg", "Samples"
        }
        assert ET.parse(folder / "movie.nfo").findtext("num") == code
        with Image.open(folder / "fanart.jpg") as cover:
            assert cover.size == (800, 600)
        with Image.open(folder / "poster.jpg") as poster:
            assert poster.size == (380, 600)
        with Image.open(folder / "Samples" / "sample1.jpg") as sample:
            assert sample.size == (800, 600)


def test_custom_output_skips_completed_titles_and_force_refreshes_only_requested_code(
    monkeypatch, tmp_path, controlled_fetcher
):
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "exports"
    folder = output / "SONE-035"
    folder.mkdir(parents=True)
    marker = folder / "movie.nfo"
    marker.write_bytes(b"existing metadata")
    unrelated = output / "SSIS-001"
    unrelated.mkdir()
    fetcher, _, _ = controlled_fetcher([], title_delay=0)
    monkeypatch.setattr(cli, "Fetcher", lambda **kwargs: fetcher)
    queried = []

    def fetch_bus(current_fetcher, code):
        queried.append(code)
        return source_metadata(code)

    monkeypatch.setattr(scrape, "fetch_javbus", fetch_bus)
    monkeypatch.setattr(scrape, "fetch_javdb", lambda *args: None)
    monkeypatch.setattr(scrape, "download_with_alt", lambda *args, **kwargs: False)

    assert run_command(monkeypatch, "SONE-035", "--output", str(output)) == 0
    assert queried == []
    assert marker.read_bytes() == b"existing metadata"

    run_command(monkeypatch, "SONE-035", "--output", str(output), "--force")
    assert queried == ["SONE-035"]
    assert ET.parse(marker).findtext("num") == "SONE-035"
    assert list(unrelated.iterdir()) == []
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize(
    ("failure", "expected_exit", "continued"),
    [(None, 1, True), (RuntimeError, 1, True), (KeyboardInterrupt, 130, False)],
)
def test_failure_status_and_batch_continuation(
    monkeypatch, tmp_path, controlled_fetcher, failure, expected_exit, continued
):
    fetcher, _, _ = controlled_fetcher([], title_delay=0)
    monkeypatch.setattr(cli, "Fetcher", lambda **kwargs: fetcher)

    def fetch_bus(current_fetcher, code):
        if code == "TEST-001":
            if failure:
                raise failure("simulated failure")
            return None
        return source_metadata(code)

    monkeypatch.setattr(scrape, "fetch_javbus", fetch_bus)
    monkeypatch.setattr(scrape, "fetch_javdb", lambda *args: None)
    monkeypatch.setattr(scrape, "download_with_alt", lambda *args, **kwargs: False)

    result = run_command(
        monkeypatch, "TEST-001", "TEST-002", "--output", str(tmp_path)
    )

    assert result == expected_exit
    assert not (tmp_path / "TEST-001" / "movie.nfo").exists()
    assert (tmp_path / "TEST-002" / "movie.nfo").exists() is continued


@pytest.mark.parametrize("occupied_root", [True, False])
def test_occupied_output_paths_fail_before_scraping(monkeypatch, tmp_path, occupied_root):
    output = tmp_path / "output"
    if occupied_root:
        occupied = output
    else:
        output.mkdir()
        occupied = output / "SSIS-001"
    occupied.write_bytes(b"keep this file")
    monkeypatch.setattr(cli, "Fetcher", lambda **kwargs: pytest.fail("must not scrape"))

    with pytest.raises(SystemExit, match="Unable to prepare output directory"):
        run_command(monkeypatch, "SONE-035", "SSIS-001", "--output", str(output))

    assert occupied.read_bytes() == b"keep this file"
    assert not (output / "SONE-035").exists()
