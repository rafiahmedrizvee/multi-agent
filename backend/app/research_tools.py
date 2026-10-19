
from tavily import TavilyClient

from app.config import settings


def search_web(query: str, max_results: int = 5) -> dict:
    """Search the web and return source-backed results."""

    if not query.strip():
        return {
            "status": "error",
            "message": "Search query cannot be empty.",
            "results": [],
        }

    if not settings.tavily_api_key:
        return {
            "status": "not_configured",
            "message": "Tavily API key is not configured.",
            "query": query,
            "results": [],
        }

    try:
        client = TavilyClient(api_key=settings.tavily_api_key)

        response = client.search(
            query=query,
            max_results=max(1, min(max_results, 10)),
            search_depth="basic",
        )

        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
            }
            for item in response.get("results", [])
        ]

        return {
            "status": "success",
            "query": query,
            "results": results,
        }

    except Exception:
        return {
            "status": "error",
            "message": "Web search failed. Check configuration and connection.",
            "query": query,
            "results": [],
        }
