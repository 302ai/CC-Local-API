---
name: 302ai-search
description: Use the 302.AI Universal Search API for web searches. It is used when you need to get real-time information, news, web content, and supports a variety of search engine providers (such as Tavily, Exa, Metaso, etc.). Configuration AI302_API_KEY is required.
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

> "用 302ai-search 搜一下今天的新闻，供应商用 search1_news"
> "帮我用 metaso 搜索学术论文，只看第一页"

### 直接调用脚本

```bash
# 基本用法
python3 ~/skills/302ai-search/scripts/302ai-search.py "搜索关键词"

# 指定结果数量和搜索引擎
python3 ~/skills/302ai-search/scripts/302ai-search.py "AI trends" --count 10 --provider tavily

# 指定特定的分类搜索 (如寻找指定分类的公司)
python3 ~/skills/302ai-search/scripts/302ai-search.py "AI公司" --provider exa --category company

# 域名过滤
python3 ~/skills/302ai-search/scripts/302ai-search.py "技术文章" --include-domains example.com,techblog.com

# 学术搜索并分页
python3 ~/skills/302ai-search/scripts/302ai-search.py "大模型进展" --provider metaso --category scholar --page 1

# 指定时间范围
python3 ~/skills/302ai-search/scripts/302ai-search.py "今日新闻" --time-range day

# 排除图片
python3 ~/skills/302ai-search/scripts/302ai-search.py "搜索词" --no-images

# 输出原始JSON响应
python3 ~/skills/302ai-search/scripts/302ai-search.py "搜索词" --json
```

### 命令行参数

| 参数                        | 简写 | 说明                                                         | 默认值 |
| ------------------------- | ---- | ------------------------------------------------------------ | ------ |
| `query`                   | -    | 搜索关键词（必需）                                           | -      |
| `--count`                 | `-c` | 返回结果数量                                                 | 5      |
| `--provider`              | `-p` | 搜索供应商                                                   | tavily |
| `--time-range`            | `-t` | 时间范围 (time_range)，如 day, week, month, year                   | -      |
| `--category`              | -    | 搜索分类，具体值因供应商而异 (如 general, news, company 等)    | -      |
| `--no-images`             | -    | 排除图片结果                                                 | false  |
| `--include-domains`       | -    | 域名白名单，逗号分隔 (如: `example.com,techblog.com`)              | -      |
| `--exclude-domains`       | -    | 域名黑名单，逗号分隔 (如: `spam.com,ads.com`)                      | -      |
| `--start-crawl-date`      | -    | `exa` 专用: 爬取起始时间 (ISO8601 格式)                            | -      |
| `--end-crawl-date`        | -    | `exa` 专用: 爬取结束时间 (ISO8601 格式)                            | -      |
| `--start-published-date`  | -    | `exa` 专用: 发布起始时间 (ISO8601 格式)                            | -      |
| `--end-published-date`    | -    | `exa` 专用: 发布结束时间 (ISO8601 格式)                            | -      |
| `--crawl-results`         | -    | `search1_*` 专用: 爬取完整网页内容的数量                         | -      |
| `--include-row-content`   | -    | `metaso` 专用: 返回页面完整文本内容 (可能产生额外费用)           | -      |
| `--page`                  | -    | 分页页码 (`metaso`/`unifuncs` 专用，metaso 1 page = 10 条)         | -      |
| `--max-tokens-per-page`   | -    | `perplexity` 专用: 每页返回的最大 Token 数量                       | -      |
| `--country`               | -    | `perplexity` 专用: 按国家/地区过滤结果                             | -      |
| `--json`                  | `-j` | 输出原始JSON响应                                               | false  |

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
			"summary": "摘要",
			"score": 0.85,
			"images": []
		}
	],
	"images": ["https://..."],
	"response_time": 0.95,
	"request_id": "xxx-xxx-xxx"
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
  - `summary`：AI 生成的摘要（如有）
  - `score`：相关性分数（如有）
  - `images`：相关图片（如有）
