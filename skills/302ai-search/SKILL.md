---
name: 302ai-search
description: Use the 302.AI Universal Search API for web searches. It is used when you need to get real-time information, news, web content, and supports a variety of search engine providers (such as Tavily, Exa, Metaso, etc.). Configuration AI302_API_KEY is required.
metadata:
  { "openclaw": { "primaryEnv": "AI302_API_KEY", "requires": { "env": ["AI302_API_KEY"] } } }
---

# 302 Search

使用 302.AI 通用搜索 API 进行网络搜索，支持多种搜索引擎供应商。**当指定供应商失败时，会自动切换到备用供应商**。

## 前置要求

1. **302.AI API Key**：需要在 https://302.ai 注册并获取 API Key
2. **账户余额**：确保账户有足够余额用于搜索调用
3. **Python 环境**：Python 3.8+ 和 `requests` Python 包

## 安装依赖

```bash
pip3 install requests
```

## 配置 API Key

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

使配置生效：

```bash
openclaw gateway restart
```

## 使用方法

### 作为 Agent 工具使用

配置完成后，可以直接问 Agent：

> "用 302ai-search 搜一下今天的新闻"
> "帮我用 metaso 搜索学术论文，只看第一页"

### 直接调用脚本

```bash
# 基本用法
python3 ~/skills/302ai-search/scripts/302ai-search.py "搜索关键词"

# 指定结果数量和搜索引擎
python3 ~/skills/302ai-search/scripts/302ai-search.py "AI trends" --count 10 --provider tavily


# 其他用法
python3 ~/skills/302ai-search/scripts/302ai-search.py "AI公司" --provider exa --category company
python3 ~/skills/302ai-search/scripts/302ai-search.py "技术文章" --include-domains example.com,techblog.com
python3 ~/skills/302ai-search/scripts/302ai-search.py "学术论文" --provider metaso --category scholar --page 1
```

### 命令行参数

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `query` | - | 搜索关键词（必需） | - |
| `--count` | `-c` | 返回结果数量 | 5 |
| `--provider` | `-p` | 搜索供应商 | tavily |
| `--time-range` | `-t` | 时间范围 (day, week, month, year) | - |
| `--category` | - | 搜索分类 | - |
| `--no-images` | - | 排除图片结果 | false |
| `--include-domains` | - | 域名白名单，逗号分隔 | - |
| `--exclude-domains` | - | 域名黑名单，逗号分隔 | - |
| `--no-fallback` | - | 禁用供应商自动切换 | false |
| `--json` | `-j` | 输出原始JSON响应 | false |

## 供应商自动切换

当指定供应商请求失败时，脚本会自动尝试其他供应商（按优先级顺序）。

**供应商优先级：**
1. `tavily` (默认)
2. `search1_search`
3. `metaso`
4. `exa`
5. `bocha`
6. `firecrawl`
7. `perplexity`
8. `unifuncs`
9. `search1_news`

**使用示例：**

```bash
# 如果 tavily 失败，会自动尝试其他供应商
python3 ~/skills/302ai-search/scripts/302ai-search.py "今日新闻"

# 禁用自动切换，失败直接报错
python3 ~/skills/302ai-search/scripts/302ai-search.py "今日新闻" --no-fallback
```

当发生切换时，输出结果会包含 `_fallback_notice` 字段提示用户。

## 输出格式

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
    "request_id": "xxx-xxx-xxx",
    "_fallback_notice": "原供应商 'tavily' 失败，已自动切换至 'search1_search'"
}
```

## 支持的供应商

| 供应商 | provider 值 | 分类 (category) | 时间范围 |
|--------|-------------|-----------------|----------|
| Tavily | `tavily` | `general`, `news` | `day`, `week`, `month`, `year` |
| Search1 | `search1_search` | `google`, `bing` 等 | `day`, `month`, `year` |
| Search1 News | `search1_news` | 同上 | 同上 |
| Bocha | `bocha` | - | `oneDay`, `oneWeek` 等 |
| Exa | `exa` | `company`, `news`, `pdf` 等 | - |
| Metaso | `metaso` | `webpage`, `scholar`, `video` 等 | - |
| Firecrawl | `firecrawl` | - | `day`, `hour`, `week` 等 |
| Perplexity | `perplexity` | - | - |
| Unifuncs | `unifuncs` | - | `Day`, `Week`, `Month`, `Year` |

## 最佳实践

### 提高搜索质量

1. **使用具体的关键词**：`"AI 大语言模型 最新进展"` 比 `"AI"` 更有效
2. **选择合适的供应商与分类**：
   - 找最近新闻：`--provider tavily --category news --time-range week`
   - 找公司介绍：`--provider exa --category company`
   - 找学术资源：`--provider metaso --category scholar`
   - 找微信公众号文章：`--provider search1_search --category wechat`
3. **域名过滤**：找技术资料时限定具体网站，如 `--include-domains github.com,stackoverflow.com`

### 节省 API 费用

1. **限制结果数量**：`--count 5` 而不是默认的 10
2. **谨慎使用抓取参数**：避免在 `metaso` 开启 `--include-row-content`（可能产生额外计费）
3. **排除图片**：`--no-images` 减少数据传输
