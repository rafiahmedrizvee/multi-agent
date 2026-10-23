
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from app.research_agent import research_topic
from app.analyst_agent import analyze_sources
from app.writer_agent import write_report


class ResearchState(TypedDict, total=False):
    topic: str
    research_result: dict
    analysis_result: dict
    writer_result: dict


def researcher_node(state: ResearchState) -> dict:
    """Collect research sources from the web."""

    result = research_topic(state["topic"])

    return {"research_result": result}


def analyst_node(state: ResearchState) -> dict:
    """Analyze the sources collected by the Research Agent."""

    research = state.get("research_result", {})

    if research.get("status") != "success":
        return {
            "analysis_result": {
                "status": "error",
                "message": research.get(
                    "message",
                    "Research Agent failed to collect sources.",
                ),
            }
        }

    sources = research.get("sources", [])

    if not sources:
        return {
            "analysis_result": {
                "status": "error",
                "message": "No research sources are available for analysis.",
            }
        }

    result = analyze_sources(
        state["topic"],
        sources,
    )

    return {"analysis_result": result}


def writer_node(state: ResearchState) -> dict:
    """Generate the final research report."""

    analysis = state.get("analysis_result", {})

    if analysis.get("status") != "success":
        return {"writer_result": analysis}

    research = state.get("research_result", {})
    sources = research.get("sources", [])

    result = write_report(
        state["topic"],
        analysis.get("analysis", ""),
        sources,
    )

    return {"writer_result": result}


def build_research_workflow():
    """Build and compile the sequential LangGraph workflow."""

    workflow = StateGraph(ResearchState)

    workflow.add_node("researcher", researcher_node)
    workflow.add_node("analyst", analyst_node)
    workflow.add_node("writer", writer_node)

    workflow.add_edge(START, "researcher")
    workflow.add_edge("researcher", "analyst")
    workflow.add_edge("analyst", "writer")
    workflow.add_edge("writer", END)

    return workflow.compile()


research_workflow = build_research_workflow()


def run_research_workflow(topic: str) -> dict:
    """Run the complete multi-agent research workflow."""

    topic = topic.strip()

    if not topic:
        return {
            "status": "error",
            "message": "Research topic cannot be empty.",
        }

    try:
        result = research_workflow.invoke({"topic": topic})

        writer_result = result.get("writer_result", {})

        if not writer_result:
            return {
                "status": "error",
                "message": "The workflow finished without producing a report.",
                "workflow": "LangGraph",
                "agents": ["researcher", "analyst", "writer"],
            }

        return {
            **writer_result,
            "workflow": "LangGraph",
            "agents": ["researcher", "analyst", "writer"],
        }

    except Exception as exc:
        print(
            f"[Research Workflow] Error: "
            f"{type(exc).__name__}: {exc}"
        )

        return {
            "status": "error",
            "message": (
                "The research workflow failed. "
                "Check the backend logs for details."
            ),
            "workflow": "LangGraph",
            "agents": ["researcher", "analyst", "writer"],
        }