- `images`：搜索结果中的图片列表
- `response_time`：API 响应时间（秒）
- `request_id`：请求 ID

### 原始 JSON 输出（--json）

使用 `--json` 参数可获取 302 API 的原始响应，包含所有字段：

```json
{
  "search_results": [...],
  "data": {
    "query": "搜索词",
    "images": [...],
    "results": [...],
    "response_time": 0.95,
    "request_id": "xxx-xxx-xxx"
  },
  "images": [...]
}
```

## 支持的供应商及其特定参数

| 供应商         | provider 值      | 分类 (category) | 时间范围 (time_range) | 特殊参数说明 |
| -------------- | ---------------- | ---------------- | -------------------- | ------------- |
| Tavily         | `tavily`         | `general`, `news` | `day`, `week`, `month`, `year` | 默认供应商，高质量综合搜索 |
| Search1        | `search1_search` | `google`, `bing` 等 | `day`, `month`, `year` | 支持 `crawl_results` 爬取全网页 |
| Search1 News   | `search1_news`   | 同上 | 同上 | 专注于新闻 |
| Bocha          | `bocha`          | - | `oneDay`, `oneWeek` 等 | 中文搜索优化 |
| Exa            | `exa`            | `company`, `news`, `pdf` 等 | - | 不支持 time_range，使用专用的四个 Date 参数替代 |
| Metaso         | `metaso`         | `webpage`, `scholar`, `video` 等 | - | 不支持 time_range。支持 `page`, `include_row_content` |
| Firecrawl      | `firecrawl`      | - | `day`, `hour`, `week` 等 | - |
| Perplexity     | `perplexity`     | - | - | 不支持 time_range。限制: `max_results` ≤ 20. 支持 `country`, `max_tokens_per_page` |
| Unifuncs       | `unifuncs`       | - | `Day`, `Week`, `Month`, `Year` | 支持 `page` 分页 |

*- 其他 Search1 分类: `duckduckgo`, `yahoo`, `youtube`, `x`, `reddit`, `github`, `arxiv`, `wechat`, `bilibili`, `imdb`, `wikipedia`.*

**注意**：为避免触发 API 报错，脚本内部会自动检查你传递的 `time_range` 是否被该 `provider` 真正支持；如果传递给不支持它的引擎（如 `metaso` 或 `exa`），将会在这边直接抛出异常拦截。

## API 参考

- **端点**：`POST https://api.302.ai/302/general/search`
- **认证**：`Authorization: Bearer {{API_KEY}}`
- **Content-Type**：`application/json`

### 请求参数示例 (API 层面)

```json
{
  "query": "人工智能最新进展",
  "provider": "tavily",
  "max_results": 10,
  "time_range": "week",
  "category": "news",
  "include_images": true
}
```

## 最佳实践

### 提高搜索质量

1. **使用具体的关键词**：`"AI 大语言模型 最新进展"` 比 `"AI"` 更有效
2. **选择合适的供应商与分类**：
   - 找最近新闻：`--provider tavily --category news --time-range week`
   - 找公司介绍：`--provider exa --category company`
   - 找学术资源：`--provider metaso --category scholar`
   - 找微信公众号文章：`--provider search1_search --category wechat`
3. **域名过滤**：找技术资料时限定具体网站，如 `--include-domains github.com,stackoverflow.com`

### 节省 API 费用/提高速度

1. **限制结果数量**：`--count 5` 而不是默认的 10 (Perplexity 供应商受限为最多 20)。
2. **谨慎使用抓取参数**：如非必需，避免在 `metaso` 开启 `--include-row-content`（因内容大可能产生额外计费），或者在 `search1_*` 设置过大的 `--crawl-results`。
3. **排除图片**：`--no-images` 减少数据传输。

### 错误处理

脚本会自动处理常见错误：
- API 余额不足
- 尝试为 provider 传递了不支持的 time_range 或 category 报错
- 无效的 provider
- 网络超时
- 参数验证失败

错误信息会通过标准错误输出（stderr）显示。
