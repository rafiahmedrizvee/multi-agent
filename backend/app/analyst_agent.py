
import time
import ollama

LOCAL_MODEL = "qwen2.5:3b"

MAX_SOURCE_CHARS = 1000
MAX_OUTPUT_TOKENS = 200


def analyze_sources(topic: str, sources: list[dict]) -> dict:
    """Analyze web sources and extract concise, evidence-based findings."""

    total_start = time.perf_counter()
    topic = topic.strip()

    if not topic:
        return {
            "status": "error",
            "message": "Research topic cannot be empty.",
        }

    if not sources:
        return {
            "status": "no_sources",
            "message": "No sources are available for analysis.",
            "topic": topic,
            "analysis": "",
        }

    # Keep source context concise to reduce prompt processing time.
    source_parts = []

    for i, source in enumerate(sources, start=1):
        title = source.get("title", "Untitled")
        url = source.get("url", "")
        content = source.get("content", "") or ""
        content = content[:MAX_SOURCE_CHARS]

        source_parts.append(
            f"Source {i}:\n"
            f"Title: {title}\n"
            f"URL: {url}\n"
            f"Content: {content}"
        )

    source_context = "\n\n".join(source_parts)

    try:
        print(
            f"[Analyst Agent] Starting analysis "
            f"with {len(sources)} sources."
        )

        model_start = time.perf_counter()

        response = ollama.chat(
            model=LOCAL_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a concise, evidence-based research analyst. "
                        "Use only the supplied sources. Never invent facts, "
                        "statistics, or citations. Identify uncertainty when "
                        "relevant. Return brief Markdown with these sections: "
                        "Key Findings, Evidence and Source Numbers, "
                        "Limitations, Research Summary. "
                        "Prioritize the most important findings. "
                        "Keep the entire analysis under 180 words."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Topic: {topic}\n\n"
                        f"Sources:\n{source_context}\n\n"
                        "Analyze the sources for the report writer. "
                        "Use source numbers to support important claims."
                    ),
                },
            ],
            options={
                "temperature": 0.2,
                "num_predict": MAX_OUTPUT_TOKENS,
            },
        )

        model_elapsed = time.perf_counter() - model_start
        print(
            f"[Analyst Agent] Ollama generation: "
            f"{model_elapsed:.2f}s"
        )

        analysis = response["message"]["content"].strip()

        if not analysis:
            return {
                "status": "error",
                "message": "The model returned an empty analysis.",
                "topic": topic,
            }

        total_elapsed = time.perf_counter() - total_start
        print(
            f"[Analyst Agent] Total time: {total_elapsed:.2f}s"
        )

        return {
            "status": "success",
            "topic": topic,
            "analysis": analysis,
            "sources_analyzed": len(sources),
            "model": LOCAL_MODEL,
        }

    except Exception as exc:
        print(
            f"[Analyst Agent] Error: "
            f"{type(exc).__name__}: {exc}"
        )

        return {
            "status": "model_unavailable",
            "message": (
                "The Analyst Agent could not complete its analysis. "
                "Check that Ollama is running and the model is installed."
            ),
            "topic": topic,
        }
