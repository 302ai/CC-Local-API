#!/usr/bin/env python3
"""
302ai-search - 使用 302.AI 通用搜索 API 进行网络搜索
支持供应商自动切换：当某个供应商失败时，自动尝试下一个

Usage:
    302ai-search.py "搜索关键词"
    302ai-search.py "今天的新闻" --count 10 --provider tavily
    302ai-search.py "AI trends" --time-range week --json
    302ai-search.py "AI公司" --provider exa --category company
"""

import sys
import os

try:
    import requests
except ImportError:
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
        subprocess.call([found_python] + sys.argv)
        sys.exit(0)
    else:
        print("错误: 需要安装 requests 模块", file=sys.stderr)
        print("请运行: pip3 install requests", file=sys.stderr)
        sys.exit(1)

import json
import argparse
from typing import Optional, List

API_URL = "https://api.302.ai/302/general/search"

# 供应商优先级列表（按顺序尝试）
PROVIDER_FALLBACK_ORDER = [
    "tavily",
    "search1_search",
    "metaso",
    "exa",
    "bocha",
    "firecrawl",
    "perplexity",
    "unifuncs",
    "search1_news",
]

DEFAULT_PROVIDER = "tavily"
DEFAULT_COUNT = 5

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

PROVIDER_TIME_RANGES = {
    "tavily": ["day", "week", "month", "year", "d", "w", "m", "y"],
    "search1_search": ["day", "month", "year"],
    "search1_news": ["day", "month", "year"],
    "bocha": ["oneDay", "oneWeek", "oneMonth", "oneYear"],
    "firecrawl": ["day", "hour", "week", "month", "year"],
    "unifuncs": ["Day", "Week", "Month", "Year"],
}


def parse_list_arg(value: str) -> List[str]:
    """解析逗号分隔的列表参数"""
    return [item.strip() for item in value.split(",") if item.strip()]


def is_provider_compatible(provider: str, time_range: Optional[str], category: Optional[str]) -> bool:
    """检查供应商是否兼容给定的参数"""
    if time_range and provider in PROVIDER_TIME_RANGES:
        if time_range not in PROVIDER_TIME_RANGES[provider]:
            return False
    elif time_range and provider not in PROVIDER_TIME_RANGES:
        return False
    
    if category and provider in PROVIDER_CATEGORIES:
        if category not in PROVIDER_CATEGORIES[provider]:
            return False
    
    return True


