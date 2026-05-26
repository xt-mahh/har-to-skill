#!/usr/bin/env python3
"""Parse HAR files and extract API call entries, filtering out noise."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


NOISE_DOMAINS = {
    "google-analytics.com", "doubleclick.net", "googletagmanager.com",
    "sentry.io", "amplitude.com", "mixpanel.com", "facebook.net",
    "facebook.com/tr", "hotjar.com", "fullstory.com", "segment.io",
    "segment.com", "cdn.jsdelivr.net", "cdnjs.cloudflare.com",
    "fonts.googleapis.com", "fonts.gstatic.com",
}

NOISE_URL_FRAGMENTS = {
    "/analytics/", "/collect", "/beacon", "/ping",
    ".js", ".css", ".png", ".jpg", ".jpeg", ".gif",
    ".svg", ".woff", ".woff2", ".ico", ".webp",
    ".mp4", ".mp3", ".m3u8", ".ts",
}

API_CONTENT_TYPES = {
    "application/json", "application/xml", "text/xml",
    "application/x-www-form-urlencoded", "multipart/form-data",
    "text/plain", "application/grpc", "application/x-protobuf",
    "application/octet-stream",
}


@dataclass
class HarEntry:
    method: str = "GET"
    url: str = ""
    request_headers: dict[str, str] = field(default_factory=dict)
    request_body: str | None = None
    response_status: int = 0
    response_headers: dict[str, str] = field(default_factory=dict)
    response_body: str | None = None
    timestamp: str = ""


class HarParser:
    def parse(self, har_path: str) -> list[HarEntry]:
        with open(har_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        entries = []
        for e in raw.get("log", {}).get("entries", []):
            req = e.get("request", {})
            res = e.get("response", {})
            entry = HarEntry(
                method=req.get("method", "GET"),
                url=req.get("url", ""),
                request_headers={
                    h["name"].lower(): h["value"]
                    for h in req.get("headers", [])
                },
                request_body=self._extract_body(req.get("postData")),
                response_status=res.get("status", 0),
                response_headers={
                    h["name"].lower(): h["value"]
                    for h in res.get("headers", [])
                },
                response_body=self._extract_body(res.get("content")),
                timestamp=e.get("startedDateTime", ""),
            )
            entries.append(entry)
        return entries

    def _extract_body(self, data: dict | None) -> str | None:
        if not data:
            return None
        text = data.get("text")
        if text:
            try:
                return json.dumps(json.loads(text), ensure_ascii=False, indent=2)
            except (json.JSONDecodeError, TypeError):
                return text
        return None

    def filter_api_calls(self, entries: list[HarEntry]) -> list[HarEntry]:
        return [e for e in entries if self._is_api_call(e)]

    def _is_api_call(self, entry: HarEntry) -> bool:
        if entry.method in ("OPTIONS", "CONNECT"):
            return False
        url_lower = entry.url.lower()
        for domain in NOISE_DOMAINS:
            if domain in url_lower:
                return False
        is_api_path = bool(
            re.search(
                r"/api/|/v\d+/|/open-apis/|/graphql|/rest/|/services/",
                url_lower,
            )
        )
        for frag in NOISE_URL_FRAGMENTS:
            if frag in url_lower and not is_api_path:
                return False
        content_type = (
            entry.response_headers.get("content-type", "")
            or entry.request_headers.get("content-type", "")
        )
        for ct in API_CONTENT_TYPES:
            if ct in content_type:
                return True
        if is_api_path:
            return True
        if entry.method in ("POST", "PUT", "PATCH", "DELETE") and entry.request_body:
            return True
        if entry.response_body:
            try:
                json.loads(entry.response_body)
                return True
            except json.JSONDecodeError:
                pass
        return False
