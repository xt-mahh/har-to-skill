"""Tests for the Skill Generator module."""

import json
import re

import pytest
import yaml

from scripts.api_analyzer import ApiEndpoint


@pytest.fixture
def basic_endpoint():
    return ApiEndpoint(
        method="GET",
        path_pattern="/v1/users/{id}",
        base_url="https://api.example.com",
        request_headers={
            "authorization": "<TOKEN>",
            "content-type": "application/json",
        },
        auth_type="bearer",
        status_code=200,
        count=1,
    )


@pytest.fixture
def post_endpoint():
    return ApiEndpoint(
        method="POST",
        path_pattern="/v1/users",
        base_url="https://api.example.com",
        request_headers={
            "authorization": "<TOKEN>",
            "content-type": "application/json",
        },
        auth_type="bearer",
        request_body_example=json.dumps(
            {
                "name": "Alice",
                "email": "alice@example.com",
                "token": "cli_secret123",
            }
        ),
        status_code=201,
        count=3,
    )


@pytest.fixture
def api_key_endpoint():
    return ApiEndpoint(
        method="GET",
        path_pattern="/v2/contacts",
        base_url="https://api.other.com",
        request_headers={
            "x-api-key": "<API_KEY>",
            "accept": "application/json",
        },
        auth_type="apikey",
        status_code=200,
        count=1,
    )


@pytest.fixture
def generator():
    from scripts.skill_generator import SkillGenerator

    return SkillGenerator(
        har_filename="recording.har",
        timestamp="2025-01-15T10:00:00",
        service_name="test-service",
    )


class TestFrontmatter:
    def test_frontmatter_is_valid_yaml(self, generator, basic_endpoint):
        """Frontmatter YAML must be parseable."""
        frontmatter = generator._gen_frontmatter(
            [basic_endpoint], har_path="recording.har"
        )
        # Extract YAML between --- markers
        match = re.match(r"^---\n(.*?)\n---", frontmatter, re.DOTALL)
        assert match is not None, "Frontmatter must have --- delimiters"
        data = yaml.safe_load(match.group(1))
        assert data is not None, "Frontmatter must be valid YAML"
        assert data["name"] == "test-service"
        assert data["metadata"]["hermes"]["endpoint_count"] == 1
        assert "security_note" in data["metadata"]["hermes"]

    def test_frontmatter_includes_source_har(self, generator, basic_endpoint):
        """Frontmatter must include source HAR path."""
        frontmatter = generator._gen_frontmatter(
            [basic_endpoint], har_path="recordings/recording.har"
        )
        match = re.match(r"^---\n(.*?)\n---", frontmatter, re.DOTALL)
        data = yaml.safe_load(match.group(1))
        assert data["metadata"]["hermes"]["source_har"] == "recordings/recording.har"

    def test_frontmatter_with_multiple_endpoints(
        self, generator, basic_endpoint, post_endpoint
    ):
        """Frontmatter must reflect count of multiple endpoints."""
        frontmatter = generator._gen_frontmatter(
            [basic_endpoint, post_endpoint], har_path="recording.har"
        )
        match = re.match(r"^---\n(.*?)\n---", frontmatter, re.DOTALL)
        data = yaml.safe_load(match.group(1))
        assert data["metadata"]["hermes"]["endpoint_count"] == 2


class TestCurlGeneration:
    def test_body_contains_curl(self, generator, basic_endpoint):
        """Body must contain a curl command."""
        body = generator._gen_body([basic_endpoint])
        assert "curl -s -X GET" in body
        assert "api.example.com" in body
        assert "<TOKEN>" in body

    def test_curl_has_placeholder(self, generator, basic_endpoint):
        """URL params and auth tokens must be replaced with placeholders."""
        curl = generator._gen_curl(basic_endpoint)
        assert "<TOKEN>" in curl
        assert basic_endpoint.base_url in curl
        assert basic_endpoint.path_pattern in curl

    def test_curl_post_with_body(self, generator, post_endpoint):
        """POST curl must include -d with parameterized body."""
        curl = generator._gen_curl(post_endpoint)
        assert "-X POST" in curl
        assert "-d" in curl
        # The body should be parameterized (no raw values)
        assert "<SECRET>" in curl or "<string>" in curl

    def test_curl_api_key_auth(self, generator, api_key_endpoint):
        """API key endpoints should get Bearer placeholder in curl."""
        curl = generator._gen_curl(api_key_endpoint)
        assert "<TOKEN>" in curl


class TestAuthSection:
    def test_body_contains_auth_section(self, generator, basic_endpoint):
        """Body must contain an authentication section."""
        body = generator._gen_body([basic_endpoint])
        assert "## 认证" in body or "## 认证" in body
        # Should mention Bearer Token
        assert "Bearer" in body

    def test_auth_section_shows_api_key(self, generator, api_key_endpoint):
        """API Key auth type should appear in body."""
        body = generator._gen_body([api_key_endpoint])
        assert "API Key" in body or "API_KEY" in body


