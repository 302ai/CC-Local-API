#!/usr/bin/env python3
"""
302ai-search - 使用 302.AI 通用搜索 API 进行网络搜索

Usage:
    302ai-search.py "搜索关键词"
    302ai-search.py "今天的新闻" --count 10 --provider tavily
    302ai-search.py "AI trends" --time-range week --json
    302ai-search.py "AI公司" --provider exa --category company
    302ai-search.py "技术文章" --include-domains example.com,techblog.com
"""

import sys
import os

# 检查当前 Python 是否有 requests，如果没有尝试找其他 Python
try:
    import requests
except ImportError:
    # 尝试用 subprocess 找有 requests 的 Python
    import subprocess
    python_candidates = ['python3', 'python3.12', 'python3.11', 'python3.10', 'python3.9']
    found_python = None
    for py in python_candidates:
        try:
            result = subprocess.run([py, '-c', 'import requests'],
                                  capture_output=True, timeout=2)
            if result.returncode == 0:
                found_python = py
                break
        except:
            continue

    if found_python and found_python != sys.executable.split('/')[-1]:
        # 重新用找到的 Python 执行本脚本
        import subprocess
        subprocess.call([found_python] + sys.argv)
        sys.exit(0)
    else:
        print("错误: 需要安装 requests 模块", file=sys.stderr)
        print("请运行: pip3 install requests", file=sys.stderr)
        sys.exit(1)

import json
import argparse
from typing import Optional, List


# API 端点
API_URL = "https://api.302.ai/302/general/search"

# 支持的供应商列表
SUPPORTED_PROVIDERS = [
    "tavily",
    "search1_search",
    "search1_news",
    "bocha",
    "exa",
    "firecrawl",
    "metaso",
    "perplexity",
    "unifuncs",
]

# 默认值
DEFAULT_PROVIDER = "tavily"
DEFAULT_COUNT = 5

# 各供应商支持的 category 枚举
PROVIDER_CATEGORIES = {
    "tavily": ["general", "news"],
    "search1_search": ["google", "bing", "duckduckgo", "yahoo", "youtube", "x",
                       "reddit", "github", "arxiv", "wechat", "bilibili", "imdb", "wikipedia"],
    "search1_news": ["google", "bing", "duckduckgo", "yahoo", "youtube", "x",
                     "reddit", "github", "arxiv", "wechat", "bilibili", "imdb", "wikipedia"],
    "exa": ["company", "research paper", "news", "pdf", "github", "tweet",
            "personal site", "linkedin profile", "financial report"],
    "metaso": ["webpage", "document", "scholar", "podcast", "video", "image"],
}

# 各供应商支持的 time_range 枚举
PROVIDER_TIME_RANGES = {
    "tavily": ["day", "week", "month", "year", "d", "w", "m", "y"],
    "search1_search": ["day", "month", "year"],
    "search1_news": ["day", "month", "year"],
    "bocha": ["oneDay", "oneWeek", "oneMonth", "oneYear"],  # bocha 也支持日期范围格式，代码中作了宽容处理
    "firecrawl": ["day", "hour", "week", "month", "year"],
    "unifuncs": ["Day", "Week", "Month", "Year"],
}


def parse_list_arg(value: str) -> List[str]:
    """解析逗号分隔的列表参数"""
    return [item.strip() for item in value.split(",") if item.strip()]


