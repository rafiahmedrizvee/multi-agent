import re
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import ollama


LOCAL_MODEL = "qwen2.5:3b"

MAX_ANALYSIS_CHARS = 1800
MAX_SOURCE_TITLE_CHARS = 150
MAX_SOURCE_EXCERPT_CHARS = 900
MAX_OUTPUT_TOKENS = 750
MAX_REPAIR_TOKENS = 750

REQUIRED_SECTIONS = (
    "Introduction",
    "Key Findings",
    "Evidence and Citations",
    "Limitations",
    "Conclusion",
)

PLACEHOLDER_TITLES = {
    "a specific title about the topic",
    "descriptive title",
    "your title here",
    "insert title",
    "title goes here",
    "untitled",
    "research report",
}


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


def _canonicalize_url(url: str) -> str:
    """Normalize common URL variations for duplicate detection."""
    try:
        parsed = urlparse(url.strip())
        scheme = parsed.scheme.lower()
        hostname = (parsed.hostname or "").lower()
        if not scheme or not hostname:
            return url.strip()

        # www is usually a presentation variant, not a different article.
        if hostname.startswith("www."):
            hostname = hostname[4:]

        port = parsed.port
        netloc = hostname
        if port and not (
            (scheme == "http" and port == 80)
            or (scheme == "https" and port == 443)
        ):
            netloc = f"{hostname}:{port}"

        # Ignore common tracking parameters while preserving content parameters.
        tracking_prefixes = ("utm_",)
        tracking_names = {
            "fbclid", "gclid", "dclid", "mc_cid", "mc_eid",
            "ref", "source", "campaign",
        }
        query_items = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in tracking_names
            and not key.lower().startswith(tracking_prefixes)
        ]
        query = urlencode(sorted(query_items), doseq=True)

        path = re.sub(r"/{2,}", "/", parsed.path or "/")
        if path != "/":
            path = path.rstrip("/")

        return urlunparse((scheme, netloc, path, "", query, ""))
    except (ValueError, AttributeError):
        return url.strip()


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
    """Validate and deduplicate sources; create context and Markdown."""
    valid_sources = []
    context_lines = []
    markdown_lines = []
    seen_urls = set()

    for source in sources:
        if not isinstance(source, dict):
            continue

        url = _normalize_url(source.get("url"))
        if not _is_valid_http_url(url):
            continue

        canonical_url = _canonicalize_url(url)
        if canonical_url in seen_urls:
            continue

        seen_urls.add(canonical_url)
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
            (i + 1 for i, line in enumerate(lines)
             if heading_pattern.match(line.strip())),
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
    return [
        number for number in sorted(found, key=int)
        if int(number) < 1 or int(number) > source_count
    ]


def _title_from_topic(topic: str) -> str:
    """Build a usable, deterministic report title from the user's topic."""
    title = re.sub(r"\s+", " ", str(topic or "")).strip()
    # If the prompt contains multiple sentences, use the first as the title basis.
    title = re.split(r"(?<=[.!?])\s+", title, maxsplit=1)[0].strip(" .!?")
    # Remove common instruction prefixes while preserving the actual subject.
    title = re.sub(
        r"(?i)^(?:please\s+)?(?:research|investigate|explore|analyze|analyse|"
        r"examine|study|review)\s+(?:the\s+)?(?:role\s+of\s+)?",
        "",
        title,
    )
    title = re.sub(r"(?i)^the role of\s+", "", title)
    title = title.strip(" .:;—-")
    if not title:
        title = "Research Report"
    if len(title) > 110:
        title = title[:107].rsplit(" ", 1)[0].rstrip(" ,:;-") + "..."
    return title[0].upper() + title[1:] if title else "Research Report"


def _ensure_valid_title(report: str, topic: str) -> str:
    """Replace missing/placeholder H1 titles without another model call."""
    title_match = re.search(r"(?m)^#\s+(.+?)\s*#*\s*$", report)
    title = title_match.group(1).strip() if title_match else ""
    bad_title = (
        not title
        or title.lower() in PLACEHOLDER_TITLES
        or bool(re.search(
            r"(?i)\b(descriptive title|your title here|insert title|"
            r"title goes here|a specific title about the topic)\b",
            title,
        ))
    )
    if not bad_title:
        return report.strip()

    fallback_title = _title_from_topic(topic)
    if title_match:
        start, end = title_match.span()
        return (report[:start] + f"# {fallback_title}" + report[end:]).strip()
    return f"# {fallback_title}\n\n{report.strip()}".strip()


