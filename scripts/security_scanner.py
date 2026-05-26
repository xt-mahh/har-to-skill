#!/usr/bin/env python3
"""Security scanner: sanitize HAR entries and validate generated output."""

import re
from urllib.parse import urlparse, parse_qs
from urllib.parse import urlencode

SENSITIVE_PATTERNS = {
    'jwt': re.compile(
        r'eyJ[A-Za-z0-9\-_]+\.eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+'),
    'bearer_token': re.compile(
        r'(?i)Bearer\s+[A-Za-z0-9\-_\.=]{20,}'),
    'api_key_in_url': re.compile(
        r'[?&](key|api_key|token|secret|access_token)=([A-Za-z0-9\-_%.]{8,})'),
    'app_secret': re.compile(
        r'(?i)(cli_|sk-|pk-|tk-)[A-Za-z0-9\-_]{8,}'),
    'session_cookie': re.compile(
        r'(?i)(session|sessionid|jwt|auth_token)=[A-Za-z0-9\-_%.]{8,}'),
    'phone_number': re.compile(r'\b1[3-9]\d{9}\b'),
    'id_card': re.compile(
        r'\b[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])'
        r'(0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b'),
    'internal_ip': re.compile(
        r'\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|'
        r'172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|'
        r'192\.168\.\d{1,3}\.\d{1,3})\b'),
}


class SecurityScanner:
    def __init__(self, strict: bool = True):
        self.strict = strict
        self.findings: list[dict] = []

    def scan_entry(self, entry) -> list[dict]:
        findings = []
        # 扫描 headers
        for key, value in entry.request_headers.items():
            for name, pat in SENSITIVE_PATTERNS.items():
                if pat.search(f"{key}: {value}"):
                    findings.append({
                        'type': name, 'location': f'request.headers.{key}',
                        'severity': 'critical',
                    })
        # 扫描 URL
        for name, pat in SENSITIVE_PATTERNS.items():
            if pat.search(entry.url):
                findings.append({
                    'type': name, 'location': 'request.url',
                    'severity': 'high',
                })
        # 扫描请求体
        if entry.request_body:
            for name, pat in SENSITIVE_PATTERNS.items():
                if pat.search(entry.request_body):
                    findings.append({
                        'type': name, 'location': 'request.body',
                        'severity': 'high',
                    })
        # 扫描响应体
        if entry.response_body:
            for name, pat in SENSITIVE_PATTERNS.items():
                if pat.search(entry.response_body):
                    findings.append({
                        'type': name, 'location': 'response.body',
                        'severity': 'medium',
                    })
        return findings

    def sanitize_headers(self, headers: dict) -> dict:
        cleaned = {}
        for k, v in headers.items():
            if k.lower() in ('authorization', 'x-api-key', 'x-tenant-key',
                             'x-auth-token', 'cookie', 'set-cookie'):
                cleaned[k] = '<REDACTED>'
            else:
                cleaned[k] = v
        return cleaned

    def sanitize_url(self, url: str) -> str:
        parsed = urlparse(url)
        sensitive_params = {'token', 'api_key', 'secret', 'access_token',
                            'refresh_token', 'key', 'sign', 'signature'}
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        safe_params = {k: v for k, v in query_params.items()
                       if k.lower() not in sensitive_params}
        if safe_params != query_params:
            new_qs = urlencode(safe_params, doseq=True)
            return parsed._replace(query=new_qs).geturl()
        return url

    def scan_output(self, skill_md: str) -> list[dict]:
        findings = []
        for name, pat in SENSITIVE_PATTERNS.items():
            matches = pat.findall(skill_md)
            if matches:
                findings.append({
                    'type': name, 'location': 'output.skill_md',
                    'severity': 'critical', 'count': len(matches),
                })
        return findings

    def report(self, findings: list[dict]) -> str:
        if not findings:
            return "✅ 安全检查通过，未发现敏感信息"
        lines = [f"⚠️  发现 {len(findings)} 个安全风险:\n"]
        for f in findings:
            icon = {"critical": "🔴", "high": "🟡", "medium": "🔵"}.get(
                f.get('severity', 'medium'), "🔵")
            lines.append(
                f"  {icon} [{f['severity'].upper()}] {f['type']} 位于 {f['location']}"
                + (f" (x{f['count']})" if 'count' in f else ""))
        lines.append("\n已自动脱敏处理，请确认后使用")
        return "\n".join(lines)
