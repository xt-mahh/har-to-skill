"""Tests for the security scanner module."""

import pytest

from scripts.security_scanner import SecurityScanner


class MockEntry:
    """Minimal mock entry compatible with HarEntry interface."""
    def __init__(self, request_headers=None, url="", request_body=None,
                 response_body=None):
        self.request_headers = request_headers or {}
        self.url = url
        self.request_body = request_body
        self.response_body = response_body


@pytest.fixture
def scanner():
    return SecurityScanner(strict=True)


@pytest.fixture
def strict_scanner():
    return SecurityScanner(strict=True)


# ---------------------------------------------------------------------------
# scan_entry — detection tests
# ---------------------------------------------------------------------------

def test_scan_entry_detects_jwt(scanner):
    """JWT tokens in headers should be flagged as critical."""
    token = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    entry = MockEntry(
        request_headers={"Authorization": f"Bearer {token}"},
        url="https://api.example.com/users",
    )
    findings = scanner.scan_entry(entry)
    jwt_findings = [f for f in findings if f["type"] == "jwt"]
    assert len(jwt_findings) >= 1
    assert jwt_findings[0]["severity"] == "critical"


def test_scan_entry_detects_bearer(scanner):
    """Bearer tokens in headers should be flagged."""
    entry = MockEntry(
        request_headers={"Authorization": "Bearer sk-1234567890abcdef1234567890abcdef"},
        url="https://api.example.com/data",
    )
    findings = scanner.scan_entry(entry)
    bearer_findings = [f for f in findings if f["type"] == "bearer_token"]
    assert len(bearer_findings) >= 1
    assert bearer_findings[0]["severity"] == "critical"


def test_scan_entry_detects_phone_in_body(scanner):
    """Phone numbers in request body should be flagged as high severity."""
    entry = MockEntry(
        request_headers={"content-type": "application/json"},
        url="https://api.example.com/register",
        request_body='{"phone": "13800138000", "name": "test"}',
    )
    findings = scanner.scan_entry(entry)
    phone_findings = [f for f in findings if f["type"] == "phone_number"]
    assert len(phone_findings) >= 1
    # Phone in request body should be severity 'high'
    assert phone_findings[0]["severity"] == "high"


def test_scan_entry_detects_api_key_in_url(scanner):
    """API keys in URL query parameters should be flagged."""
    entry = MockEntry(
        request_headers={},
        url="https://api.example.com/data?api_key=abc123def456ghi789jkl012&foo=bar",
    )
    findings = scanner.scan_entry(entry)
    key_findings = [f for f in findings if f["type"] == "api_key_in_url"]
    assert len(key_findings) >= 1
    assert key_findings[0]["location"] == "request.url"


def test_scan_entry_detects_internal_ip_in_response(scanner):
    """Internal IP addresses in response body should be flagged as medium."""
    entry = MockEntry(
        request_headers={},
        url="https://api.example.com/status",
        response_body='{"internal_ip": "10.0.0.5", "status": "ok"}',
    )
    findings = scanner.scan_entry(entry)
    ip_findings = [f for f in findings if f["type"] == "internal_ip"]
    assert len(ip_findings) >= 1
    assert ip_findings[0]["severity"] == "medium"


# ---------------------------------------------------------------------------
# sanitize_headers
# ---------------------------------------------------------------------------

def test_sanitize_headers_redacts_sensitive_keys(scanner):
    """Authorization, X-Api-Key, Cookie etc. should be redacted."""
    headers = {
        "Authorization": "Bearer my-secret-token",
        "X-Api-Key": "sk-abcdef123456",
        "X-Tenant-Key": "tenant-abc",
        "X-Auth-Token": "tok_12345",
        "Content-Type": "application/json",
        "Accept": "*/*",
    }
    cleaned = scanner.sanitize_headers(headers)
    assert cleaned["Authorization"] == "<REDACTED>"
    assert cleaned["X-Api-Key"] == "<REDACTED>"
    assert cleaned["X-Tenant-Key"] == "<REDACTED>"
    assert cleaned["X-Auth-Token"] == "<REDACTED>"
    assert cleaned["Content-Type"] == "application/json"
    assert cleaned["Accept"] == "*/*"
    assert len(cleaned) == len(headers)


def test_sanitize_headers_handles_empty_dict(scanner):
    """Empty headers dict should return empty dict."""
    assert scanner.sanitize_headers({}) == {}


# ---------------------------------------------------------------------------
# sanitize_url
# ---------------------------------------------------------------------------

def test_sanitize_url_removes_sensitive_params(scanner):
    """URL query parameters like token, api_key, secret should be stripped."""
    url = "https://api.example.com/data?token=abc123&api_key=xyz789&name=test&secret=mys3cret"
    sanitized = scanner.sanitize_url(url)
    assert "token=" not in sanitized
    assert "api_key=" not in sanitized
    assert "secret=" not in sanitized
    assert "name=test" in sanitized


def test_sanitize_url_unchanged_when_clean(scanner):
    """URL with no sensitive parameters should be unchanged."""
    url = "https://api.example.com/data?name=test&page=1"
    sanitized = scanner.sanitize_url(url)
    assert sanitized == url


def test_sanitize_url_no_query_string(scanner):
    """URL without query string should remain unchanged."""
    url = "https://api.example.com/data"
    sanitized = scanner.sanitize_url(url)
    assert sanitized == url


# ---------------------------------------------------------------------------
# scan_output
# ---------------------------------------------------------------------------

def test_scan_output_detects_sensitive_data(scanner):
    """Scanning output markdown should detect leaked secrets."""
    skill_md = (
        "# API Skill\n\n"
        "```\n"
        "Authorization: Bearer sk-abcdef1234567890abcdef1234567890\n"
        "```\n\n"
        'Phone: 13912345678\n\n'
        "Internal IP: 192.168.1.1\n"
    )
    findings = scanner.scan_output(skill_md)
    assert len(findings) >= 1
    # Check that at least bearer_token or phone_number is found
    types_found = {f["type"] for f in findings}
    assert "bearer_token" in types_found or "phone_number" in types_found


def test_scan_output_clean_md(scanner):
    """Clean output with no sensitive data should return empty list."""
    skill_md = "# My Skill\nThis is a clean API skill description."
    findings = scanner.scan_output(skill_md)
    assert findings == []


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def test_report_empty_findings(scanner):
    """No findings should produce a pass message."""
    msg = scanner.report([])
    assert "通过" in msg or "未发现" in msg


def test_report_with_findings(scanner):
    """Findings should produce a formatted report with severity icons."""
    findings = [
        {"type": "jwt", "location": "request.headers.Authorization",
         "severity": "critical"},
        {"type": "api_key_in_url", "location": "request.url",
         "severity": "high"},
    ]
    msg = scanner.report(findings)
    assert "CRITICAL" in msg
    assert "HIGH" in msg
    assert "jwt" in msg
    assert "api_key_in_url" in msg


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_scan_entry_no_sensitive_data(scanner):
    """Entry with no sensitive data should return empty findings."""
    entry = MockEntry(
        request_headers={"Content-Type": "application/json"},
        url="https://api.example.com/users",
        request_body='{"name": "test"}',
        response_body='{"id": 1, "name": "test"}',
    )
    findings = scanner.scan_entry(entry)
    assert findings == []
