import importlib.util
from pathlib import Path

import pytest
import requests


spec = importlib.util.spec_from_file_location(
    "check_live_sources",
    Path(__file__).resolve().parents[1] / "scripts" / "check_live_sources.py",
)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


@pytest.fixture
def metadata():
    return {
        "source": "javdb",
        "dvdid": "TEST-001",
        "title": "Example title",
        "release": "2024-02-03",
        "runtime": 120,
        "studio": "Example studio",
        "actors": [{"name": "Example actress", "thumb": ""}],
        "genres": ["Example genre"],
        "cover": "https://images.example/cover.jpg",
        "samples": ["https://images.example/sample.jpg"],
    }


def test_reference_metadata_passes(metadata):
    assert check.validate(metadata, "javdb", "TEST-001") == []


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("actors", [], "actor names"),
        ("actors", [{"name": " "}], "actor names"),
        ("runtime", None, "runtime"),
        ("runtime", True, "runtime"),
        ("studio", "", "studio"),
        ("genres", [], "genres"),
        ("samples", [], "samples"),
        ("samples", ["/relative.jpg"], "samples"),
        ("cover", "https://", "cover URL"),
        ("release", "2024-02-30", "release date"),
        ("title", "TEST-001", "title"),
        ("dvdid", "TEST-002", "catalog number"),
    ],
)
def test_missing_or_invalid_metadata_cannot_pass(metadata, field, value, message):
    metadata[field] = value

    category, detail = check.check_source(
        lambda fetcher, code: metadata, "javdb", "TEST-001", None
    )

    assert category == "PARSE_ERROR"
    assert message in detail


def test_empty_metadata_is_a_parse_failure():
    category, detail = check.check_source(
        lambda fetcher, code: None, "javdb", "TEST-001", None
    )

    assert category == "PARSE_ERROR"
    assert "no matching metadata" in detail


class ScriptedAdapter(requests.adapters.BaseAdapter):
    """Exercise real Requests response hooks and redirects without a network."""

    def __init__(self, responses):
        self.responses = iter(responses)
        self.urls = []
        self.requests = []

    def send(self, request, **kwargs):
        self.urls.append(request.url)
        self.requests.append(request)
        item = next(self.responses)
        if isinstance(item, Exception):
            raise item
        status, headers, text = item
        response = requests.Response()
        response.status_code = status
        response.headers.update(headers)
        response._content = text.encode("utf-8")
        response.encoding = "utf-8"
        response.url = request.url
        response.request = request
        return response

    def close(self):
        pass


def probe_with_responses(monkeypatch, responses):
    probe = check.ProbeFetcher()
    adapter = ScriptedAdapter(responses)
    probe.s.mount("https://", adapter)
    monkeypatch.setattr(check.time, "sleep", lambda seconds: None)
    return probe, adapter


@pytest.mark.parametrize("status", [401, 403, 429])
def test_access_denial_is_not_retried(monkeypatch, status):
    probe, adapter = probe_with_responses(monkeypatch, [(status, {}, "blocked")])

    with pytest.raises(check.ProbeFailure) as caught:
        probe.get("https://javdb.com/search?q=TEST-001&f=all")

    assert caught.value.category == "ACCESS_BLOCKED"
    assert len(adapter.urls) == 1


def test_login_redirect_with_http_200_is_not_a_parser_failure(monkeypatch):
    probe, adapter = probe_with_responses(
        monkeypatch,
        [(302, {"Location": "/login"}, ""), (200, {}, "<title>Login</title>")],
    )

    category, detail = check.check_source(
        check.fetch_javdb, "javdb", "TEST-001", probe
    )

    assert category == "ACCESS_BLOCKED"
    assert "login" in detail
    assert adapter.urls == [
        "https://javdb.com/search?q=TEST-001&f=all",
        "https://javdb.com/login",
    ]
    assert probe.history == [
        "HTTP 200 https://javdb.com/search?q=TEST-001&f=all -> https://javdb.com/login"
    ]


@pytest.mark.parametrize(
    ("status", "headers", "page"),
    [
        (200, {}, "<title>Just a moment...</title>"),
        (503, {"cf-mitigated": "challenge"}, "Verification required"),
    ],
)
def test_challenge_pages_stop_without_retries(monkeypatch, status, headers, page):
    probe, adapter = probe_with_responses(monkeypatch, [(status, headers, page)])

    with pytest.raises(check.ProbeFailure) as caught:
        probe.get("https://javdb.com/search?q=TEST-001&f=all")

    assert caught.value.category == "ACCESS_BLOCKED"
    assert len(adapter.urls) == 1


def test_normal_page_with_captcha_script_is_not_blocked(monkeypatch):
    page = '<title>Metadata</title><script src="/captcha/challenge-platform.js"></script>'
    probe, _ = probe_with_responses(monkeypatch, [(200, {}, page)])

    assert probe.get("https://javdb.com/v/example") == (200, page)


