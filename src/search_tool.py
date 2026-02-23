"""
Generic web search tool using a configurable HTTP JSON API.
"""
from __future__ import annotations

from typing import Any, Dict, List
import os
import requests


def _normalize_results(data: Any, top_k: int) -> List[Dict[str, str]]:
    """Normalize common result shapes into [{title, snippet, url}]."""
    items = None
    if isinstance(data, dict):
        items = data.get("items") or data.get("results") or data.get("data") or data.get("webPages", {}).get("value")
    elif isinstance(data, list):
        items = data
    if not items or not isinstance(items, list):
        return []

    results = []
    for row in items[:top_k]:
        if isinstance(row, str):
            results.append({"title": row, "snippet": "", "url": ""})
            continue
        if not isinstance(row, dict):
            continue
        title = row.get("title") or row.get("name") or ""
        snippet = row.get("snippet") or row.get("description") or row.get("content") or row.get("answer") or ""
        url = row.get("link") or row.get("url") or row.get("href") or ""
        results.append({"title": str(title), "snippet": str(snippet), "url": str(url)})
    return results


def search_web(query: str, config: Dict[str, Any], top_k: int = 5) -> Dict[str, Any]:
    """
    Perform a web search via a configured JSON API.
    Config (settings.yaml):
      search:
        api_url: "https://serpapi.com/search.json"
        api_key: "..."
        api_key_param: "api_key"
        api_key_header: null
        query_param: "q"
        extra_params: { engine: "bing" }
    """
    search_cfg = config.get("search", {})
    api_url = search_cfg.get("api_url")
    provider = (search_cfg.get("provider") or "").lower().strip()
    if not api_url:
        return {"success": False, "error": "search_api_url_missing", "results": []}

    timeout = int(search_cfg.get("timeout", 15))
    api_key = search_cfg.get("api_key")

    # Tavily default flow
    if provider == "tavily" or "tavily" in api_url:
        api_key = api_key or os.getenv("TAVILY_API_KEY")
        if not api_key:
            return {"success": False, "error": "tavily_api_key_missing", "results": []}
        payload = {
            "api_key": api_key,
            "query": query,
            "max_results": top_k,
        }
        # Optional flags
        for k in ["search_depth", "include_domains", "exclude_domains", "include_answer", "include_images"]:
            if k in search_cfg:
                payload[k] = search_cfg[k]
        resp = requests.post(api_url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        results = _normalize_results(data, top_k=top_k)
        return {"success": True, "results": results, "raw": data}

    # Generic GET-based search API
    query_param = search_cfg.get("query_param", "q")
    params = {query_param: query}
    params.update(search_cfg.get("extra_params", {}) or {})

    headers = {}
    api_key_param = search_cfg.get("api_key_param")
    api_key_header = search_cfg.get("api_key_header")
    if api_key:
        if api_key_param:
            params[api_key_param] = api_key
        if api_key_header:
            headers[api_key_header] = api_key

    resp = requests.get(api_url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    results = _normalize_results(data, top_k=top_k)
    return {"success": True, "results": results, "raw": data}
