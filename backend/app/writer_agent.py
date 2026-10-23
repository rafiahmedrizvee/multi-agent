import re
import time
from urllib.parse import urlparse

import ollama


LOCAL_MODEL = "qwen2.5:3b"

MAX_ANALYSIS_CHARS = 1500
MAX_SOURCE_TITLE_CHARS = 150
MAX_SOURCE_EXCERPT_CHARS = 700
MAX_OUTPUT_TOKENS = 700
MAX_REPAIR_TOKENS = 700

REQUIRED_SECTIONS = (
    "Introduction",
    "Key Findings",
    "Evidence and Citations",
    "Limitations",
    "Conclusion",
)


def _normalize_url(url: object) -> str:
    """Extract a raw HTTP(S) URL from common Markdown link formats."""
    if not isinstance(url, str):
        return ""

    url = url.strip()

    for _ in range(3):
        match = re.fullmatch(
            r"\[.*?\]\(\s*<?(https?://[^)\s>]+)>?\s*\)",
            url,
            flags=re.IGNORECASE,
        )
        if not match:
            break
        url = match.group(1).strip()

    if url.startswith("<") and url.endswith(">"):
        url = url[1:-1].strip()

    return url


def _is_valid_http_url(url: object) -> bool:
    """Accept only absolute HTTP or HTTPS URLs with a hostname."""
    if not isinstance(url, str) or not url:
        return False

    try:
        parsed = urlparse(url)
        return (
            parsed.scheme.lower() in {"http", "https"}
            and bool(parsed.hostname)
            and not any(char.isspace() for char in url)
        )
    except (ValueError, AttributeError):
        return False


def _clean_title(title: object) -> str:
    """Normalize source titles and escape Markdown brackets."""
    text = str(title or "Untitled source").strip()
    text = re.sub(r"\s+", " ", text)[:MAX_SOURCE_TITLE_CHARS]
    text = text.replace("\\", "\\\\")
    text = text.replace("[", "\\[").replace("]", "\\]")
    return text or "Untitled source"


def _build_sources(sources: list[dict]) -> tuple[list[dict], str, str]:
    """Validate sources and create concise source context and Markdown."""
    valid_sources = []
    context_lines = []
    markdown_lines = []
    seen_urls = set()

    for source in sources:
        if not isinstance(source, dict):
            continue

        url = _normalize_url(source.get("url"))
        if not _is_valid_http_url(url) or url in seen_urls:
            continue

        seen_urls.add(url)
        title = _clean_title(source.get("title"))
        valid_source = {**source, "title": title, "url": url}
        valid_sources.append(valid_source)
        number = len(valid_sources)

        content = source.get("content", "")
        if not isinstance(content, str):
            content = ""
        content = re.sub(r"\s+", " ", content).strip()
        content = content[:MAX_SOURCE_EXCERPT_CHARS]

        context_lines.append(
            f"[{number}] {title}\nURL: {url}\n"
            f"Excerpt: {content or 'No source excerpt supplied.'}"
        )
        markdown_lines.append(f"{number}. [{title}]({url})")

    return (
        valid_sources,
        "\n\n".join(context_lines),
        "\n".join(markdown_lines),
    )


def _get_response_field(response, field: str):
    """Read a field from either a dictionary or an Ollama response."""
    if isinstance(response, dict):
        return response.get(field)
    return getattr(response, field, None)


def _get_content(response) -> str:
    """Extract generated content from an Ollama chat response."""
    message = _get_response_field(response, "message")

    if isinstance(message, dict):
        content = message.get("content", "")
    else:
        content = getattr(message, "content", "")

    return content.strip() if isinstance(content, str) else ""


def _clean_report(report: str) -> str:
    """Remove duplicated source lists and surrounding whitespace."""
    report = report.strip()
    return re.split(
        r"(?im)^\s*##\s+(?:Verified Source URLs|Sources)\s*$",
        report,
        maxsplit=1,
    )[0].strip()


def _missing_sections(report: str) -> list[str]:
    """Find required Markdown H2 headings."""
    missing = []
    for section in REQUIRED_SECTIONS:
        pattern = rf"^##[ \t]+{re.escape(section)}[ \t]*#*[ \t]*$"
        if not re.search(pattern, report, flags=re.IGNORECASE | re.MULTILINE):
            missing.append(section)
    return missing


