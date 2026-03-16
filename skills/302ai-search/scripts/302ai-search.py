#!/usr/bin/env python3
"""
302ai-search - 使用 302.AI 通用搜索 API 进行网络搜索

Usage:
    302ai-search.py "搜索关键词"
    302ai-search.py "今天的新闻" --count 10 --provider tavily
    302ai-search.py "AI trends" --freshness week --json
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
from typing import Optional


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
]

# 默认值
DEFAULT_PROVIDER = "tavily"
DEFAULT_COUNT = 5


def search(
    query: str,
    api_key: str = None,
    count: int = DEFAULT_COUNT,
    provider: str = DEFAULT_PROVIDER,
    freshness: Optional[str] = None,
    raw_json: bool = False,
) -> dict:
    """
    使用 302.AI 通用搜索 API 进行网络搜索

    Args:
        query: 搜索关键词
        api_key: 302.AI API Key，如果不提供则从环境变量获取
        count: 返回结果数量，默认5
        provider: 搜索供应商，默认tavily
        freshness: 时效性过滤（day/week/month）
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

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "query": query,
        "provider": provider,
        "max_results": count,
        "include_images": True,
    }

    # 添加时效性参数（映射到 time_range）
    if freshness:
        payload["time_range"] = freshness

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
            "images": result.get("images", []),
        })

    return {
        "query": query,
        "count": len(formatted_results),
        "provider": provider,
        "results": formatted_results,
        "images": data.get("images", []),
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
  302ai-search "AI trends" --count 10 --provider exa
  302ai-search "最新技术" --freshness week --json
        """
    )

    parser.add_argument("query", help="搜索关键词")
    parser.add_argument("--count", "-c", type=int, default=DEFAULT_COUNT,
                        help=f"返回结果数量 (默认: {DEFAULT_COUNT})")
    parser.add_argument("--provider", "-p", default=DEFAULT_PROVIDER,
                        choices=SUPPORTED_PROVIDERS,
                        help=f"搜索供应商 (默认: {DEFAULT_PROVIDER})")
    parser.add_argument("--freshness", "-f", choices=["day", "week", "month"],
                        help="时效性过滤: day, week, month")
    parser.add_argument("--json", "-j", action="store_true",
                        help="输出原始JSON响应")

    args = parser.parse_args()

    try:
        result = search(
            query=args.query,
            count=args.count,
            provider=args.provider,
            freshness=args.freshness,
            raw_json=args.json,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
