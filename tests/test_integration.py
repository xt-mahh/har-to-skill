"""Integration tests: run the full HAR→Skill pipeline."""

import json, sys, os
from pathlib import Path

# 确保项目在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.har_parser import HarParser
from scripts.api_analyzer import ApiAnalyzer
from scripts.skill_generator import SkillGenerator

FIXTURES = Path(__file__).parent / "fixtures"


def _run_pipeline(har_path: str) -> str:
    parser = HarParser()
    entries = parser.parse(har_path)
    api_entries = parser.filter_api_calls(entries)

    analyzer = ApiAnalyzer()
    endpoints = analyzer.analyze(api_entries)

    generator = SkillGenerator(har_filename=har_path)
    return generator.generate(endpoints, har_path)


def test_simple_har_pipeline():
    """完整流水线：simple-api.har → 生成 skill"""
    output = _run_pipeline(str(FIXTURES / "simple-api.har"))
    assert "---" in output
    assert "curl" in output
    assert "open.feishu.cn" in output


def test_generated_frontmatter_is_valid_yaml():
    """frontmatter YAML 合法"""
    import yaml

    output = _run_pipeline(str(FIXTURES / "simple-api.har"))
    _, front, _ = output.split("---", 2)
    meta = yaml.safe_load(front)
    assert "name" in meta
    assert "version" in meta
    assert "description" in meta


def test_tokens_not_in_output():
    """HAR 中的真实 token 不出现在输出中"""
    output = _run_pipeline(str(FIXTURES / "simple-api.har"))
    # simple-api.har 中的 token 是 fake_token_xxx
    assert "fake_token_xxx" not in output


def test_noise_filter_completely():
    """噪音 HAR 经过解析后 API 为 0"""
    parser = HarParser()
    entries = parser.parse(str(FIXTURES / "noise-filter.har"))
    api_entries = parser.filter_api_calls(entries)
    assert len(api_entries) == 0


def test_lark_api_generated():
    """飞书 API HAR 生成后应包含正确的端点"""
    output = _run_pipeline(str(FIXTURES / "lark-api.har"))
    assert "POST" in output or "GET" in output
    assert "/open-apis/contact/v3" in output or "/open-apis/auth/v3" in output


def test_multiple_endpoints():
    """多端点 HAR 应合并相同路径模式、保留不同方法"""
    output = _run_pipeline(str(FIXTURES / "multiple-endpoints.har"))
    assert "GET" in output
    assert "POST" in output
    assert "/api/v1/users/{id}" in output or "/api/v1/users" in output


def test_lark_has_curl_command():
    """飞书场景的 curl 命令应参数化"""
    output = _run_pipeline(str(FIXTURES / "lark-api.har"))
    assert "curl" in output
    assert "<TOKEN>" in output or "<" in output


def test_cli_invocation():
    """CLI 入口应正常工作"""
    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "har_to_skill",
            "tests/fixtures/simple-api.har",
            "--name",
            "test-cli",
        ],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    assert result.returncode == 0
    assert "---" in result.stdout
    assert "curl" in result.stdout
    assert "test-cli" in result.stdout
