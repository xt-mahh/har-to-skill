---
name: har-to-skill
description: "从浏览器录制的 HAR 文件自动生成 Hermes Skill。录制 → 导出 → 自动生成可复用的 SKILL.md + curl 命令。"
version: 1.0.0 
author: hermes-agent
metadata:
  hermes:
    tags: [meta-skill, har, api, code-generation, automation]
    related_skills: [skill-creator, hermes-agent-skill-authoring]
---

# HAR-to-Skill 元技能

## 用途

把浏览器 DevTools 中录制的网络请求导出为 HAR 文件后,智能分析推测api功能，自动逆向工程为可直接复用的 Hermes Skill。

## 工作流

1. 在浏览器 DevTools → Network 面板录制操作
2. 右键 → "Save all as HAR" 导出为 `.har` 文件
3. 运行 `python -m har_to_skill /path/to/recording.har`
4. 获得包含 curl 命令的 SKILL.md

## 使用方法

### 方式一：通过 Hermes 交互式调用

> "解析 `/path/to/capture.har`，生成一个飞书通讯录 API 的 skill"

### 方式二：Python CLI

```bash
# 安装依赖
pip install pyyaml

# 直接生成到 stdout
python -m har_to_skill /path/to/capture.har --name my-api-skill

# 保存到文件
python -m har_to_skill /path/to/capture.har --name my-api-skill --output ./my-skill/SKILL.md

# 直接安装为 Hermes Skill
python -m har_to_skill /path/to/capture.har --name my-api-skill --install

# 只提取特定服务的端点
python -m har_to_skill /path/to/capture.har --service open.feishu.cn
```

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `har_path` | HAR 文件路径 | 必填 |
| `--name` | 生成的 skill 名称 | `auto-<har文件名>` |
| `--output` | 输出文件路径 | stdout |
| `--install` | 安装到 ~/.hermes/skills/ | false |
| `--service` | 只提取指定域名的端点 | 全部 |

## 输出格式

生成的 SKILL.md 包含：

- **YAML frontmatter** — 名称、描述、版本、来源 HAR 信息
- **安全横幅** — 提醒脱敏处理和注意事项
- **认证概览** — 检测到的认证方式（Bearer / API Key）
- **端点列表** — 每个端点有参数化的 curl 命令 + 请求体结构 + 响应示例

## 安全特性

- 所有 `Authorization: Bearer xxx`、`X-API-Key: xxx` 自动替换为 `<TOKEN>`
- 请求体中的敏感值（app_secret、token 等）替换为占位符
- URL query 中的敏感参数（`?token=`、`?api_key=`）自动清理
- 输出前二次扫描验证，发现残留凭据将中断输出

---

## 🤖 Agent 智能生成指南（核心逻辑）

当你（作为Agent）解析 HAR 文件生成 SKILL.md 时，按照以下规则智能推测内容，而非硬编码实现：

### 1. 服务类型检测（根据域名）
优先根据请求域名识别服务类型：
| 域名匹配 | 服务名称 | 预设标签 |
|----------|----------|----------|
| `feishu.cn` / `larksuite.com` | 飞书开放平台 | `["飞书", "企业协作", "开放API"]` |
| `dingtalk.com` | 钉钉开放平台 | `["钉钉", "阿里生态", "企业办公"]` |
| `weixin.qq.com` | 企业微信开放平台 | `["企业微信", "腾讯生态", "办公API"]` |
| `slack.com` | Slack | `["Slack", "团队沟通"]` |
| `github.com` | GitHub | `["GitHub", "代码托管"]` |
| `notion.so` | Notion | `["Notion", "知识库"]` |
| `aliyun.com` / `aliyuncs.com` | 阿里云 | `["阿里云", "云服务"]` |
| 其他通用域名 | 对应服务名称 | `["API", "auto-generated"]` |

### 2. Frontmatter 生成规则
```yaml
name: "{服务名称} Skill"
description: |
  {服务名称} API 自动化 Skill，用于构建 {服务名称} 工作流。包括{服务标签1}、{服务标签2}等功能。
version: "1.0.0"
metadata:
  hermes:
    tags: ["{服务名称}" ,"{服务标签1}", "{服务标签2}", ...]
    service_type: "{服务名称}"
    source_har: "{HAR文件名}"
    endpoint_count: {n}
    auth_types: ["{认证类型列表}"]
    security_note: "tokens_redacted"
```

### 3. API 端点功能推测规则
根据请求方法 + 路径关键词智能生成功能描述：

| 方法 | 路径关键词 | 功能描述示例 |
|------|------------|--------------|
| GET | `/login` `/auth` `/token` | 获取访问凭证 |
| GET | `/user/me` `/user/info` | 获取当前用户信息 |
| GET | `/list` `/users` `/files` | 查询{资源名称}列表 |
| GET | `/get` `/detail` `/\{id\}` | 查询{资源名称}详情 |
| POST | `/create` `/add` `/send` | 创建/发送{资源名称} |
| POST/PUT | `/update` `/edit` | 更新{资源名称}信息 |
| DELETE | `/delete` `/remove` | 删除{资源名称}资源 |
| POST | `/upload` | 上传{资源名称} |
| GET | `/download` | 下载{资源名称} |
| * | `/search` | 搜索{资源名称} |
| * | `/notification` `/notify` | 发送通知 |

通用 fallback 规则：
- GET 请求：`查询{路径最后一段}信息`
- POST 请求：`创建{路径最后一段}资源`
- PUT/PATCH 请求：`更新{路径最后一段}信息`
- DELETE 请求：`删除{路径最后一段}资源`

### 4. 输出内容结构
每个端点必须包含：
```markdown
### {方法} {路径模式}
{智能推测的功能描述}
- 状态码: `{实际状态码}`
- 调用次数: {录制中出现的次数（可选）}

```bash
{参数化的 curl 命令，所有token替换为<TOKEN>，敏感参数替换为占位符}
```

**请求体结构:**
```json
{参数化的请求体结构，值替换为<STRING>/<NUMBER>/<BOOLEAN>等类型占位符}
```

**响应示例:**
```json
{响应内容示例，过长时截断}
```
---
```

## 注意事项

- **HAR 文件可能包含敏感信息**，不要在他人设备上操作
- 生成的 Skill 中所有认证凭据已被脱敏，使用前请填入实际凭证
- 路径中的数字/UUID等被泛化为 `{id}`、`{uuid}` 等占位符
- 首次使用建议先用 GET 请求测试连通性
- 同一个 HAR 可以反复调整参数重新生成

## 示例

```bash
$ python -m har_to_skill tests/fixtures/simple-api.har --name example-api

  ── 总请求: 3 | API 请求: 1
  ── 识别到 1 个独立端点
     GET /open-apis/contact/v3/users/{id}  [bearer]

╔══════════════════════════════════════════════════╗
║  ⚠️  安全检查                                      ║
║  已自动脱敏所有认证凭据                             ║
║  请确认输出不包含敏感信息再分享                     ║
╚══════════════════════════════════════════════════╝

# ... 生成的 SKILL.md 内容 ...
```
