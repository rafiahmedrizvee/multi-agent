import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useState } from "react";
import {
  ArrowDown,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Clock3,
  ExternalLink,
  FileText,
  Globe2,
  LoaderCircle,
  Search,
  ShieldCheck,
  Sparkles,
  Users,
  Workflow,
} from "lucide-react";
import "./App.css";

const API_URL = "http://127.0.0.1:8100";

function App() {
  const [topic, setTopic] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  async function handleResearch(event) {
    event.preventDefault();

    const trimmedTopic = topic.trim();

    if (trimmedTopic.length < 3) {
      setError("Please enter a research topic with at least 3 characters.");
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const response = await fetch(`${API_URL}/api/research`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ topic: trimmedTopic }),
      });

      const data = await response.json();

      if (!response.ok || data.status === "error" || data.status === "no_sources") {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : typeof data.message === "string"
              ? data.message
              : "The research request failed. Please try again.",
        );
      }

      setResult(data);
    } catch (err) {
      if (err instanceof TypeError) {
        setError(
          "Cannot connect to the backend. Make sure the FastAPI server is running at http://127.0.0.1:8100.",
        );
      } else {
        setError(err.message || "Something went wrong. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  function getSourceUrl(source) {
    if (typeof source === "string") return source;
    return source?.url || source?.link || "";
  }

  function getSourceTitle(source, index) {
    if (typeof source === "string") {
      try {
        return new URL(source).hostname;
      } catch {
        return `Source ${index + 1}`;
      }
    }

    return source?.title || source?.url || `Source ${index + 1}`;
  }

  const sources = Array.isArray(result?.sources) ? result.sources : [];
  const report = typeof result?.report === "string" ? result.report : "";

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#home" aria-label="AgentResearch AI home">
          <span className="brand-icon">
            <Sparkles size={22} />
          </span>
          <span>
            <strong>AgentResearch</strong>
            <small>AI RESEARCH WORKSPACE</small>
          </span>
        </a>

        <nav className="top-nav" aria-label="Main navigation">
          <a className="nav-link active" href="#home">
            Workspace
          </a>
          <a className="nav-link" href="#workflow">
            How it works
          </a>
          <a className="nav-link" href="#results">
            Reports
          </a>
        </nav>

        <div className="status-pill">
          <span className="status-dot" />
          Local AI
        </div>
      </header>

      <main id="home">
        <section className="hero">
          <div className="hero-copy">
            <div className="eyebrow">
              <Sparkles size={15} />
              MULTI-AGENT INTELLIGENCE
            </div>

            <h1>
              Research smarter.
              <br />
              <span>Discover deeper.</span>
            </h1>

            <p className="hero-description">
              Turn complex questions into structured research reports.
              Three specialized AI agents work together to research the web,
              analyze evidence, and write your report.
            </p>

            <div className="hero-benefits">
              <span>
                <CheckCircle2 size={16} />
                Web-backed research
              </span>
              <span>
                <CheckCircle2 size={16} />
                Multi-agent workflow
              </span>
              <span>
                <CheckCircle2 size={16} />
                Source links included
              </span>
            </div>
          </div>

          <div className="hero-visual" aria-hidden="true">
            <div className="orbit orbit-one" />
            <div className="orbit orbit-two" />
            <div className="orbit-core">
              <Sparkles size={39} />
            </div>
            <div className="orbit-node node-top">
              <Search size={19} />
            </div>
            <div className="orbit-node node-right">
              <BookOpen size={19} />
            </div>
            <div className="orbit-node node-bottom">
              <FileText size={19} />
            </div>
            <div className="visual-label">THINK · ANALYZE · WRITE</div>
          </div>
        </section>

        <section className="workspace-grid">
          <div className="research-panel panel">
            <div className="panel-heading">
              <div className="heading-icon">
                <Search size={20} />
              </div>
              <div>
                <h2>Start your research</h2>
                <p>What would you like to investigate?</p>
              </div>
            </div>

            <form onSubmit={handleResearch}>
              <label className="field-label" htmlFor="research-topic">
                RESEARCH TOPIC
              </label>

              <textarea
                id="research-topic"
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
                placeholder="e.g. How are AI agents transforming healthcare in 2026?"
                rows={4}
                maxLength={300}
                minLength={3}
                disabled={loading}
                required
              />

              <div className="field-footer">
                <span>Be specific for more relevant results.</span>
                <span>{topic.length}/300</span>
              </div>

              {error && (
                <div className="error-message" role="alert">
                  {error}
                </div>
              )}

              <button
                className="generate-button"
                type="submit"
                disabled={loading}
              >
                {loading ? (
                  <>
                    <LoaderCircle className="spin" size={19} />
                    Researching...
                  </>
                ) : (
                  <>
                    <Sparkles size={18} />
                    Generate Research Report
                    <ArrowRight size={18} />
                  </>
                )}
              </button>

              <p className="privacy-note">
                <ShieldCheck size={15} />
                Powered by your local AI model and web search.
              </p>
            </form>
          </div>

          <aside className="workflow-panel panel" id="workflow">
            <div className="section-kicker">YOUR RESEARCH TEAM</div>
            <h2>Three agents. One report.</h2>
            <p className="workflow-intro">
              Each agent has a dedicated role in the research process.
            </p>

            <div className="agent-list">
              <div className="agent-item">
                <div className="agent-icon researcher-icon">
                  <Globe2 size={19} />
                </div>
                <div className="agent-info">
                  <strong>01 · Researcher</strong>
                  <span>Finds relevant web sources</span>
                </div>
                <span className="agent-tag">SEARCH</span>
              </div>

              <div className="agent-connector">
                <ArrowDown size={15} />
              </div>

              <div className="agent-item">
                <div className="agent-icon analyst-icon">
                  <Search size={19} />
                </div>
                <div className="agent-info">
                  <strong>02 · Analyst</strong>
                  <span>Extracts insights from sources</span>
                </div>
                <span className="agent-tag">ANALYZE</span>
              </div>

              <div className="agent-connector">
                <ArrowDown size={15} />
              </div>

              <div className="agent-item">
                <div className="agent-icon writer-icon">
                  <FileText size={19} />
                </div>
                <div className="agent-info">
                  <strong>03 · Writer</strong>
                  <span>Creates the final report</span>
                </div>
                <span className="agent-tag">WRITE</span>
              </div>
            </div>

            <div className="workflow-footer">
              <Workflow size={17} />
              <span>Orchestrated with LangGraph</span>
              <CheckCircle2 size={16} />
            </div>
          </aside>
        </section>

        {loading && (
          <section className="loading-panel panel" aria-live="polite">
            <LoaderCircle className="spin loading-icon" size={27} />
            <div>
              <h3>Your research is in progress</h3>
              <p>
                The agents are gathering sources, analyzing information, and
                preparing your report. This may take a little while.
              </p>
            </div>
          </section>
        )}

        {result && (
          <section className="results-section" id="results">
            <div className="results-header">
              <div>
                <div className="eyebrow">
                  <CheckCircle2 size={15} />
                  RESEARCH COMPLETED
                </div>
                <h2>Your research report</h2>
                <p className="results-topic">{result.topic || topic}</p>
              </div>
              <div className="completed-badge">
                <CheckCircle2 size={16} />
                Complete
              </div>
            </div>

            <div className="result-stats">
              <div className="stat-card">
                <Globe2 size={19} />
                <div>
                  <strong>{sources.length}</strong>
                  <span>Sources collected</span>
                </div>
              </div>
              <div className="stat-card">
                <Users size={19} />
                <div>
                  <strong>
                    {Array.isArray(result.agents) ? result.agents.length : 3}
                  </strong>
                  <span>Agents involved</span>
                </div>
              </div>
              <div className="stat-card">
                <Clock3 size={19} />
                <div>
                  <strong>Ready</strong>
                  <span>Report generated</span>
                </div>
              </div>
            </div>

            <article className="report-card panel">
              <div className="report-title">
                <div className="heading-icon">
                  <FileText size={20} />
                </div>
                <div>
                  <h3>Research findings</h3>
                  <p>Generated by {result.model || "your AI model"}</p>
                </div>
              </div>
              <div className="report-body">
                {report.trim() ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {report}
                  </ReactMarkdown>
                ) : (
                  <p>
                    The request completed, but the API did not return a report.
                    Please check the backend response and try again.
                  </p>
                )}
              </div>
            </article>

            <div className="sources-panel panel">
              <div className="report-title">
                <div className="heading-icon">
                  <BookOpen size={20} />
                </div>
                <div>
                  <h3>Research sources</h3>
                  <p>Open the original pages to verify the information.</p>
                </div>
              </div>

              {sources.length > 0 ? (
                <div className="source-list">
                  {sources.map((source, index) => {
                    const url = getSourceUrl(source);

                    return (
                      <div className="source-item" key={`${url}-${index}`}>
                        <div className="source-number">
                          {String(index + 1).padStart(2, "0")}
                        </div>
                        <div className="source-info">
                          <strong>{getSourceTitle(source, index)}</strong>
                          {source?.content && (
                            <p>{source.content}</p>
                          )}
                        </div>
                        {url.startsWith("https://") ||
                        url.startsWith("http://") ? (
                          <a
                            className="source-link"
                            href={url}
                            target="_blank"
                            rel="noreferrer"
                            aria-label={`Open ${getSourceTitle(source, index)}`}
                          >
                            <ExternalLink size={17} />
                          </a>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="empty-sources">
                  No source links were returned for this report.
                </p>
              )}
            </div>
          </section>
        )}

        <footer className="page-footer">
          <span>AgentResearch AI</span>
          <span>Built with React, FastAPI, Ollama & LangGraph</span>
        </footer>
      </main>
    </div>
  );
}

export default App;
