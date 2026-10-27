
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.workflow import run_research_workflow


app = FastAPI(
    title="AgentResearch AI",
    description="LangGraph Multi-Agent Research and Report Writer API",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8080",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    result = run_research_workflow(request.topic)

    if result.get("status") != "success":
        raise HTTPException(
            status_code=503,
            detail=result.get(
                "message",
                "Research workflow failed.",
            ),
        )

    return result
