
import ollama

from app.research_tools import search_web


LOCAL_MODEL = "qwen2.5:3b"


def research_topic(topic: str) -> dict:
    """Research a topic using Tavily and a local Ollama model."""

    topic = topic.strip()

    if not topic:
        return {
            "status": "error",
            "message": "Research topic cannot be empty.",
        }

    # Step 1: Search the web for real sources.
    search_result = search_web(topic, max_results=5)

    if search_result["status"] != "success":
        return {
            "status": search_result["status"],
            "message": search_result.get(
                "message", "Web search failed."
            ),
            "topic": topic,
            "sources": [],
        }

    sources = search_result["results"]

    if not sources:
        return {
            "status": "no_sources",
            "message": "No web sources were found.",
            "topic": topic,
            "sources": [],
        }

    # Step 2: Prepare source material for the local model.
    source_context = "\n\n".join(
        f"Source {i}:\n"
        f"Title: {source['title']}\n"
        f"URL: {source['url']}\n"
        f"Content: {source['content']}"
        for i, source in enumerate(sources, start=1)
    )

    # Step 3: Generate the research report locally.
    try:
        response = ollama.chat(
            model=LOCAL_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a careful research assistant. "
                        "Use only the supplied web sources for factual "
                        "claims. Cite claims using the exact source URLs "
                        "provided. Never invent sources, URLs, quotations, "
                        "or statistics. If the sources do not establish "
                        "something, clearly say so. Write a structured "
                        "report with a title, introduction, key findings, "
                        "conclusion, and source URLs."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Research topic: {topic}\n\n"
                        f"Available web sources:\n{source_context}\n\n"
                        "Write a useful, evidence-based research report."
                    ),
                },
            ],
            options={"temperature": 0.2},
        )

        report = response["message"]["content"]

        return {
            "status": "success",
            "topic": topic,
            "report": report,
            "sources": sources,
            "model": LOCAL_MODEL,
        }

    except Exception as exc:
        print(f"Local model error: {type(exc).__name__}: {exc}")

        return {
            "status": "model_unavailable",
            "message": (
                "The local AI model could not generate the report. "
                "Check that Ollama is running and the model is installed."
            ),
            "topic": topic,
            "sources": sources,
        }
