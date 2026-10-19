
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.research_agent import research_topic

app = FastAPI(
    title="AgentResearch AI",
    description="Multi-Agent Research and Report Writer API",
    version="0.2.0",
)


class ResearchRequest(BaseModel):
    topic: str = Field(
        min_length=3,
        max_length=300,
        description="The topic to research",
    )


@app.get("/")
def root():
    return {
        "message": "AgentResearch AI API is running",
        "status": "ok",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}



@app.post("/api/research")
def create_research(request: ResearchRequest):
    result = research_topic(request.topic)

    if result["status"] in ("error", "model_unavailable"):
        raise HTTPException(
            status_code=503,
            detail=result["message"],
        )

    return result
