---
name: 302ai-search
description: 使用 302.AI 通用搜索 API 进行网络搜索。当需要获取实时信息、新闻、网页内容时使用，支持多种搜索引擎供应商。需要配置 AI302_API_KEY。
metadata:
  { "openclaw": { "primaryEnv": "AI302_API_KEY", "requires": { "env": ["AI302_API_KEY"] } } }
---

# 302 Search

使用 302.AI 通用搜索 API 进行网络搜索，支持多种搜索引擎供应商。

## 前置要求

1. **302.AI API Key**：需要在 https://302.ai 注册并获取 API Key
2. **账户余额**：确保账户有足够余额用于搜索调用
3. **Python 环境**：Python 3.8+ 和 `requests` Python 包

## 安装依赖

Skill 需要 `requests` Python 包。安装方式：

```bash
pip3 install requests
```

或者使用虚拟环境（推荐）：

```bash
python3 -m venv ~/skills/302ai-search/venv
source ~/skills/302ai-search/venv/bin/activate  # Linux/macOS
# 或
~/skills/302ai-search/venv/Scripts/activate  # Windows

pip install requests
```

## 配置 API Key

### 工作原理

本 skill 声明了 `primaryEnv: AI302_API_KEY`。OpenClaw 会自动将你配置的 `apiKey` 值注入到 `AI302_API_KEY` 环境变量中供脚本读取。

### 配置方式（推荐）

编辑 `~/.openclaw/openclaw.json`，添加：

```json
{
	"skills": {
		"entries": {
			"302ai-search": {
				"enabled": true,
				"apiKey": "sk-你的APIKey"
			}
		}
	}
}
```

### 使配置生效

```bash
openclaw gateway restart
```

## 使用方法

### 作为 Agent 工具使用

配置完成后，可以直接问 Agent：

> "用 302ai-search 搜一下今天的新闻"

### 直接调用脚本

```bash
# 基本用法
/skills/302ai-search/scripts/302ai-search.py "搜索关键词"

# 指定结果数量
~/skills/302ai-search/scripts/302ai-search.py "AI trends" --count 10

# 指定搜索引擎
~/skills/302ai-search/scripts/302ai-search.py "最新技术" --provider exa

# 时效性过滤
~/skills/302ai-search/scripts/302ai-search.py "今日新闻" --freshness day

# 输出原始JSON响应
~/skills/302ai-search/scripts/302ai-search.py "搜索词" --json
```

### 命令行参数

| 参数          | 简写 | 说明                        | 默认值 |
| ------------- | ---- | --------------------------- | ------ |
| `query`       | -    | 搜索关键词（必需）          | -      |
| `--count`     | `-c` | 返回结果数量                | 5      |
| `--provider`  | `-p` | 搜索供应商                  | tavily |
| `--freshness` | `-f` | 时效性过滤 (day/week/month) | -      |
| `--json`      | `-j` | 输出原始JSON响应            | false  |

## 输出格式

### 标准输出格式

脚本返回 JSON 格式：

```json
{
	"query": "搜索关键词",
	"count": 5,
	"provider": "tavily",
	"results": [
		{
			"title": "标题",
			"url": "https://...",
			"snippet": "摘要内容",
			"content": "完整网页内容",
			"published_at": "2024-01-01",
			"images": []
		}
	],
	"images": ["https://..."]
}
```

- `query`：原始搜索词
- `count`：返回结果数量
- `provider`：使用的搜索引擎
- `results`：搜索结果列表
  - `title`：网页标题
  - `url`：网页链接
  - `snippet`：内容摘要
  - `content`：完整网页内容（如有）
  - `published_at`：发布日期（如有）
  - `images`：相关图片（如有）
- `images`：搜索结果中的图片列表

### 原始 JSON 输出（--json）

使用 `--json` 参数可获取 302 API 的原始响应，包含更多字段如 `data` 等。

## 支持的供应商

| 供应商       | provider 值      | 说明                       |
| ------------ | ---------------- | -------------------------- |
| Tavily       | `tavily`         | 默认供应商，高质量搜索结果 |
| Search1      | `search1_search` | Search1 搜索               |
| Search1 News | `search1_news`   | Search1 新闻搜索           |
| Bocha        | `bocha`          | 博查搜索                   |
| Exa          | `exa`            | Exa AI 搜索                |
| Firecrawl    | `firecrawl`      | Firecrawl 搜索             |
| Metaso       | `metaso`         | 秘塔搜索                   |
| Perplexity   | `perplexity`     | Perplexity 搜索            |

## API 参考

- **端点**：`POST https://api.302.ai/302/general/search`
- **认证**：`Authorization: Bearer {{API_KEY}}`
- **Content-Type**：`application/json`

### 请求参数

```json
{
	"query": "Tesla",
	"provider": "tavily",
	"max_results": 6
}
```