def test_transient_error_retries_once_and_can_recover(monkeypatch):
    probe, adapter = probe_with_responses(
        monkeypatch, [(503, {}, "unavailable"), (200, {}, "metadata")]
    )

    assert probe.get("https://javdb.com/v/example") == (200, "metadata")
    assert len(adapter.urls) == 2


def test_transport_failure_is_not_reported_as_html_drift(monkeypatch):
    probe, adapter = probe_with_responses(
        monkeypatch, [requests.Timeout("first"), requests.Timeout("second")]
    )

    category, _ = check.check_source(check.fetch_javdb, "javdb", "TEST-001", probe)

    assert category == "NETWORK_ERROR"
    assert len(adapter.urls) == 2


@pytest.mark.parametrize("failure", ["PARSE_ERROR", "ACCESS_BLOCKED"])
def test_summary_keeps_failure_category_and_does_not_report_success(
    monkeypatch, tmp_path, metadata, capsys, failure
):
    monkeypatch.setenv("JAVBUS_SMOKE_CODE", "TEST-001")
    monkeypatch.setenv("JAVDB_SMOKE_CODE", "TEST-001")
    monkeypatch.setenv("JAV321_SMOKE_CODE", "TEST-001")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr(
        check, "fetch_javbus", lambda fetcher, code: dict(metadata, source="javbus")
    )

    def failing_source(fetcher, code):
        if failure == "ACCESS_BLOCKED":
            raise check.ProbeFailure("ACCESS_BLOCKED", "redirected to a login page")
        return dict(metadata, actors=[])

    monkeypatch.setattr(check, "fetch_javdb", failing_source)
    monkeypatch.setattr(
        check, "fetch_jav321",
        lambda fetcher, code: {"source": "jav321", "dvdid": code, "plot": "Synopsis"},
    )

    assert check.main() == 1
    output = capsys.readouterr().out
    assert "PASS JavBus" in output
    assert "PASS Jav321" in output
    assert f"{failure} JavDB" in output
    assert f"| JavDB | TEST-001 | {failure} |" in summary.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("page_id", "plot", "expected"),
    [("TEST-001", "Synopsis", "PASS"), ("TEST-002", "Synopsis", "PARSE_ERROR"),
     ("TEST-001", " ", "PARSE_ERROR")],
)
def test_plot_source_checks_id_and_plot_only(page_id, plot, expected):
    result, _ = check.check_source(
        lambda f, c: {"source": "jav321", "dvdid": page_id, "plot": plot},
        "jav321", "TEST-001", None,
    )
    assert result == expected


def test_jav321_probe_follows_post_redirect_without_extra_detail_request(monkeypatch):
    page = '<div class="panel-body"><b>品番:</b> TEST-001<br>' \
           '<div class="row"><div class="col-md-12">Synopsis</div></div></div>'
    probe, adapter = probe_with_responses(
        monkeypatch, [(301, {"Location": "/video/test00001"}, ""), (200, {}, page)]
    )

    result, _ = check.check_source(check.fetch_jav321, "jav321", "TEST-001", probe)

    assert result == "PASS"
    assert [request.method for request in adapter.requests] == ["POST", "GET"]
    assert adapter.requests[0].body == "sn=TEST-001"
    assert adapter.urls == [
        "https://www.jav321.com/search", "https://www.jav321.com/video/test00001"
    ]


@pytest.mark.parametrize("status", [403, 429])
def test_jav321_probe_reports_access_blocks_without_retry(monkeypatch, status):
    probe, adapter = probe_with_responses(monkeypatch, [(status, {}, "blocked")])

    result, _ = check.check_source(check.fetch_jav321, "jav321", "TEST-001", probe)

    assert result == "ACCESS_BLOCKED"
    assert len(adapter.urls) == 1


def test_jav321_parse_failure_describes_the_page_without_its_text(monkeypatch):
    # The search stays on /search (no redirect), as it did from Nov 21 to Nov 24.
    page = (
        "<title>JAV321 search</title><p>Private body text</p>"
        '<a href="/video/sone00035">one</a><a href="/video/sone00036">two</a>'
    )
    probe, _ = probe_with_responses(monkeypatch, [(200, {}, page)])

    result, message = check.check_source(check.fetch_jav321, "jav321", "SONE-035", probe)

    assert result == "PARSE_ERROR"
    assert "no matching metadata parsed" in message
    assert "title=JAV321 search" in message
    assert "品番=0" in message
    assert "video links=2 /video/sone00035 /video/sone00036" in message
    assert "Private body text" not in message


def test_page_description_handles_a_missing_response():
    assert check.describe_page(None) == "page: no response"