def try_search(
    query: str,
    api_key: str,
    count: int,
    provider: str,
    time_range: Optional[str],
    include_images: bool,
    category: Optional[str],
    include_domains: Optional[List[str]],
    exclude_domains: Optional[List[str]],
    start_crawl_date: Optional[str],
    end_crawl_date: Optional[str],
    start_published_date: Optional[str],
    end_published_date: Optional[str],
    crawl_results: Optional[int],
    include_row_content: Optional[bool],
    page: Optional[int],
    max_tokens_per_page: Optional[int],
    country: Optional[str],
) -> tuple:
    """
    尝试使用指定供应商进行搜索
    
    Returns:
        (success: bool, result: dict or str)
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "query": query,
        "provider": provider,
        "max_results": count,
        "include_images": include_images,
    }

    if time_range:
        payload["time_range"] = time_range
    if category:
        payload["category"] = category
    if include_domains:
        payload["include_domains"] = include_domains
    if exclude_domains:
        payload["exclude_domains"] = exclude_domains
    if start_crawl_date:
        payload["startCrawlDate"] = start_crawl_date
    if end_crawl_date:
        payload["endCrawlDate"] = end_crawl_date
    if start_published_date:
        payload["startPublishedDate"] = start_published_date
    if end_published_date:
        payload["endPublishedDate"] = end_published_date
    if crawl_results is not None:
        payload["crawl_results"] = crawl_results
    if include_row_content is not None:
        payload["includeRowContent"] = include_row_content
    if page is not None:
        payload["page"] = page
    if max_tokens_per_page is not None:
        payload["max_tokens_per_page"] = max_tokens_per_page
    if country:
        payload["country"] = country

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return True, response.json()
    except requests.exceptions.Timeout:
        return False, "请求超时"
    except requests.exceptions.RequestException as e:
        error_msg = "网络请求失败"
        if hasattr(e, "response") and e.response is not None:
            try:
                error_data = e.response.json()
                error_msg = error_data.get("error", e.response.text)
            except:
                error_msg = e.response.text or f"HTTP {e.response.status_code}"
        return False, error_msg


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
    fallback: bool = True,
) -> dict:
    """
    使用 302.AI 通用搜索 API 进行网络搜索
    
    Args:
        fallback: 是否启用供应商自动切换（默认开启）
    """
    if not api_key:
        api_key = os.environ.get("AI302_API_KEY")
        if not api_key:
            raise ValueError("需要提供 AI302_API_KEY 或设置环境变量")

    # 构建尝试列表
    if fallback:
        # 从指定供应商开始，然后是其他供应商
        providers_to_try = [provider]
        for p in PROVIDER_FALLBACK_ORDER:
            if p != provider:
                providers_to_try.append(p)
    else:
        providers_to_try = [provider]

    attempted = []
    
    for current_provider in providers_to_try:
        # 跳过不兼容参数的供应商
        if not is_provider_compatible(current_provider, time_range, category):
            continue
            
        success, result = try_search(
            query=query,
            api_key=api_key,
            count=count,
            provider=current_provider,
            time_range=time_range,
            include_images=include_images,
            category=category,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            start_crawl_date=start_crawl_date,
            end_crawl_date=end_crawl_date,
            start_published_date=start_published_date,
            end_published_date=end_published_date,
            crawl_results=crawl_results,
            include_row_content=include_row_content,
            page=page,
            max_tokens_per_page=max_tokens_per_page,
            country=country,
        )
        
        if success:
            # 如果使用了备用供应商，添加提示信息
            if current_provider != provider and raw_json:
                result["_fallback_notice"] = f"原供应商 '{provider}' 失败，已自动切换至 '{current_provider}'"
            
            if raw_json:
                return result
            
            return format_result(result, query, current_provider, provider if current_provider != provider else None)
        
        attempted.append(f"{current_provider}: {result}")
    
    # 所有供应商都失败
    raise ValueError(f"所有供应商均失败。尝试记录: {'; '.join(attempted)}")


def format_result(data: dict, query: str, provider: str, fallback_from: Optional[str] = None) -> dict:
    """格式化搜索结果"""
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

    data_info = data.get("data", {})
    
    result = {
        "query": query,
        "count": len(formatted_results),
        "provider": provider,
        "results": formatted_results,
        "images": data.get("images", []),
        "response_time": data_info.get("response_time", None),
        "request_id": data_info.get("request_id", None),
    }
    
    if fallback_from:
        result["_fallback_notice"] = f"原供应商 '{fallback_from}' 失败，已自动切换至 '{provider}'"
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="使用 302.AI 通用搜索 API 进行网络搜索（支持供应商自动切换）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
支持的供应商: {', '.join(PROVIDER_FALLBACK_ORDER)}

供应商自动切换:
  当指定供应商失败时，会自动尝试其他供应商（默认开启）
  使用 --no-fallback 可禁用自动切换

示例:
  302ai-search "今天的新闻"
  302ai-search "AI trends" --count 10 --provider tavily
  302ai-search "最新技术" --time-range week --no-fallback
  302ai-search "AI公司" --provider exa --category company
        """
    )

    parser.add_argument("query", help="搜索关键词")
    parser.add_argument("--count", "-c", type=int, default=DEFAULT_COUNT,
                        help=f"返回结果数量 (默认: {DEFAULT_COUNT})")
    parser.add_argument("--provider", "-p", default=DEFAULT_PROVIDER,
                        choices=PROVIDER_FALLBACK_ORDER,
                        help=f"搜索供应商 (默认: {DEFAULT_PROVIDER})")
    parser.add_argument("--time-range", "-t",
                        help="时间范围，如: day, week, month, year")
    parser.add_argument("--category",
                        help="搜索分类，具体值因供应商而异")
    parser.add_argument("--no-images", action="store_true",
                        help="排除图片结果")
    parser.add_argument("--include-domains",
                        help="域名白名单，逗号分隔")
    parser.add_argument("--exclude-domains",
                        help="域名黑名单，逗号分隔")
    parser.add_argument("--no-fallback", action="store_true",
                        help="禁用供应商自动切换")

    # exa 专用参数
    exa_group = parser.add_argument_group("exa 专用参数")
    exa_group.add_argument("--start-crawl-date", help="爬取起始时间 (ISO8601)")
    exa_group.add_argument("--end-crawl-date", help="爬取结束时间")
    exa_group.add_argument("--start-published-date", help="发布起始时间")
    exa_group.add_argument("--end-published-date", help="发布结束时间")

    # search1 专用参数
    search1_group = parser.add_argument_group("search1 专用参数")
    search1_group.add_argument("--crawl-results", type=int,
                               help="爬取完整网页内容的数量")

    # metaso 专用参数
    metaso_group = parser.add_argument_group("metaso 专用参数")
    metaso_group.add_argument("--include-row-content", action="store_true",
                              help="返回页面完整文本内容")

    # 分页
    parser.add_argument("--page", type=int, help="分页页码")

    # perplexity 专用参数
    perplexity_group = parser.add_argument_group("perplexity 专用参数")
    perplexity_group.add_argument("--max-tokens-per-page", type=int,
                                  help="每页最大 Token 数")
    perplexity_group.add_argument("--country", help="国家/地区过滤")

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
            fallback=not args.no_fallback,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