def search(
    query: str,
    api_key: str = None,
    count: int = DEFAULT_COUNT,
    provider: str = DEFAULT_PROVIDER,
    time_range: Optional[str] = None,
    include_images: bool = True,
    category: Optional[str] = None,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    start_crawl_date: Optional[str] = None,
    end_crawl_date: Optional[str] = None,
    start_published_date: Optional[str] = None,
    end_published_date: Optional[str] = None,
    crawl_results: Optional[int] = None,
    include_row_content: Optional[bool] = None,
    page: Optional[int] = None,
    max_tokens_per_page: Optional[int] = None,
    country: Optional[str] = None,
    raw_json: bool = False,
) -> dict:
    """
    使用 302.AI 通用搜索 API 进行网络搜索

    Args:
        query: 搜索关键词
        api_key: 302.AI API Key，如果不提供则从环境变量获取
        count: 返回结果数量，默认5
        provider: 搜索供应商，默认tavily
        time_range: 时间范围，具体值因供应商而异
        include_images: 是否包含图片，默认True
        category: 搜索分类，具体值因供应商而异
        include_domains: 域名白名单列表
        exclude_domains: 域名黑名单列表
        start_crawl_date: ISO8601 日期，exa 专用，爬取起始时间
        end_crawl_date: ISO8601 日期，exa 专用，爬取结束时间
        start_published_date: ISO8601 日期，exa 专用，发布起始时间
        end_published_date: ISO8601 日期，exa 专用，发布结束时间
        crawl_results: 爬取完整网页数量，search1_search/search1_news 专用
        include_row_content: 是否返回完整文本，metaso 专用（可能产生额外费用）
        page: 分页页码，metaso/unifuncs 专用
        max_tokens_per_page: 每页最大 Token 数，perplexity 专用
        country: 国家过滤，perplexity 专用
        raw_json: 是否返回原始JSON响应

    Returns:
        包含搜索结果的 dict
    """
    if not api_key:
        api_key = os.environ.get("AI302_API_KEY")
        if not api_key:
            raise ValueError("需要提供 AI302_API_KEY 或设置环境变量")

    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"不支持的供应商: {provider}。支持的供应商: {', '.join(SUPPORTED_PROVIDERS)}")

    # 验证 category 是否在供应商支持范围内
    if category and provider in PROVIDER_CATEGORIES:
        valid_categories = PROVIDER_CATEGORIES[provider]
        if category not in valid_categories:
            raise ValueError(
                f"供应商 {provider} 不支持分类 '{category}'。"
                f"支持的分类: {', '.join(valid_categories)}"
            )

    # 验证 time_range 是否在供应商支持范围内，提前拦截错误以防 API 报错
    if time_range:
        if provider in PROVIDER_TIME_RANGES:
            valid_time_ranges = PROVIDER_TIME_RANGES[provider]
            # bocha supports ranges like YYYY-MM-DD..YYYY-MM-DD which is hard to enum fully
            if provider != "bocha" and time_range not in valid_time_ranges:
                raise ValueError(
                    f"供应商 {provider} 不支持时间范围 '{time_range}'。"
                    f"支持的时间范围: {', '.join(valid_time_ranges)}"
                )
        else:
            raise ValueError(f"供应商 {provider} 不支持 time_range(时间范围) 参数，请不要传递它。")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # 构建请求 payload
    payload = {
        "query": query,
        "provider": provider,
        "max_results": count,
        "include_images": include_images,
    }

    # 添加可选参数 —— 通用
    if time_range:
        payload["time_range"] = time_range

    if category:
        payload["category"] = category

    if include_domains:
        payload["include_domains"] = include_domains

    if exclude_domains:
        payload["exclude_domains"] = exclude_domains

    # 添加可选参数 —— exa 专用
    if start_crawl_date:
        payload["startCrawlDate"] = start_crawl_date

    if end_crawl_date:
        payload["endCrawlDate"] = end_crawl_date

    if start_published_date:
        payload["startPublishedDate"] = start_published_date

    if end_published_date:
        payload["endPublishedDate"] = end_published_date

    # 添加可选参数 —— search1 专用
    if crawl_results is not None:
        payload["crawl_results"] = crawl_results

    # 添加可选参数 —— metaso 专用
    if include_row_content is not None:
        payload["includeRowContent"] = include_row_content

    # 添加可选参数 —— metaso/unifuncs 分页
    if page is not None:
        payload["page"] = page

    # 添加可选参数 —— perplexity 专用
    if max_tokens_per_page is not None:
        payload["max_tokens_per_page"] = max_tokens_per_page

    if country:
        payload["country"] = country

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        raise ValueError("请求超时，请稍后重试")
    except requests.exceptions.RequestException as e:
        if hasattr(e, "response") and e.response is not None:
            try:
                error_data = e.response.json()
                error_msg = error_data.get("error", e.response.text)
            except:
                error_msg = e.response.text
            raise ValueError(f"API 错误 ({e.response.status_code}): {error_msg}")
        raise ValueError(f"网络请求失败: {str(e)}")

    data = response.json()

    # 如果请求原始JSON，直接返回
    if raw_json:
        return data

    # 格式化输出
    search_results = data.get("search_results", [])

    formatted_results = []
    for result in search_results:
        formatted_results.append({
            "title": result.get("title", ""),
            "url": result.get("url", ""),
            "snippet": result.get("description", "") or result.get("content", "")[:200] if result.get("content") else "",
            "content": result.get("content", ""),
            "published_at": result.get("published_at", ""),
            "summary": result.get("summary", ""),
            "score": result.get("score", None),
            "images": result.get("images", []),
        })

    # 构建 data 字段信息
    data_info = data.get("data", {})

    return {
        "query": query,
        "count": len(formatted_results),
        "provider": provider,
        "results": formatted_results,
        "images": data.get("images", []),
        "response_time": data_info.get("response_time", None),
        "request_id": data_info.get("request_id", None),
    }


