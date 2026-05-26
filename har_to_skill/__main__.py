#!/usr/bin/env python3
"""CLI: python -m har_to_skill recording.har"""

import argparse
import sys
from pathlib import Path

# Ensure the package root is on sys.path (supports both direct run and -m)
_pkg_root = str(Path(__file__).resolve().parent)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from scripts.har_parser import HarParser
from scripts.api_analyzer import ApiAnalyzer
from scripts.skill_generator import SkillGenerator
from scripts.security_scanner import SecurityScanner


def main():
    parser = argparse.ArgumentParser(description="将 HAR 文件转换为 Hermes Skill")
    parser.add_argument("har_path", help="HAR 文件路径")
    parser.add_argument("--name", help="生成的 skill 名称")
    parser.add_argument("--output", help="输出文件路径（默认 stdout）")
    parser.add_argument("--install", action="store_true",
                        help="安装到 ~/.hermes/skills/")
    parser.add_argument("--service", help="仅处理指定域名")

    parser.add_argument("--strict", action="store_true", default=True,
                        help="严格模式：发现敏感数据暂停并确认（默认开启）")
    parser.add_argument("--no-strict", action="store_false", dest="strict",
                        help="宽松模式：仅警告，不中断")
    parser.add_argument("--keep-auth", action="store_true",
                        help="保留认证令牌原文（危险！仅调试用）")
    args = parser.parse_args()

    har_parser = HarParser()
    all_entries = har_parser.parse(args.har_path)
    api_entries = har_parser.filter_api_calls(all_entries)

    print(f"  ── 总请求: {len(all_entries)} | API 请求: {len(api_entries)}",
          file=sys.stderr)

    if not api_entries:
        print("⚠️  未检测到 API 调用，请检查 HAR 文件", file=sys.stderr)
        sys.exit(1)

    scanner = SecurityScanner(strict=args.strict)
    entry_findings = []
    for e in api_entries:
        entry_findings.extend(scanner.scan_entry(e))
    if entry_findings:
        print(scanner.report(entry_findings), file=sys.stderr)
        critical_count = sum(1 for f in entry_findings if f['severity'] == 'critical')
        if critical_count > 0 and args.strict:
            print(f"  ⛔ 发现 {critical_count} 个关键风险，已自动脱敏", file=sys.stderr)

    analyzer = ApiAnalyzer()
    if args.service:
        groups = analyzer.cluster_by_service(api_entries)
        api_entries = [e for k, g in groups.items()
                      for e in g if args.service in k]
        print(f"  ── 按服务「{args.service}」过滤后: {len(api_entries)} 个请求",
              file=sys.stderr)

    endpoints = analyzer.analyze(api_entries)
    print(f"  ── 识别到 {len(endpoints)} 个独立端点", file=sys.stderr)
    for ep in endpoints:
        print(f"     {ep.method} {ep.path_pattern}  [{ep.auth_type or 'no auth'}]",
              file=sys.stderr)

    generator = SkillGenerator(
        har_filename=args.har_path, service_name=args.name)
    result = generator.generate(endpoints, args.har_path)

    output_findings = scanner.scan_output(result)
    if output_findings and args.strict:
        print(f"  ⛔ 输出中仍发现 {len(output_findings)} 个敏感项！中止输出！",
              file=sys.stderr)
        for f in output_findings:
            print(f"     {f['type']} (x{f.get('count', 1)})", file=sys.stderr)
        sys.exit(1)

    if args.install:
        install_path = (Path.home() / ".hermes" / "skills" /
                       (args.name or "auto-skill"))
        install_path.mkdir(parents=True, exist_ok=True)
        skill_path = install_path / "SKILL.md"
        skill_path.write_text(result, encoding="utf-8")
        print(f"  ✅ 已安装到: {skill_path}", file=sys.stderr)
    elif args.output:
        Path(args.output).write_text(result, encoding="utf-8")
        print(f"  ✅ 已写入: {args.output}", file=sys.stderr)
    else:
        print("\n" + "╔" + "═" * 50 + "╗", file=sys.stderr)
        print("║  ⚠️  安全检查                                      ║", file=sys.stderr)
        print("║  已自动脱敏所有认证凭据                             ║", file=sys.stderr)
        print("║  请确认输出不包含敏感信息再分享                     ║", file=sys.stderr)
        print("╚" + "═" * 50 + "╝\n", file=sys.stderr)
        print(result)


if __name__ == "__main__":
    main()
