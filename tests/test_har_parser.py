"""Tests for the HAR parser."""

import json
from pathlib import Path

import pytest

from scripts.har_parser import HarParser, HarEntry

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def simple_har_path():
    return str(FIXTURES_DIR / "simple-api.har")


def test_parse_counts_entries(simple_har_path):
    """Parsing a HAR file with 3 entries should return 3 HarEntry objects."""
    parser = HarParser()
    entries = parser.parse(simple_har_path)
    assert len(entries) == 3
    assert all(isinstance(e, HarEntry) for e in entries)


def test_parse_extracts_method_and_url(simple_har_path):
    """Verify the first API entry is extracted correctly."""
    parser = HarParser()
    entries = parser.parse(simple_har_path)
    api_entry = entries[0]
    assert api_entry.method == "GET"
    assert "/open-apis/contact/v3/users/12345" in api_entry.url


def test_parse_extracts_request_body(simple_har_path):
    """Verify request body is extracted from postData."""
    parser = HarParser()
    entries = parser.parse(simple_har_path)
    # The third entry (google-analytics) has a request body
    analytics_entry = entries[2]
    assert analytics_entry.request_body is not None
    assert "v=1&t=pageview" in analytics_entry.request_body


def test_parse_extracts_response_body(simple_har_path):
    """Verify response body is extracted and pretty-printed JSON."""
    parser = HarParser()
    entries = parser.parse(simple_har_path)
    api_entry = entries[0]
    assert api_entry.response_body is not None
    # Should be pretty-printed JSON
    assert '"Test User"' in api_entry.response_body
    # Verify it can be re-parsed as valid JSON
    parsed = json.loads(api_entry.response_body)
    assert parsed["code"] == 0


def test_filter_removes_images(simple_har_path):
    """Filter should remove the logo.png image request."""
    parser = HarParser()
    entries = parser.parse(simple_har_path)
    api_calls = parser.filter_api_calls(entries)
    urls = [e.url for e in api_calls]
    assert all("logo.png" not in url for url in urls)


def test_filter_removes_analytics_tracking(simple_har_path):
    """Filter should remove google-analytics.com tracking requests."""
    parser = HarParser()
    entries = parser.parse(simple_har_path)
    api_calls = parser.filter_api_calls(entries)
    urls = [e.url for e in api_calls]
    assert all("google-analytics.com" not in url for url in urls)


def test_filter_keeps_api_calls(simple_har_path):
    """Filter should keep the /open-apis/ API call."""
    parser = HarParser()
    entries = parser.parse(simple_har_path)
    api_calls = parser.filter_api_calls(entries)
    urls = [e.url for e in api_calls]
    assert any("/open-apis/contact/v3/users/12345" in url for url in urls)


def test_filter_all_entries_reduces_count(simple_har_path):
    """After filtering, we should have exactly 1 API call remaining (out of 3)."""
    parser = HarParser()
    entries = parser.parse(simple_har_path)
    api_calls = parser.filter_api_calls(entries)
    assert len(api_calls) == 1


def test_options_request_is_filtered():
    """OPTIONS requests should always be filtered out."""
    parser = HarParser()
    entry = HarEntry(
        method="OPTIONS",
        url="https://api.example.com/data",
        request_headers={"content-type": "application/json"},
        response_headers={"content-type": "application/json"},
    )
    result = parser.filter_api_calls([entry])
    assert len(result) == 0


def test_connect_request_is_filtered():
    """CONNECT requests should always be filtered out."""
    parser = HarParser()
    entry = HarEntry(method="CONNECT", url="https://api.example.com")
    result = parser.filter_api_calls([entry])
    assert len(result) == 0


def test_empty_har_file(tmp_path):
    """Parsing an empty HAR should return empty list."""
    har = {"log": {"entries": []}}
    har_path = tmp_path / "empty.har"
    with open(har_path, "w") as f:
        json.dump(har, f)

    parser = HarParser()
    entries = parser.parse(str(har_path))
    assert entries == []


def test_har_without_log(tmp_path):
    """HAR missing 'log' key should return empty list."""
    har = {}
    har_path = tmp_path / "no-log.har"
    with open(har_path, "w") as f:
        json.dump(har, f)

    parser = HarParser()
    entries = parser.parse(str(har_path))
    assert entries == []
