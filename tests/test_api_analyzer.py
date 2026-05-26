"""Tests for the API Analyzer module."""

import pytest

from scripts.api_analyzer import ApiAnalyzer, ApiEndpoint
from scripts.har_parser import HarEntry


def make_entry(
    method="GET",
    url="https://api.example.com/v1/users/12345",
    request_headers=None,
    request_body=None,
    response_status=200,
    response_body=None,
):
    return HarEntry(
        method=method,
        url=url,
        request_headers=request_headers or {},
        request_body=request_body,
        response_status=response_status,
        response_body=response_body,
    )


@pytest.fixture
def analyzer():
    return ApiAnalyzer()


class TestClusterByService:
    def test_groups_by_base_url(self, analyzer):
        entries = [
            make_entry(url="https://api.example.com/v1/users"),
            make_entry(url="https://api.example.com/v1/products"),
            make_entry(url="https://other.api.com/v2/items"),
        ]
        groups = analyzer.cluster_by_service(entries)
        assert len(groups) == 2
        assert any("api.example.com" in k for k in groups)
        assert any("other.api.com" in k for k in groups)

    def test_same_service_same_group(self, analyzer):
        entries = [
            make_entry(url="https://api.example.com/v1/users/1"),
            make_entry(url="https://api.example.com/v1/users/2"),
            make_entry(url="https://api.example.com/v1/products"),
        ]
        groups = analyzer.cluster_by_service(entries)
        # All three share the same netloc and first path segment
        matching = [k for k in groups if "api.example.com" in k]
        assert len(matching) == 1
        assert len(groups[matching[0]]) == 3


class TestExtractPathPattern:
    def test_single_url_parameterizes_id(self, analyzer):
        base, pattern, example = analyzer.extract_path_pattern(
            ["https://api.example.com/v1/users/12345"]
        )
        assert base == "https://api.example.com"
        assert "{id}" in pattern
        assert "12345" in example

    def test_single_url_parameterizes_uuid(self, analyzer):
        base, pattern, example = analyzer.extract_path_pattern(
            ["https://api.example.com/v1/orders/550e8400-e29b-41d4-a716-446655440000"]
        )
        assert base == "https://api.example.com"
        assert "{uuid}" in pattern

    def test_single_url_preserves_literal_segments(self, analyzer):
        base, pattern, _ = analyzer.extract_path_pattern(
            ["https://api.example.com/v1/users"]
        )
        assert "v1" in pattern
        assert "users" in pattern

    def test_multi_url_merges_to_pattern(self, analyzer):
        urls = [
            "https://api.example.com/v1/users/12345",
            "https://api.example.com/v1/users/67890",
            "https://api.example.com/v1/users/99999",
        ]
        base, pattern, example = analyzer.extract_path_pattern(urls)
        assert base == "https://api.example.com"
        assert pattern == "/v1/users/{id}"
        assert example == urls[0]

    def test_multi_url_merges_different_param_types(self, analyzer):
        urls = [
            "https://api.example.com/v1/users/12345",
            "https://api.example.com/v1/users/550e8400-e29b-41d4-a716-446655440000",
        ]
        base, pattern, _ = analyzer.extract_path_pattern(urls)
        assert base == "https://api.example.com"
        # Both are parameterizable — either {id} or {uuid} may be chosen
        # The first URL (12345) maps to {id}, and both should collapse to
        # a single param placeholder since each segment is parameterizable.
        # The algorithm picks the param from the first unique value it sees
        # that maps to a known pattern.
        # With 12345 -> {id} and uuid -> {uuid}, these are different
        # param_candidates, so param_set for two different unique values
        # will have size > 1, and it falls back to {param_2}
        assert "{param_" in pattern or "{id}" in pattern or "{uuid}" in pattern


class TestDetectAuth:
    def test_bearer_token_detected(self, analyzer):
        entries = [
            make_entry(
                url="https://api.example.com/v1/users",
                request_headers={"authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.dGVzdA"},
            )
        ]
        auth_type, auth_display = analyzer.detect_auth(entries)
        assert auth_type == "bearer"
        assert "BEARER" in auth_display.upper()

    def test_no_auth_returns_none(self, analyzer):
        entries = [
            make_entry(
                url="https://api.example.com/v1/users",
                request_headers={},
            )
        ]
        auth_type, auth_display = analyzer.detect_auth(entries)
        assert auth_type is None
        assert auth_display is None

    def test_api_key_detected(self, analyzer):
        entries = [
            make_entry(
                url="https://api.example.com/v1/users",
                request_headers={"x-api-key": "abc123def456"},
            )
        ]
        auth_type, auth_display = analyzer.detect_auth(entries)
        assert auth_type == "apikey"

    def test_tenant_key_detected(self, analyzer):
        entries = [
            make_entry(
                url="https://api.example.com/v1/users",
                request_headers={"x-tenant-key": "my-tenant"},
            )
        ]
        auth_type, auth_display = analyzer.detect_auth(entries)
        assert auth_type == "tenant"