class TestParameterize:
    def test_parameterize_body_sensitive_values_replaced(self, generator):
        """Sensitive values in request body must be replaced."""
        body = json.dumps(
            {
                "name": "Alice",
                "token": "cli_secret123",
                "secret_key": "a" * 30,
                "age": 30,
            }
        )
        result = generator._parameterize_body(body)
        parsed = json.loads(result)
        assert parsed["name"] == "<string>"
        assert parsed["token"] == "<SECRET>"  # starts with cli_
        assert parsed["secret_key"] == "<SECRET>"  # length > 20
        assert parsed["age"] == 0  # numbers become 0

    def test_parameterize_body_non_json(self, generator):
        """Non-JSON body must be returned as-is."""
        result = generator._parameterize_body("not json")
        assert result == "not json"

    def test_parameterize_body_empty(self, generator):
        """Empty JSON body must be handled."""
        result = generator._parameterize_body("{}")
        assert json.loads(result) == {}


class TestInferDescription:
    def test_infer_user_endpoint(self, generator, basic_endpoint):
        """User-related endpoints must be detected."""
        desc = generator._infer_description(basic_endpoint)
        assert desc is not None
        assert "用户" in desc

    def test_infer_contact_endpoint(self, generator, api_key_endpoint):
        """Contact-related endpoints must be detected."""
        desc = generator._infer_description(api_key_endpoint)
        assert desc is not None
        assert "联系人" in desc

    def test_infer_unknown_endpoint(self, generator):
        """Unknown endpoints should return None."""
        ep = ApiEndpoint(
            method="GET",
            path_pattern="/v1/unknown-stuff/items",
            base_url="https://api.example.com",
        )
        desc = generator._infer_description(ep)
        assert desc is None

    def test_infer_by_method(self, generator):
        """Method type should reflect in description."""
        ep = ApiEndpoint(
            method="DELETE",
            path_pattern="/v1/users/{id}",
            base_url="https://api.example.com",
        )
        desc = generator._infer_description(ep)
        assert desc is not None
        assert "删除" in desc

    def test_infer_login_endpoint(self, generator):
        """Login/auth endpoints should be detected."""
        ep = ApiEndpoint(
            method="POST",
            path_pattern="/v1/auth/token",
            base_url="https://api.example.com",
        )
        desc = generator._infer_description(ep)
        assert desc is not None
        assert "登录" in desc or "认证" in desc


class TestGenerate:
    def test_generate_creates_output(self, generator, basic_endpoint, post_endpoint):
        """Full generate must produce complete SKILL.md output."""
        output = generator.generate(
            [basic_endpoint, post_endpoint], har_path="recording.har"
        )
        assert output.startswith("---")
        assert "test-service" in output
        assert "# test-service" in output
        assert "curl" in output
        assert "## 端点" in output
        assert "## ⚠️ 安全警告" in output
        assert "## 注意事项" in output
        assert "recording.har" in output

    def test_generate_with_empty_endpoints(self, generator):
        """Generate must handle empty endpoint list."""
        output = generator.generate([], har_path="recording.har")
        assert output.startswith("---")
        assert "0 个端点" in output
        assert "## 端点" in output

    def test_generate_no_auth(self, generator):
        """Endpoints without auth should not show auth section."""
        ep = ApiEndpoint(
            method="GET",
            path_pattern="/v1/public/info",
            base_url="https://api.example.com",
            request_headers={"content-type": "application/json"},
            auth_type=None,
            status_code=200,
        )
        output = generator.generate([ep], har_path="recording.har")
        # Should still work but no auth section
        assert "GET" in output
        # No auth type section
        assert "Bearer" not in output


class TestSecurityBanner:
    def test_security_warning_present(self, generator, basic_endpoint):
        """Security warning banner must be in output."""
        body = generator._gen_body([basic_endpoint])
        assert "⚠️" in body or "安全" in body

    def test_curl_token_placeholder(self, generator, basic_endpoint):
        """Curl must use <TOKEN> placeholder."""
        curl = generator._gen_curl(basic_endpoint)
        assert "<TOKEN>" in curl
        # No raw token values
        assert "Bearer " not in curl.replace("Bearer <TOKEN>", "")


class TestResponseBody:
    def test_response_sample_included(self, generator):
        """Response body sample must appear in output."""
        ep = ApiEndpoint(
            method="GET",
            path_pattern="/v1/users/me",
            base_url="https://api.example.com",
            request_headers={"authorization": "<TOKEN>"},
            auth_type="bearer",
            status_code=200,
            response_body_sample=json.dumps({"id": 1, "name": "Alice"}, indent=2),
        )
        body = generator._gen_body([ep])
        assert "响应示例" in body
        assert "Alice" in body

    def test_response_sample_truncated(self, generator):
        """Long response body must be truncated."""
        large_body = json.dumps({"data": "x" * 3000})
        ep = ApiEndpoint(
            method="GET",
            path_pattern="/v1/large",
            base_url="https://api.example.com",
            request_headers={"authorization": "<TOKEN>"},
            auth_type="bearer",
            status_code=200,
            response_body_sample=large_body,
        )
        body = generator._gen_body([ep])
        assert "... (截断)" in body or "truncated" in body