def main():
    parser = argparse.ArgumentParser(
        description="使用 302.AI 通用搜索 API 进行网络搜索",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
支持的供应商:
  {', '.join(SUPPORTED_PROVIDERS)}

示例:
  302ai-search "今天的新闻"
  302ai-search "AI trends" --count 10 --provider tavily
  302ai-search "最新技术" --time-range week
  302ai-search "AI公司" --provider exa --category company
  302ai-search "技术文章" --include-domains example.com,techblog.com
  302ai-search "学术论文" --provider metaso --category scholar --page 2
  302ai-search "最近新闻" --no-images --json
        """
    )

    # 必需参数
    parser.add_argument("query", help="搜索关键词")

    # 通用可选参数
    parser.add_argument("--count", "-c", type=int, default=DEFAULT_COUNT,
                        help=f"返回结果数量 (默认: {DEFAULT_COUNT})")
    parser.add_argument("--provider", "-p", default=DEFAULT_PROVIDER,
                        choices=SUPPORTED_PROVIDERS,
                        help=f"搜索供应商 (默认: {DEFAULT_PROVIDER})")
    parser.add_argument("--time-range", "-t",
                        help="时间范围 (time_range)，具体值因供应商而异，如: day, week, month, year")
    parser.add_argument("--category",
                        help="搜索分类，具体值因供应商而异 (如 tavily: general/news; exa: company/news/pdf 等)")
    parser.add_argument("--no-images", action="store_true",
                        help="排除图片结果")
    parser.add_argument("--include-domains",
                        help="域名白名单，逗号分隔 (如: example.com,techblog.com)")
    parser.add_argument("--exclude-domains",
                        help="域名黑名单，逗号分隔 (如: spam.com,ads.com)")

    # exa 专用参数
    exa_group = parser.add_argument_group("exa 专用参数")
    exa_group.add_argument("--start-crawl-date",
                           help="爬取起始时间 (ISO8601 格式，如: 2024-01-01T00:00:00Z)")
    exa_group.add_argument("--end-crawl-date",
                           help="爬取结束时间 (ISO8601 格式)")
    exa_group.add_argument("--start-published-date",
                           help="发布起始时间 (ISO8601 格式)")
    exa_group.add_argument("--end-published-date",
                           help="发布结束时间 (ISO8601 格式)")

    # search1 专用参数
    search1_group = parser.add_argument_group("search1_search / search1_news 专用参数")
    search1_group.add_argument("--crawl-results", type=int,
                               help="爬取完整网页内容的数量")

    # metaso 专用参数
    metaso_group = parser.add_argument_group("metaso 专用参数")
    metaso_group.add_argument("--include-row-content", action="store_true",
                              help="返回页面完整文本内容 (可能产生额外费用)")

    # metaso / unifuncs 分页
    parser.add_argument("--page", type=int,
                        help="分页页码 (metaso: 1 page = 10 条; unifuncs 也支持)")

    # perplexity 专用参数
    perplexity_group = parser.add_argument_group("perplexity 专用参数")
    perplexity_group.add_argument("--max-tokens-per-page", type=int,
                                  help="每页返回的最大 Token 数量")
    perplexity_group.add_argument("--country",
                                  help="按国家/地区过滤结果")

    # 输出控制
    parser.add_argument("--json", "-j", action="store_true",
                        help="输出原始JSON响应")

    args = parser.parse_args()

    try:
        result = search(
            query=args.query,
            count=args.count,
            provider=args.provider,
            time_range=args.time_range,
            include_images=not args.no_images,
            category=args.category,
            include_domains=parse_list_arg(args.include_domains) if args.include_domains else None,
            exclude_domains=parse_list_arg(args.exclude_domains) if args.exclude_domains else None,
            start_crawl_date=args.start_crawl_date,
            end_crawl_date=args.end_crawl_date,
            start_published_date=args.start_published_date,
            end_published_date=args.end_published_date,
            crawl_results=args.crawl_results,
            include_row_content=args.include_row_content if args.include_row_content else None,
            page=args.page,
            max_tokens_per_page=args.max_tokens_per_page,
            country=args.country,
            raw_json=args.json,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