def _empty_sections(report: str) -> list[str]:
    """Detect required headings with no meaningful body content."""
    empty = []
    lines = report.splitlines()

    for section in REQUIRED_SECTIONS:
        heading_pattern = re.compile(
            rf"^##[ \t]+{re.escape(section)}[ \t]*#*[ \t]*$",
            flags=re.IGNORECASE,
        )
        start = next(
            (i + 1 for i, line in enumerate(lines) if heading_pattern.match(line.strip())),
            None,
        )
        if start is None:
            continue

        body = []
        for line in lines[start:]:
            if re.match(r"^\s*#{1,2}\s+", line):
                break
            body.append(line)

        content = "\n".join(body).strip()
        if len(re.sub(r"[\s*_`>#-]", "", content)) < 20:
            empty.append(section)

    return empty


def _invalid_citations(report: str, source_count: int) -> list[str]:
    """Find numeric citations that refer to nonexistent sources."""
    found = set(re.findall(r"(?<!\!)\[(\d+)\]", report))
    invalid = []
    for number in sorted(found, key=int):
        if int(number) < 1 or int(number) > source_count:
            invalid.append(number)
    return invalid


def _validation_issues(report: str, source_count: int) -> dict:
    """Collect structural and citation validation issues."""
    missing = _missing_sections(report)
    empty = _empty_sections(report)
    invalid_citations = _invalid_citations(report, source_count)

    title_match = re.search(r"(?m)^#\s+(.+?)\s*#*\s*$", report)
    title = title_match.group(1).strip() if title_match else ""
    invalid_title = (
        not title
        or bool(
            re.search(
                r"(?i)\b(descriptive title|your title here|insert title|title goes here)\b",
                title,
            )
        )
    )

    return {
        "missing_sections": missing,
        "empty_sections": empty,
        "invalid_citations": invalid_citations,
        "invalid_title": invalid_title,
    }


def _generate_report(prompt: str, max_tokens: int) -> tuple[str, str | None, float]:
    """Generate text and return stop reason and elapsed time."""
    start = time.perf_counter()
    response = ollama.chat(
        model=LOCAL_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a careful research report writer. "
                    "Return complete Markdown only. Follow the exact required "
                    "headings. Use only supplied findings and source excerpts. "
                    "Never invent facts, statistics, URLs, or citations. "
                    "Be concise and finish every section."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        options={"temperature": 0.1, "num_predict": max_tokens},
    )
    elapsed = time.perf_counter() - start
    report = _get_content(response)
    done_reason = _get_response_field(response, "done_reason")
    return report, done_reason, elapsed


def _make_prompt(topic: str, analysis: str, source_context: str) -> str:
    return (
        f"Research topic: {topic}\n\n"
        f"Analyst findings:\n{analysis[:MAX_ANALYSIS_CHARS]}\n\n"
        f"Sources and excerpts:\n{source_context}\n\n"
        "Write a concise Markdown research report of about 180-250 words "
        "(source list excluded). Start with one specific H1 title about the "
        "actual topic, not a placeholder. Use these exact headings, in order:\n"
        "# A specific title about the topic\n"
        "## Introduction\n"
        "## Key Findings\n"
        "## Evidence and Citations\n"
        "## Limitations\n"
        "## Conclusion\n\n"
        "Instructions:\n"
        "- Write 1-3 short sentences under every heading.\n"
        "- Cover the topic's main subtopics.\n"
        "- Support factual claims with relevant inline citations such as [1].\n"
        "- In Evidence and Citations, explain what the cited excerpts support.\n"
        "- Cite only the supplied source numbers; never invent evidence.\n"
        "- If evidence is insufficient, state that explicitly.\n"
        "- Do not add a Sources heading; the application appends it.\n"
        "- Return the report only, with no preamble or code fences."
    )


def _make_repair_prompt(
    topic: str,
    analysis: str,
    source_context: str,
    previous_report: str,
    source_count: int,
) -> str:
    return (
        f"Research topic: {topic}\n"
        f"Analyst findings: {analysis[:MAX_ANALYSIS_CHARS]}\n"
        f"Sources and excerpts:\n{source_context}\n\n"
        f"Previous draft to correct (may be incomplete):\n{previous_report[:3500]}\n\n"
        "Rewrite the entire report, concise (180-250 words), as Markdown. "
        "Start with one specific H1 title. Include these exact headings in "
        "this order, each with 1-3 short sentences:\n"
        "# A specific title about the topic\n"
        "## Introduction\n"
        "## Key Findings\n"
        "## Evidence and Citations\n"
        "## Limitations\n"
        "## Conclusion\n\n"
        f"Only cite source numbers from 1 to {source_count}. "
        "Use only supplied evidence; do not invent claims or citations. "
        "Do not add a Sources heading. Return only the complete report."
    )


