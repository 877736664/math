"""联网文档搜索服务。"""

from __future__ import annotations

import json
import logging
import re
from html import unescape
from urllib import error, parse, request


logger = logging.getLogger(__name__)


def search_online_documents(question: str, limit: int = 6) -> list[dict]:
    """从在线文档站点抓取与题目相关的候选资料。"""

    query = str(question or "").strip()
    if not query:
        return []

    results: list[dict] = []
    try:
        results.extend(_search_book118(query, limit=limit))
    except Exception:
        logger.exception("Book118 online search failed")

    try:
        results.extend(_search_doc88(query, limit=max(2, limit // 2)))
    except Exception:
        logger.exception("Doc88 online search failed")

    deduped: list[dict] = []
    seen: set[str] = set()
    for item in results:
        url = str(item.get("url", "")).strip()
        title = str(item.get("title", "")).strip()
        key = f"{title}|{url}"
        if not title or not url or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def render_online_search_context(results: list[dict]) -> str:
    """把联网搜索结果整理成适合给 LLM 的文本上下文。"""

    if not results:
        return ""

    lines = ["以下是联网检索到的相关文档标题与摘要，请谨慎吸收并优先提炼与题目最相关的信息："]
    for index, item in enumerate(results, start=1):
        source = item.get("source", "在线文档")
        title = item.get("title", "未命名文档")
        summary = item.get("summary", "")
        url = item.get("url", "")
        lines.append(f"{index}. [{source}] {title}")
        if summary:
            lines.append(f"   摘要：{summary}")
        if url:
            lines.append(f"   链接：{url}")
    return "\n".join(lines)


def _search_book118(query: str, limit: int) -> list[dict]:
    encoded = parse.quote(query)
    search_url = f"https://max.book118.com/search.html?q={encoded}"
    html = _fetch_text(search_url)
    if not html:
        return []

    api_path_match = re.search(r"loadmore:\s*'([^']+newSearchApi\.html)'", html)
    if not api_path_match:
        return []

    api_url = parse.urljoin("https://max.book118.com", api_path_match.group(1))
    try:
        body = _fetch_json(f"{api_url}?q={encoded}&page=1")
    except Exception:
        logger.exception("Book118 search API request failed")
        return []

    docs: list[dict] = []
    if isinstance(body, dict):
        data = body.get("data", {})
        if isinstance(data, dict):
            payload = data.get("list", {})
            if isinstance(payload, dict):
                raw_docs = payload.get("docs", [])
                if isinstance(raw_docs, list):
                    docs = raw_docs
            elif isinstance(payload, list):
                docs = [item for item in payload if isinstance(item, dict)]

    results: list[dict] = []
    for item in docs:
        if not isinstance(item, dict):
            continue
        title = _clean_html(item.get("title") or item.get("highlight") or "")
        url = str(item.get("url") or "").strip()
        if url and not url.startswith("http"):
            url = parse.urljoin("https://max.book118.com", url)
        summary = _clean_html(item.get("summary") or item.get("description") or "")
        if title and url:
            results.append(
                {
                    "source": "原创力文档",
                    "title": title,
                    "summary": summary,
                    "url": url,
                }
            )
        if len(results) >= limit:
            break
    return results


def _search_doc88(query: str, limit: int) -> list[dict]:
    encoded = parse.quote(query)
    search_url = f"https://www.doc88.com/tag/{encoded}"
    html = _fetch_text(search_url)
    if not html:
        return []

    pattern = re.compile(r'<a[^>]+href="(?P<href>/p-[^"]+)"[^>]*title="(?P<title>[^"]+)"', re.IGNORECASE)
    results: list[dict] = []
    for match in pattern.finditer(html):
        title = _clean_html(match.group("title"))
        url = parse.urljoin("https://www.doc88.com", match.group("href"))
        if title and url:
            results.append(
                {
                    "source": "道客巴巴",
                    "title": title,
                    "summary": "来自道客巴巴的相关文档标题，可作为补充参考。",
                    "url": url,
                }
            )
        if len(results) >= limit:
            break
    return results


def _fetch_text(url: str) -> str:
    http_request = request.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="GET")
    with request.urlopen(http_request, timeout=20) as response:
        return response.read().decode("utf-8", errors="ignore")


def _fetch_json(url: str) -> dict:
    http_request = request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"},
        method="GET",
    )
    with request.urlopen(http_request, timeout=20) as response:
        raw = response.read().decode("utf-8", errors="ignore")
    return json.loads(raw)


def _clean_html(value: object) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
