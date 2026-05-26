# har-to-skill

将 HAR (HTTP Archive) 文件自动转换为 Hermes Skill 的工具。自动识别API端点、脱敏敏感数据、生成可直接使用的技能文件。

## ✨ 功能特性

- 🚀 **全自动转换**：一键将HAR文件转换为完整的Hermes Skill
- 🔒 **自动脱敏**：自动识别并移除敏感数据（令牌、密钥、手机号、内部IP等）
- 🧠 **智能API识别**：自动聚类相同端点、识别路径参数、提取请求/响应Schema
- 🛡️ **安全扫描**：多层安全检查，确保输出不包含敏感信息
- 📝 **生成完整Skill**：包含YAML元数据、认证说明、curl调用示例、端点功能描述
- 🔍 **灵活过滤**：支持按域名过滤API，只生成指定服务的Skill
- ⚡ **噪音过滤**：自动过滤图片、静态资源、跟踪脚本等非API请求

## 📦 安装

### 从源码安装
```bash
git clone https://github.com/your-username/har-to-skill.git
cd har-to-skill
pip install -e .
```

## 🚀 快速开始

### 基本使用
```bash
har-to-skill your-recording.har --name "My API Skill"
```

### 指定输出文件
```bash
har-to-skill your-recording.har --name "飞书联系人Skill" --output feishu-skill.md
```

### 仅处理指定域名
```bash
har-to-skill your-recording.har --service open.feishu.cn --name "飞书Skill"
```

### 宽松模式（仅警告敏感数据，不中断）
```bash
har-to-skill your-recording.har --no-strict --name "测试Skill"
```

### 安装到Hermes技能目录
```bash
har-to-skill your-recording.har --name "My Skill" --install
```

## 📖 命令行参数

| 参数 | 说明 |
|------|------|
| `har_path` | HAR文件路径（必填） |
| `--name` | 生成的Skill名称 |
| `--output` | 输出文件路径（默认输出到stdout） |
| `--install` | 安装到 `~/.hermes/skills/` 目录 |
| `--service` | 仅处理指定域名的API |
| `--strict` | 严格模式：发现敏感数据暂停并确认（默认开启） |
| `--no-strict` | 宽松模式：仅警告，不中断 |
| `--keep-auth` | 保留认证令牌原文（危险！仅调试用） |

## 🔒 安全特性

- 自动识别并脱敏：
  - Bearer Token/JWT
  - API Key/密钥
  - 手机号/身份证号
  - 内部IP地址
  - 查询参数中的敏感信息
- 多层安全扫描：输入扫描 + 输出二次校验
- 默认严格模式，发现关键风险自动中止
- 所有生成的curl命令使用占位符代替真实凭证

## 🛠️ 开发指南

### 环境搭建
```bash
pip install -r requirements.txt
pip install pytest pytest-cov
```

### 运行测试
```bash
# 运行所有测试
pytest tests/ -v

# 生成覆盖率报告
pytest tests/ --cov=scripts --cov-report=html
```

### 项目结构
```
har-to-skill/
├── __main__.py              # CLI入口
├── scripts/
│   ├── har_parser.py        # HAR文件解析和噪音过滤
│   ├── api_analyzer.py      # API端点分析和聚类
│   ├── security_scanner.py  # 敏感数据扫描和脱敏
│   └── skill_generator.py   # Hermes Skill文件生成
├── tests/
│   ├── fixtures/            # 测试用HAR文件
│   └── test_*.py            # 单元测试和集成测试
└── pyproject.toml           # 项目配置
```

## 🤝 贡献

欢迎提交Issue和Pull Request！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解贡献指南。

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件。