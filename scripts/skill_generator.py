#!/usr/bin/env python3
"""Generate a Hermes SKILL.md from analyzed API endpoints."""

import json
import os
import re
from datetime import datetime

import yaml

from scripts.api_analyzer import ApiEndpoint


class SkillGenerator:
    def __init__(self, har_filename: str = "recording.har",
                 timestamp: str | None = None,
                 service_name: str | None = None):
        self.har_name = os.path.splitext(os.path.basename(har_filename))[0]
        self.timestamp = timestamp or datetime.now().isoformat()
        self.service_name = service_name or f"auto-{self.har_name}"

    def generate(self, endpoints: list[ApiEndpoint], har_path: str = "") -> str:
        return self._gen_frontmatter(endpoints, har_path) + "\n" + self._gen_body(endpoints)

    def _gen_frontmatter(self, endpoints, har_path) -> str:
        meta = {
            "name": self.service_name,
            "description": (
                f"由 HAR 文件「{self.har_name}.har」自动生成的 skill — "
                f"共 {len(endpoints)} 个端点。请替换占位符中的令牌和参数后使用。"
                f"\n\n⚠️ 安全提示：此文件由 HAR 自动生成，已脱敏认证凭据。"
                f"请勿将原始 HAR 文件或此 Skill 上传到公开仓库。"
            ),
            "version": "1.0.0",
            "author": "hermes-har-to-skill",
            "metadata": {
                "hermes": {
                    "tags": ["auto-generated", "api"],
                    "source_har": har_path or f"{self.har_name}.har",
                    "generated_at": self.timestamp,
                    "endpoint_count": len(endpoints),
                    "security_note": "tokens_redacted",
                }
            }
        }
        return f"---\n{yaml.dump(meta, default_flow_style=False, allow_unicode=True, sort_keys=False, indent=2)}---\n"

    def _gen_body(self, endpoints) -> str:
        lines = [f"# {self.service_name}\n"]
        lines.append(f"> 自动生成自: `{self.har_name}.har`（{self.timestamp}）\n")

        # 安全横幅
        lines.append("## ⚠️ 安全警告\n")
        lines.append("> 此 Skill 由浏览器录制的 HAR 文件自动生成。")
        lines.append("> **所有认证凭据已被自动替换为占位符 `<TOKEN>`。**")
        lines.append("> 请确认不包含敏感信息后再分享或上传。\n")

        # 认证概览
        auth_types = set(ep.auth_type for ep in endpoints if ep.auth_type)
        if auth_types:
            lines.append("## 认证\n")
            for at in sorted(auth_types):
                if at == "bearer":
                    lines.append("**方式:** Bearer Token（`Authorization: Bearer <TOKEN>`）\n")
                elif at == "apikey":
                    lines.append("**方式:** API Key（`X-API-Key: <API_KEY>`）\n")
                else:
                    lines.append(f"**方式:** {at}\n")
            lines.append("使用前请将 `<TOKEN>` 替换为你的实际凭证。\n")

        # 端点
        lines.append("## 端点\n")
        for i, ep in enumerate(endpoints, 1):
            lines.append(f"### {ep.method} {ep.path_pattern}\n")
            desc = self._infer_description(ep)
            if desc:
                lines.append(f"{desc}\n")
            lines.append(f"- 状态码: `{ep.status_code}`")
            if ep.count > 1:
                lines.append(f"- 录制中调用次数: {ep.count}")
            lines.append("")

            # curl 命令
            lines.append("```bash")
            lines.append(self._gen_curl(ep))
            lines.append("```\n")

            if ep.request_body_schema:
                lines.append("**请求体结构:**\n```json\n"
                            + json.dumps(ep.request_body_schema, ensure_ascii=False, indent=2)
                            + "\n```\n")

            if ep.response_body_sample:
                resp = ep.response_body_sample
                if len(resp) > 2000:
                    resp = resp[:2000] + "\n... (截断)"
                lines.append("**响应示例:**\n```json\n" + resp + "\n```\n")

            lines.append("---\n")

        lines.append("## 注意事项\n")
        lines.append("- 认证令牌已被替换为占位符，请更换为实际凭证后再使用")
        lines.append("- 路径中的参数占位符需要填入实际值")
        lines.append("- 部分请求头可能已过时，请以 API 文档为准")
        lines.append(f"- 此文件由 `{self.har_name}.har` 自动生成，如需更新请重新录制")
        lines.append("- 请勿将包含原始 Token 的 HAR 文件公开分享")
        return "\n".join(lines)

    def _gen_curl(self, ep: ApiEndpoint) -> str:
        url = ep.base_url + ep.path_pattern
        parts = [f"curl -s -X {ep.method} \"{url}\""]
        token_inserted = False
        for k, v in ep.request_headers.items():
            if k in ("authorization", "x-api-key"):
                if not token_inserted:
                    parts.append('  -H "Authorization: Bearer <TOKEN>"')
                    token_inserted = True
            elif k == "content-type":
                parts.append(f'  -H "Content-Type: {v}"')
            elif k != "content-length":
                parts.append(f'  -H "{k}: {v}"')
        if ep.request_body_example and ep.method in ("POST", "PUT", "PATCH"):
            body = self._parameterize_body(ep.request_body_example)
            parts.append(f"  -d '{body}'")
        return " \\\n".join(parts)

    def _parameterize_body(self, body: str) -> str:
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return body

        def walk(d):
            if isinstance(d, dict):
                return {k: walk(v) for k, v in d.items()}
            elif isinstance(d, list):
                return [walk(d[0])] if d else []
            elif isinstance(d, str):
                if re.match(r'^cli_', d) or len(d) > 20:
                    return "<SECRET>"
                return "<string>"
            elif isinstance(d, bool):
                return "<boolean>"
            elif isinstance(d, (int, float)):
                return 0
            return None
        return json.dumps(walk(data), ensure_ascii=False, indent=2)

    def _infer_description(self, ep: ApiEndpoint) -> str | None:
        path = ep.path_pattern.lower()
        method = ep.method.upper()
        patterns = [
            (r'/login|/auth|/token', '认证 / 登录'),
            (r'/user|/users|/member|/members', '用户管理'),
            (r'/contact|/contacts', '联系人管理'),
            (r'/message|/messages|/chat|/im', '消息 / 即时通讯'),
            (r'/file|/files|/upload|/download|/drive', '文件管理'),
            (r'/calendar|/event|/events', '日历 / 日程'),
            (r'/task|/tasks', '任务管理'),
            (r'/doc|/docs|/document|/documents|/wiki', '文档 / 知识库'),
            (r'/sheet|/sheets|/spreadsheet|/table|/base', '表格 / 多维表格'),
            (r'/search', '搜索'),
            (r'/notification|/notify', '通知'),
        ]
        method_map = {"GET": "查询", "POST": "创建", "PUT": "更新",
                     "PATCH": "部分更新", "DELETE": "删除"}
        for pat, desc in patterns:
            if re.search(pat, path):
                return f"{method_map.get(method, method)}{desc}"
        return None