def _validation_issues(report: str, source_count: int, topic: str = "") -> dict:
    """Collect structural, title, citation, and basic topic-coverage issues."""
    missing = _missing_sections(report)
    empty = _empty_sections(report)
    invalid_citations = _invalid_citations(report, source_count)

    title_match = re.search(r"(?m)^#\s+(.+?)\s*#*\s*$", report)
    title = title_match.group(1).strip() if title_match else ""
    invalid_title = (
        not title
        or title.lower() in PLACEHOLDER_TITLES
        or bool(
            re.search(
                r"(?i)\b(descriptive title|your title here|insert title|"
                r"title goes here|a specific title about the topic)\b",
                title,
            )
        )
    )

    # Basic deterministic coverage check for software-development research.
    topic_and_report = f"{topic}\n{report}"
    software_topic = bool(re.search(
        r"\b(software development|software engineering|coding|code generation|"
        r"developer productivity|AI agents?)\b",
        topic_and_report,
        flags=re.IGNORECASE,
    ))
    coverage_terms = {
        "code_generation": r"\b(code generation|generate code|coding assistance)\b",
        "debugging": r"\b(debugging|debug|bug fixing|fix bugs)\b",
        "automated_testing": r"\b(automated testing|test automation|unit tests|"
                             r"automated tests)\b",
        "code_review": r"\b(code review|reviewing code|pull request review)\b",
        "deployment": r"\b(deployment|deploying|software release|release automation)\b",
        "security_risks": r"\b(security risks?|vulnerabilit(?:y|ies)|prompt injection|"
                           r"data leakage|supply.chain)\b",
        "limitations": r"\b(limitations?|challenges?|failure|unreliable|"
                       r"human oversight|hallucination)\b",
        "future_opportunities": r"\b(future opportunities|future potential|emerging "
                                r"opportunities|future directions|outlook)\b",
    }
    required_coverage = (
        coverage_terms if software_topic else {
            "limitations": coverage_terms["limitations"]
        }
    )
    missing_coverage = [
        name for name, pattern in required_coverage.items()
        if not re.search(pattern, report, flags=re.IGNORECASE)
    ]

    return {
        "missing_sections": missing,
        "empty_sections": empty,
        "invalid_citations": invalid_citations,
        "invalid_title": invalid_title,
        "missing_coverage": missing_coverage,
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
                    "You are a careful research report writer. Return complete "
                    "Markdown only. Use the exact required headings. Use only "
                    "supplied findings and source excerpts. Never invent facts, "
                    "statistics, URLs, or citations. Use a real, topic-specific "
                    "title, never a placeholder. Be concise and finish every section."
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
        "Write a concise but useful Markdown research report of about 300-450 "
        "words (source list excluded). Create a meaningful H1 title using the "
        "actual research topic. Never copy example titles or placeholder text.\n"
        "Use these exact headings, in order:\n"
        "## Introduction\n"
        "## Key Findings\n"
        "## Evidence and Citations\n"
        "## Limitations\n"
        "## Conclusion\n\n"
        "Instructions:\n"
        "- Put one specific, informative H1 title on the first line.\n"
        "- In Key Findings, use separate labeled bullets for each major subtopic "
        "in the user's research request. For software-development AI-agent "
        "research, cover code generation, debugging, automated testing, code "
        "review, and deployment separately whenever relevant.\n"
        "- Discuss concrete security risks, limitations, and future opportunities "
        "when relevant to the research question.\n"
        "- Support factual claims with inline citations such as [1] or [2].\n"
        "- In Evidence and Citations, explain which source supports which claim; "
        "do not merely list citation numbers.\n"
        "- Cite only supplied source numbers. Do not imply a source supports a "
        "claim unless its supplied excerpt provides relevant evidence.\n"
        "- If evidence is insufficient for a subtopic, say so explicitly.\n"
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
        f"Previous draft to correct:\n{previous_report[:4000]}\n\n"
        "Rewrite the entire report as complete Markdown, about 300-450 words. "
        "Create a meaningful H1 title based on the actual topic. Never use a "
        "placeholder title. Include these exact H2 headings in this order:\n"
        "## Introduction\n"
        "## Key Findings\n"
        "## Evidence and Citations\n"
        "## Limitations\n"
        "## Conclusion\n\n"
        "Correct every reported issue. Cover the user's requested subtopics "
        "separately; for software-development AI-agent research, include code "
        "generation, debugging, automated testing, code review, deployment, "
        "security risks, limitations, and future opportunities when relevant. "
        "Explain which source supports each key claim. Only cite source numbers "
        f"from 1 to {source_count}. Use only supplied evidence. Do not add a "
        "Sources heading. Return only the complete report."
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
            f"[Writer Agent] Starting report generation with "
            f"{len(valid_sources)} unique valid sources."
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
        # Fix placeholder/missing titles locally; avoid another slow model call
        # for a deterministic formatting problem.
        report = _ensure_valid_title(report, topic)
        issues = _validation_issues(report, len(valid_sources), topic)
        truncated = str(done_reason or "").lower() == "length"

        def score(validation: dict, was_truncated: bool) -> int:
            return (
                len(validation["missing_sections"])
                + len(validation["empty_sections"])
                + len(validation["invalid_citations"])
                + len(validation["missing_coverage"])
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
            print(
                f"[Writer Agent] Repair stop reason: "
                f"{repair_reason or 'unknown'}"
            )

            if repaired:
                repaired = _clean_report(repaired)
                repaired = _ensure_valid_title(repaired, topic)
                repaired_issues = _validation_issues(
                    repaired, len(valid_sources), topic
                )
                repaired_truncated = str(repair_reason or "").lower() == "length"

                # Keep whichever draft has fewer validation failures.
                if score(repaired_issues, repaired_truncated) < score(
                    issues, truncated
                ):
                    report, issues, done_reason, truncated = (
                        repaired,
                        repaired_issues,
                        repair_reason,
                        repaired_truncated,
                    )

        complete = (
            not issues["missing_sections"]
            and not issues["empty_sections"]
            and not issues["invalid_citations"]
            and not issues["invalid_title"]
            and not issues["missing_coverage"]
            and not truncated
        )

        if source_markdown:
            report += "\n\n## Sources\n\n" + source_markdown

        total_elapsed = time.perf_counter() - total_start
        print(f"[Writer Agent] Final validation: {issues}")
        print(
            f"[Writer Agent] Complete: {complete}; "
            f"total time: {total_elapsed:.2f}s"
        )

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
                        "The report did not pass all validation checks. "
                        "Review it before relying on its claims."
                    ),
                    "missing_sections": issues["missing_sections"],
                    "empty_sections": issues["empty_sections"],
                    "invalid_citations": issues["invalid_citations"],
                    "invalid_title": issues["invalid_title"],
                    "missing_coverage": issues["missing_coverage"],
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
