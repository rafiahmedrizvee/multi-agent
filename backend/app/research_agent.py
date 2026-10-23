
import re
import time
from urllib.parse import (
    parse_qsl,
    urlencode,
    urlparse,
    urlunparse,
)

from app.research_tools import search_web


MAX_RESULTS = 5
MAX_TITLE_LENGTH = 200
MAX_CONTENT_LENGTH = 6000

TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "dclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "ref_src",
}

TRACKING_PREFIXES = (
    "utm_",
)


def _normalize_url(url: object) -> str:
    """Return a normalized absolute HTTP(S) URL."""
    if not isinstance(url, str):
        return ""

    url = url.strip()

    # Handle common Markdown link formats.
    for _ in range(3):
        match = re.fullmatch(
            r"\[.*?\]\(\s*<?(https?://[^)\s>]+)>?\s*\)",
            url,
            flags=re.IGNORECASE,
        )

        if not match:
            break

        url = match.group(1).strip()

    # Remove surrounding angle brackets.
    if url.startswith("<") and url.endswith(">"):
        url = url[1:-1].strip()

    if not url:
        return ""

    try:
        parsed = urlparse(url)

        if parsed.scheme.lower() not in {"http", "https"}:
            return ""

        if not parsed.hostname:
            return ""

        if any(char.isspace() for char in url):
            return ""

        # Accessing port also detects malformed port values.
        _ = parsed.port

        # Normalize host casing while preserving path and query.
        host = parsed.hostname.lower()

        if ":" in host and not host.startswith("["):
            host = f"[{host}]"

        if parsed.port is not None:
            default_port = (
                parsed.scheme.lower() == "http" and parsed.port == 80
            ) or (
                parsed.scheme.lower() == "https" and parsed.port == 443
            )

            if not default_port:
                host = f"{host}:{parsed.port}"

        if parsed.username or parsed.password:
            # Avoid URLs containing embedded credentials.
            return ""

        query_items = parse_qsl(
            parsed.query,
            keep_blank_values=True,
        )

        clean_query = [
            (key, value)
            for key, value in query_items
            if key.lower() not in TRACKING_PARAMS
            and not key.lower().startswith(TRACKING_PREFIXES)
        ]

        normalized = parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=host,
            query=urlencode(clean_query, doseq=True),
            fragment="",
        )

        return urlunparse(normalized)

    except (ValueError, AttributeError):
        return ""


def _canonical_url(url: str) -> str:
    """Create a comparison key for duplicate URL detection."""
    try:
        parsed = urlparse(url)

        path = parsed.path.rstrip("/") or "/"

        return urlunparse(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                path,
                "",
                parsed.query,
                "",
            )
        )

    except (ValueError, AttributeError):
        return url


def _clean_title(title: object) -> str:
    """Normalize and limit a source title."""
    if not isinstance(title, str):
        return "Untitled source"

    title = re.sub(r"\s+", " ", title).strip()

    # Remove common control characters.
    title = "".join(
        char for char in title
        if char.isprintable()
    )

    return title[:MAX_TITLE_LENGTH] or "Untitled source"


def _clean_content(content: object) -> str:
    """Normalize source text without inventing missing information."""
    if not isinstance(content, str):
        return ""

    content = re.sub(r"\s+", " ", content).strip()

    return content[:MAX_CONTENT_LENGTH]


def _normalize_sources(results: object) -> list[dict]:
    """Validate, normalize, and deduplicate web search results."""
    if not isinstance(results, list):
        return []

    sources = []
    seen_urls = set()

    for item in results:
        if not isinstance(item, dict):
            continue

        url = _normalize_url(item.get("url"))

        if not url:
            continue

        canonical = _canonical_url(url)

        if canonical in seen_urls:
            continue

        seen_urls.add(canonical)

        source = {
            **item,
            "title": _clean_title(item.get("title")),
            "url": url,
            "content": _clean_content(item.get("content")),
        }

        sources.append(source)

    return sources


def _error_result(
    topic: str,
    message: str,
    status: str = "error",
) -> dict:
    """Build a consistent failure response."""
    return {
        "status": status,
        "message": message,
        "topic": topic,
        "sources": [],
        "report": None,
        "model": "Tavily Web Search",
    }


def research_topic(topic: str) -> dict:
    """Collect, validate, and deduplicate sources using Tavily."""
    total_start = time.perf_counter()

    topic = topic.strip() if isinstance(topic, str) else ""

    if not topic:
        return _error_result(
            topic,
            "Research topic cannot be empty.",
        )

    try:
        # Step 1: Search the web.
        search_start = time.perf_counter()

        search_result = search_web(
            topic,
            max_results=MAX_RESULTS,
        )

        search_elapsed = time.perf_counter() - search_start

        print(
            f"[Research Agent] Web search: {search_elapsed:.2f}s"
        )

        # Step 2: Validate the tool response.
        if not isinstance(search_result, dict):
            raise TypeError(
                "The web search tool returned an invalid response."
            )

        if search_result.get("status") != "success":
            message = search_result.get(
                "message",
                "Web search failed.",
            )

            print(f"[Research Agent] Search failed: {message}")

            return _error_result(
                topic,
                str(message),
                str(search_result.get("status") or "error"),
            )

        # Step 3: Normalize source data.
        raw_results = search_result.get("results", [])

        raw_count = (
            len(raw_results)
            if isinstance(raw_results, list)
            else 0
        )

        sources = _normalize_sources(raw_results)

        print(f"[Research Agent] Raw results: {raw_count}")
        print(
            f"[Research Agent] Valid unique sources: {len(sources)}"
        )

        if not sources:
            total_elapsed = time.perf_counter() - total_start

            print(
                f"[Research Agent] Total time: {total_elapsed:.2f}s"
            )

            return _error_result(
                topic,
                "No valid, unique HTTP(S) sources were found.",
                "no_sources",
            )

        # Step 4: Log basic source-content coverage.
        sources_with_content = sum(
            bool(source["content"])
            for source in sources
        )

        print(
            "[Research Agent] Sources with content: "
            f"{sources_with_content}/{len(sources)}"
        )

        # Step 5: Return sources to the Analyst and Writer agents.
        result = {
            "status": "success",
            "topic": topic,
            "sources": sources,
            "report": None,
            "model": "Tavily Web Search",
        }

        total_elapsed = time.perf_counter() - total_start

        print(
            f"[Research Agent] Total time: {total_elapsed:.2f}s"
        )

        return result

    except Exception as exc:
        total_elapsed = time.perf_counter() - total_start

        print(
            f"[Research Agent] Error: {type(exc).__name__}: {exc}"
        )
        print(
            f"[Research Agent] Total time: {total_elapsed:.2f}s"
        )

        return _error_result(
            topic,
            f"Research failed: {type(exc).__name__}: {exc}",
        )