class TestRequestBodySchema:
    def test_simple_dict_schema(self, analyzer):
        entry = make_entry(request_body='{"name": "Alice", "age": 30, "active": true}')
        schema = analyzer.abstract_request_body(entry)
        assert schema == {
            "name": "<string>",
            "age": "<integer>",
            "active": "<boolean>",
        }

    def test_nested_dict_schema(self, analyzer):
        entry = make_entry(request_body='{"user": {"name": "Alice", "age": 30}}')
        schema = analyzer.abstract_request_body(entry)
        assert schema == {"user": {"name": "<string>", "age": "<integer>"}}

    def test_empty_body_returns_none(self, analyzer):
        entry = make_entry(request_body=None)
        schema = analyzer.abstract_request_body(entry)
        assert schema is None

    def test_invalid_json_returns_none(self, analyzer):
        entry = make_entry(request_body="not-json-at-all")
        schema = analyzer.abstract_request_body(entry)
        assert schema is None

    def test_list_schema(self, analyzer):
        entry = make_entry(request_body='[{"id": 1, "name": "Alice"}]')
        schema = analyzer.abstract_request_body(entry)
        assert schema == [{"id": "<integer>", "name": "<string>"}]

    def test_float_number(self, analyzer):
        entry = make_entry(request_body='{"price": 19.99}')
        schema = analyzer.abstract_request_body(entry)
        assert schema == {"price": "<number>"}

    def test_app_id_pattern(self, analyzer):
        entry = make_entry(request_body='{"app_id": "cli_abc123"}')
        schema = analyzer.abstract_request_body(entry)
        assert schema == {"app_id": "<app_id>"}

    def test_token_pattern(self, analyzer):
        entry = make_entry(request_body='{"token": "t-secret123"}')
        schema = analyzer.abstract_request_body(entry)
        assert schema == {"token": "<token>"}

    def test_long_string_becomes_secret(self, analyzer):
        entry = make_entry(request_body='{"secret": "' + "a" * 40 + '"}')
        schema = analyzer.abstract_request_body(entry)
        assert schema == {"secret": "<secret>"}

    def test_url_string(self, analyzer):
        entry = make_entry(request_body='{"url": "https://example.com/callback"}')
        schema = analyzer.abstract_request_body(entry)
        assert schema == {"url": "<url>"}


class TestAnalyze:
    def test_basic_analyze_single_entry(self, analyzer):
        entries = [
            make_entry(
                method="GET",
                url="https://api.example.com/v1/users/12345",
                request_headers={
                    "authorization": "Bearer token123",
                    "user-agent": "curl/7.68",
                },
                request_body=None,
                response_status=200,
                response_body='{"id": 12345, "name": "Alice"}',
            )
        ]
        endpoints = analyzer.analyze(entries)
        assert len(endpoints) == 1
        ep = endpoints[0]
        assert ep.method == "GET"
        assert "{id}" in ep.path_pattern
        assert ep.base_url == "https://api.example.com"
        assert ep.auth_type == "bearer"
        assert ep.status_code == 200
        assert ep.count == 1

    def test_analyze_merges_same_endpoint(self, analyzer):
        entries = [
            make_entry(
                method="GET",
                url="https://api.example.com/v1/users/12345",
                response_status=200,
            ),
            make_entry(
                method="GET",
                url="https://api.example.com/v1/users/67890",
                response_status=200,
            ),
        ]
        endpoints = analyzer.analyze(entries)
        assert len(endpoints) == 1
        assert endpoints[0].count == 2

    def test_analyze_separates_different_methods(self, analyzer):
        entries = [
            make_entry(method="GET", url="https://api.example.com/v1/users"),
            make_entry(method="POST", url="https://api.example.com/v1/users"),
        ]
        endpoints = analyzer.analyze(entries)
        assert len(endpoints) == 2
        methods = {ep.method for ep in endpoints}
        assert methods == {"GET", "POST"}

    def test_analyze_strips_noise_headers(self, analyzer):
        entries = [
            make_entry(
                url="https://api.example.com/v1/users",
                request_headers={
                    "authorization": "Bearer tok",
                    "user-agent": "curl",
                    "accept": "*/*",
                    "x-custom": "keep-me",
                },
            )
        ]
        endpoints = analyzer.analyze(entries)
        headers = endpoints[0].request_headers
        assert "user-agent" not in headers
        assert "accept" not in headers
        assert "x-custom" in headers
        # Authorization header should be masked
        assert headers.get("authorization") == "<TOKEN>"

    def test_analyze_uses_successful_response_as_sample(self, analyzer):
        entries = [
            make_entry(
                url="https://api.example.com/v1/users/1",
                response_status=500,
                response_body='{"error": "server error"}',
            ),
            make_entry(
                url="https://api.example.com/v1/users/2",
                response_status=200,
                response_body='{"id": 2, "name": "Bob"}',
            ),
        ]
        endpoints = analyzer.analyze(entries)
        assert endpoints[0].status_code == 200
        assert "Bob" in endpoints[0].response_body_sample

    def test_analyze_body_schema_populated(self, analyzer):
        entries = [
            make_entry(
                method="POST",
                url="https://api.example.com/v1/users",
                request_body='{"name": "Alice", "age": 30}',
                response_status=201,
            )
        ]
        endpoints = analyzer.analyze(entries)
        assert endpoints[0].request_body_schema is not None
        assert endpoints[0].request_body_schema["name"] == "<string>"
        assert endpoints[0].request_body_schema["age"] == "<integer>"