def write_report(topic: str, analysis: str, sources: list[dict]) -> dict:
    """Generate, validate, and optionally repair a research report."""
    total_start = time.perf_counter()
    topic = topic.strip() if isinstance(topic, str) else ""
    analysis = analysis.strip() if isinstance(analysis, str) else ""

    if not topic or not analysis:
        return {
            "status": "error",
            "complete": False,
            "message": "A topic and analysis are required.",
        }

    source_list = sources if isinstance(sources, list) else []
    valid_sources, source_context, source_markdown = _build_sources(source_list)

    if not valid_sources:
        return {
            "status": "error",
            "complete": False,
            "topic": topic,
            "message": "No valid source URLs are available.",
        }

    try:
        print(
            f"[Writer Agent] Starting report generation with {len(valid_sources)} valid sources."
        )
        prompt = _make_prompt(topic, analysis, source_context)
        report, done_reason, elapsed = _generate_report(prompt, MAX_OUTPUT_TOKENS)

        print(f"[Writer Agent] Ollama generation: {elapsed:.2f}s")
        print(f"[Writer Agent] Stop reason: {done_reason or 'unknown'}")

        if not report:
            return {
                "status": "error",
                "complete": False,
                "topic": topic,
                "message": "The Writer Agent returned an empty report.",
            }

        report = _clean_report(report)
        issues = _validation_issues(report, len(valid_sources))
        truncated = str(done_reason or "").lower() == "length"

        def score(validation: dict, was_truncated: bool) -> int:
            return (
                len(validation["missing_sections"])
                + len(validation["empty_sections"])
                + len(validation["invalid_citations"])
                + int(validation["invalid_title"])
                + int(was_truncated)
            )

        if score(issues, truncated) > 0:
            print(
                f"[Writer Agent] Validation issues: {issues}; "
                f"truncated={truncated}. Attempting one repair."
            )
            repair_prompt = _make_repair_prompt(
                topic, analysis, source_context, report, len(valid_sources)
            )
            repaired, repair_reason, repair_elapsed = _generate_report(
                repair_prompt, MAX_REPAIR_TOKENS
            )
            print(f"[Writer Agent] Repair generation: {repair_elapsed:.2f}s")
            print(f"[Writer Agent] Repair stop reason: {repair_reason or 'unknown'}")

            if repaired:
                repaired = _clean_report(repaired)
                repaired_issues = _validation_issues(repaired, len(valid_sources))
                repaired_truncated = str(repair_reason or "").lower() == "length"

                # Keep the draft with fewer validation failures. Prefer repaired
                # on ties only when it is not truncated and original was truncated.
                if score(repaired_issues, repaired_truncated) < score(issues, truncated):
                    report, issues, done_reason, truncated = (
                        repaired, repaired_issues, repair_reason, repaired_truncated
                    )

        complete = (
            not issues["missing_sections"]
            and not issues["empty_sections"]
            and not issues["invalid_citations"]
            and not issues["invalid_title"]
            and not truncated
        )

        if source_markdown:
            report += "\n\n## Sources\n\n" + source_markdown

        total_elapsed = time.perf_counter() - total_start
        print(f"[Writer Agent] Final validation: {issues}")
        print(f"[Writer Agent] Complete: {complete}; total time: {total_elapsed:.2f}s")

        result = {
            "status": "success" if complete else "incomplete",
            "complete": complete,
            "topic": topic,
            "report": report,
            "sources": valid_sources,
            "model": LOCAL_MODEL,
        }

        if not complete:
            result.update(
                {
                    "message": (
                        "The report did not pass all structural validation checks. "
                        "Review it before relying on its claims."
                    ),
                    "missing_sections": issues["missing_sections"],
                    "empty_sections": issues["empty_sections"],
                    "invalid_citations": issues["invalid_citations"],
                    "invalid_title": issues["invalid_title"],
                    "generation_limit_reached": truncated,
                }
            )
        return result

    except Exception as exc:
        print(f"[Writer Agent] Error: {type(exc).__name__}: {exc}")
        return {
            "status": "model_unavailable",
            "complete": False,
            "topic": topic,
            "message": (
                "The Writer Agent could not generate the report. "
                "Check that Ollama is running and the model is installed."
            ),
        }
