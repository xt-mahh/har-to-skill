#!/usr/bin/env python3
"""Analyze HAR entries to extract API patterns, endpoints, and auth."""

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlparse

from scripts.har_parser import HarEntry


@dataclass
class ApiEndpoint:
    method: str
    path_pattern: str
    base_url: str
    request_headers: dict = field(default_factory=dict)
    auth_type: str | None = None
    request_body_example: str | None = None
    request_body_schema: dict | None = None
    response_body_sample: str | None = None
    status_code: int = 200
    count: int = 1


class ApiAnalyzer:
    PARAM_PATTERNS = [
        (r"^\d+$", "{id}"),
        (r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", "{uuid}"),
        (r"^[0-9a-f]{32}$", "{hash}"),
        (r"^[0-9a-f]{40}$", "{hash}"),
        (r"^[A-Za-z0-9_-]{20,}$", "{token}"),
        (r"^\d{4}-\d{2}-\d{2}", "{date}"),
        (r"^\d{4}\d{2}\d{2}$", "{date}"),
    ]

    AUTH_HEADERS = {
        "authorization": {"pattern": r"^Bearer\s+(\S+)", "type": "bearer"},
        "x-api-key": {"pattern": r"^(\S+)$", "type": "apikey"},
        "x-tenant-key": {"pattern": r"^(\S+)$", "type": "tenant"},
    }

    def cluster_by_service(self, entries: list[HarEntry]) -> dict[str, list[HarEntry]]:
        groups = defaultdict(list)
        for e in entries:
            parsed = urlparse(e.url)
            key = f"{parsed.scheme}://{parsed.netloc}/{parsed.path.split('/')[1] if parsed.path.strip('/') else ''}"
            groups[key].append(e)
        return dict(groups)

    def extract_path_pattern(self, urls: list[str]) -> tuple[str, str, str]:
        if not urls:
            return ("", "", "")
        if len(urls) == 1:
            parsed = urlparse(urls[0])
            path = self._parameterize_segments(parsed.path)
            return (f"{parsed.scheme}://{parsed.netloc}", path, urls[0])
        parsed_all = [urlparse(u) for u in urls]
        base = f"{parsed_all[0].scheme}://{parsed_all[0].netloc}"
        segments_list = [p.path.strip("/").split("/") for p in parsed_all]
        max_len = max(len(s) for s in segments_list)
        paths = []
        for i in range(max_len):
            segs_at_i = [s[i] if i < len(s) else "" for s in segments_list]
            unique = set(segs_at_i)
            if len(unique) == 1:
                paths.append(segs_at_i[0])
            else:
                param_candidates = [self._try_parameterize(s) for s in unique]
                param_set = set(p for p in param_candidates if p)
                if len(param_set) == 1:
                    paths.append(param_set.pop())
                else:
                    paths.append(f"{{param_{i}}}")
        return (base, "/" + "/".join(paths), urls[0])

    def _parameterize_segments(self, path: str) -> str:
        parts = path.strip("/").split("/")
        result = []
        for part in parts:
            p = self._try_parameterize(part)
            result.append(p if p else part)
        return "/" + "/".join(result)

    def _try_parameterize(self, segment: str) -> str | None:
        for pattern, placeholder in self.PARAM_PATTERNS:
            if re.match(pattern, segment):
                return placeholder
        return None

    def detect_auth(self, entries: list[HarEntry]) -> tuple[str | None, str | None]:
        for header_name, config in self.AUTH_HEADERS.items():
            for e in entries:
                val = e.request_headers.get(header_name)
                if val and re.match(config["pattern"], val):
                    return (config["type"], f"{config['type'].upper()} <TOKEN>")
        return (None, None)

    def abstract_request_body(self, entry: HarEntry) -> dict | None:
        if not entry.request_body:
            return None
        try:
            data = json.loads(entry.request_body)
            return self._type_schema(data)
        except json.JSONDecodeError:
            return None

    def _type_schema(self, data):
        if isinstance(data, dict):
            return {k: self._type_schema(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._type_schema(data[0])] if data else []
        elif isinstance(data, bool):
            return "<boolean>"
        elif isinstance(data, int):
            return "<integer>"
        elif isinstance(data, float):
            return "<number>"
        elif isinstance(data, str):
            if re.match(r"^cli_", data):
                return "<app_id>"
            if re.match(r"^t-", data):
                return "<token>"
            if len(data) > 30:
                return "<secret>"
            if data.startswith("http"):
                return "<url>"
            return "<string>"
        return "<unknown>"

    def analyze(self, entries: list[HarEntry]) -> list[ApiEndpoint]:
        groups = defaultdict(list)
        for e in entries:
            parsed = urlparse(e.url)
            groups[(e.method, parsed.netloc)].append(e)

        endpoints = []
        for (method, netloc), group in groups.items():
            urls = [e.url for e in group]
            base_url, path_pattern, _ = self.extract_path_pattern(urls)
            latest = group[-1]
            successful = next(
                (e for e in group if 200 <= e.response_status < 300), latest
            )
            auth_type, _ = self.detect_auth(group)
            clean_headers = {
                k: ("<TOKEN>" if k in self.AUTH_HEADERS else v)
                for k, v in successful.request_headers.items()
                if k
                not in (
                    "user-agent",
                    "accept",
                    "accept-encoding",
                    "accept-language",
                    "cache-control",
                    "pragma",
                    "sec-fetch-*",
                    "upgrade-insecure-requests",
                )
            }
            body_schema = self.abstract_request_body(successful)
            ep = ApiEndpoint(
                method=method,
                path_pattern=path_pattern,
                base_url=base_url,
                request_headers=clean_headers,
                auth_type=auth_type,
                request_body_example=successful.request_body,
                request_body_schema=body_schema,
                response_body_sample=successful.response_body,
                status_code=successful.response_status,
                count=len(group),
            )
            endpoints.append(ep)

        merged = {}
        for ep in endpoints:
            key = (ep.method, ep.path_pattern)
            if key in merged:
                merged[key].count += ep.count
                merged[key].response_body_sample = (
                    ep.response_body_sample or merged[key].response_body_sample
                )
            else:
                merged[key] = ep
        return list(merged.values())
