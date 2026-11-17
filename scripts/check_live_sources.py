"""Check the real metadata adapters for HTML changes with one title per source.

No images, media-library files, or account credentials are used. Access failures
are reported separately from missing metadata; either leaves the check failing
so an unverified source never appears healthy.
"""

import os
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from javlib.fetcher import Fetcher
from javlib.sources import _same_code, fetch_jav321, fetch_javbus, fetch_javdb


class ProbeFailure(RuntimeError):
    def __init__(self, category, message):
        super().__init__(message)
        self.category = category


class ProbeFetcher(Fetcher):
    """Keep diagnostics and retry transient errors once, never access blocks."""

    TRANSIENT = {0, 408, 500, 502, 503, 504}

    def __init__(self):
        super().__init__(page_delay=5.0, image_delay=0.0, title_delay=0.0)
        self.history = []
        self.response = None
        self.s.hooks["response"].append(self._remember_response)

    def _remember_response(self, response, *args, **kwargs):
        self.response = response

    def _request(self, method, url, referer=None, binary=False, max_retry=5, data=None):
        for attempt in range(2):
            self.response = None
            status, body = super()._request(
                method, url, referer=referer, binary=binary, max_retry=1, data=data
            )
            response = self.response
            final_url = response.url if response is not None else url
            redirect = f" -> {final_url}" if final_url != url else ""
            self.history.append(f"HTTP {status} {url}{redirect}")

            if status in {401, 403, 429}:
                raise ProbeFailure("ACCESS_BLOCKED", f"HTTP {status}; no retry")
            path = urlsplit(final_url).path.rstrip("/")
            if path in {"/login", "/signin", "/auth/signin"}:
                raise ProbeFailure("ACCESS_BLOCKED", "redirected to a login page")
            challenge = response is not None and (
                response.headers.get("cf-mitigated") == "challenge"
            )
            page = response.text if response is not None else body
            challenge = challenge or (
                isinstance(page, str)
                and re.search(
                    r"<title[^>]*>\s*(?:Just a moment|Attention Required)[^<]*</title>",
                    page,
                    re.I,
                )
            )
            if challenge:
                raise ProbeFailure("ACCESS_BLOCKED", "verification page returned")
            if status == 200:
                return status, body

            if status in self.TRANSIENT and attempt == 0:
                time.sleep(3)
                continue
            category = "NETWORK_ERROR" if status in self.TRANSIENT else "HTTP_ERROR"
            raise ProbeFailure(category, f"request failed with HTTP {status}")


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _url(value):
    if not _text(value):
        return False
    try:
        parsed = urlsplit(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname)
    except ValueError:
        return False


def validate(data, source, code):
    """Validate fields known to exist on the configured reference title."""
    if not data:
        return ["no matching metadata parsed; inspect the HTML or reference title"]
    problems = []
    if data.get("source") != source:
        problems.append("unexpected source")
    if not _same_code(data.get("dvdid"), code):
        problems.append("catalog number mismatch")
    if source == "jav321":
        if not _text(data.get("plot")):
            problems.append("plot missing")
        return problems
    title = data.get("title")
    if not _text(title) or _same_code(title, code):
        problems.append("title missing or only the catalog number")
    try:
        date.fromisoformat((data.get("release") or "").replace("/", "-"))
    except (ValueError, TypeError, AttributeError):
        problems.append("release date missing or invalid")
    runtime = data.get("runtime")
    if type(runtime) is not int or runtime <= 0:
        problems.append("runtime missing or invalid")
    if not _text(data.get("studio")):
        problems.append("studio missing")
    if not _url(data.get("cover")):
        problems.append("cover URL missing or invalid")
    actors = data.get("actors")
    if not isinstance(actors, list) or not actors or not all(
        isinstance(actor, dict) and _text(actor.get("name")) for actor in actors
    ):
        problems.append("actor names missing or invalid")
    for field, valid in (("genres", _text), ("samples", _url)):
        values = data.get(field)
        if not isinstance(values, list) or not values or not all(map(valid, values)):
            problems.append(f"{field} missing or invalid")
    return problems


def check_source(fetch, source, code, fetcher):
    try:
        problems = validate(fetch(fetcher, code), source, code)
    except ProbeFailure as error:
        return error.category, str(error)
    except Exception as error:
        return "CHECK_ERROR", f"{type(error).__name__}: {error}"
    if problems:
        return "PARSE_ERROR", "; ".join(problems)
    if source == "jav321":
        return "PASS", "complete matching ID and plot valid"
    return "PASS", "ID, title, date, runtime, studio, actors, genres and image URLs valid"


def _annotation(text):
    return str(text).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _cell(text):
    return str(text).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def main():
    probes = (
        ("JavBus", "javbus", fetch_javbus, os.getenv("JAVBUS_SMOKE_CODE", "SONE-035")),
        ("JavDB", "javdb", fetch_javdb, os.getenv("JAVDB_SMOKE_CODE", "SONE-035")),
        ("Jav321", "jav321", fetch_jav321, os.getenv("JAV321_SMOKE_CODE", "SONE-035")),
    )
    summary = [
        "## Daily metadata parser checks", "",
        "PARSE_ERROR: required metadata is missing; review the adapter and reference title.",
        "ACCESS_BLOCKED / NETWORK_ERROR / HTTP_ERROR: live parsing could not be verified.",
        "CHECK_ERROR: the check or adapter raised an unexpected exception.", "",
        "| Source | Code | Result | Details |",
        "| --- | --- | --- | --- |",
    ]
    failed = False
    for name, source, fetch, raw_code in probes:
        code = raw_code.strip()
        fetcher = ProbeFetcher()
        try:
            result, message = check_source(fetch, source, code, fetcher)
        finally:
            fetcher.s.close()
        failed = failed or result != "PASS"
        print(f"{result} {name} ({code}): {message}", flush=True)
        if result != "PASS":
            print(f"::error title={name} {result}::{_annotation(message)}", flush=True)
        print("  " + "; ".join(fetcher.history or ["no HTTP requests"]), flush=True)
        summary.append(
            "| " + " | ".join(map(_cell, (name, code, result, message))) + " |"
        )

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as file:
            file.write("\n".join(summary) + "\n")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
