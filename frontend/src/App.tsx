import type { JSX } from "react";
import { FormEvent, useEffect, useState } from "react";

import {
  ApiError,
  queryKnowledge,
  type AnswerMode,
  type QueryResponse,
} from "./api";
import {
  beginLogin,
  completeLogin,
  logout,
  memoryTokenStore,
  type OidcConfig,
} from "./auth/oidc";
import "./styles.css";

const oidcConfig: OidcConfig = {
  issuer: "http://localhost:8080/realms/knowledge-local",
  clientId: "knowledge-web-local",
  redirectUri: `${window.location.origin}/auth/callback`,
  scopes: ["openid", "profile", "email"],
};

interface HistoryItem {
  question: string;
  mode: AnswerMode;
  response: QueryResponse | null;
}

export default function App(): JSX.Element {
  const [authenticated, setAuthenticated] = useState(
    memoryTokenStore.get() !== null,
  );
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<AnswerMode>("INTERNAL");
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showWhy, setShowWhy] = useState(false);

  useEffect(() => {
    if (window.location.pathname !== "/auth/callback") return;
    void completeLogin(oidcConfig)
      .then(() => setAuthenticated(true))
      .catch(() => setAuthenticated(false));
  }, []);

  if (!authenticated) {
    return (
      <main className="signed-out-shell">
        <section className="signed-out-panel" aria-labelledby="sign-in-title">
          <span className="eyebrow">NORTHSTAR KNOWLEDGE</span>
          <h1 id="sign-in-title">Find the answer you can trust.</h1>
          <p>
            Search authorized enterprise evidence with citations and clear
            policy boundaries.
          </p>
          <button
            className="primary-button"
            type="button"
            onClick={() => void beginLogin(oidcConfig)}
          >
            Sign in with Keycloak
          </button>
          <p className="quiet-copy">
            Local workspace · permission-aware · evidence first
          </p>
        </section>
      </main>
    );
  }

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || loading) return;
    const token = memoryTokenStore.get();
    if (token === null) {
      setAuthenticated(false);
      return;
    }
    setLoading(true);
    setError(null);
    setShowWhy(false);
    try {
      const nextResponse = await queryKnowledge(trimmed, mode, token);
      setResponse(nextResponse);
      setHistory((current) =>
        [{ question: trimmed, mode, response: nextResponse }, ...current].slice(
          0,
          8,
        ),
      );
    } catch (caught: unknown) {
      setError(
        caught instanceof ApiError && caught.requestId !== "unknown"
          ? `${caught.message} Request ID: ${caught.requestId}`
          : "The knowledge service could not complete that request.",
      );
      setResponse(null);
    } finally {
      setLoading(false);
    }
  };

  const signOut = (): void => {
    logout(oidcConfig);
    setAuthenticated(false);
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <span className="eyebrow">NORTHSTAR KNOWLEDGE</span>
          <h1>Evidence workspace</h1>
        </div>
        <button className="quiet-button" type="button" onClick={signOut}>
          Sign out
        </button>
      </header>
      <div className="workspace-grid">
        <aside className="history-panel" aria-label="Question history">
          <div className="panel-heading">
            <span>Recent questions</span>
            <span className="count-badge">{history.length}</span>
          </div>
          {history.length === 0 ? (
            <p className="empty-copy">
              Your recent questions will appear here.
            </p>
          ) : (
            <ul className="history-list">
              {history.map((item, index) => (
                <li key={`${item.question}-${index}`}>
                  <button
                    type="button"
                    onClick={() => {
                      setQuestion(item.question);
                      setMode(item.mode);
                      setResponse(item.response);
                    }}
                  >
                    <span>{item.question}</span>
                    <small>
                      {item.mode === "CUSTOMER_SAFE"
                        ? "Customer-safe"
                        : "Internal"}
                    </small>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
        <section className="query-column" aria-label="Knowledge query">
          <form className="query-form" onSubmit={(event) => void submit(event)}>
            <label htmlFor="question">
              Ask across your authorized knowledge
            </label>
            <textarea
              id="question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              maxLength={2000}
              placeholder="What should I know about the Acme rollout?"
              rows={4}
            />
            <div className="query-controls">
              <div
                className="mode-control"
                role="group"
                aria-label="Answer mode"
              >
                <button
                  type="button"
                  className={
                    mode === "INTERNAL" ? "mode-button selected" : "mode-button"
                  }
                  aria-pressed={mode === "INTERNAL"}
                  onClick={() => setMode("INTERNAL")}
                >
                  Internal
                </button>
                <button
                  type="button"
                  className={
                    mode === "CUSTOMER_SAFE"
                      ? "mode-button selected"
                      : "mode-button"
                  }
                  aria-pressed={mode === "CUSTOMER_SAFE"}
                  onClick={() => setMode("CUSTOMER_SAFE")}
                >
                  Customer-safe
                </button>
              </div>
              <span className="character-count">{question.length}/2,000</span>
              <button
                className="primary-button ask-button"
                type="submit"
                disabled={!question.trim() || loading}
              >
                {loading ? "Searching…" : "Ask"}
              </button>
            </div>
          </form>
          {error !== null && (
            <div className="error-banner" role="alert">
              {error}
            </div>
          )}
          {response !== null ? (
            <AnswerView
              response={response}
              showWhy={showWhy}
              setShowWhy={setShowWhy}
            />
          ) : (
            <EmptyAnswer />
          )}
        </section>
      </div>
    </main>
  );
}

function EmptyAnswer(): JSX.Element {
  return (
    <section className="answer-empty">
      <span className="empty-mark">⌁</span>
      <h2>Your answer will appear here</h2>
      <p>
        Ask a focused question to see authorized evidence, citations, and policy
        context.
      </p>
    </section>
  );
}

function AnswerView({
  response,
  showWhy,
  setShowWhy,
}: {
  response: QueryResponse;
  showWhy: boolean;
  setShowWhy: (value: boolean) => void;
}): JSX.Element {
  const answered = response.outcome === "ANSWERED";
  return (
    <article className="answer-panel">
      <div className="answer-meta">
        <span className={answered ? "status-pill answered" : "status-pill"}>
          {answered ? "Grounded answer" : "No answer"}
        </span>
        <span>
          {response.answer_mode === "CUSTOMER_SAFE"
            ? "Customer-safe mode"
            : "Internal mode"}
        </span>
        <span className="trace-label">Request {response.trace.request_id}</span>
      </div>
      <h2>{answered ? "Answer" : "Accessible evidence is insufficient"}</h2>
      <p className="answer-message">{response.message}</p>
      {response.warnings.map((warning) => (
        <div
          className={`warning-banner ${warning.severity.toLowerCase()}`}
          key={warning.code}
        >
          <strong>{warning.code.replaceAll("_", " ")}</strong>
          <span>{warning.message}</span>
        </div>
      ))}
      {response.claims.map((claim, index) => (
        <div className="claim" key={`${claim.text}-${index}`}>
          <p>{claim.text}</p>
          <div className="claim-citations">
            {claim.citations.map((citation) => (
              <CitationChip citation={citation} key={citation.evidence_id} />
            ))}
          </div>
        </div>
      ))}
      {response.conflicts.length > 0 && (
        <div className="signal-panel conflict">
          <strong>Conflicting evidence retained</strong>
          <span>
            {response.conflicts.length} conflict group
            {response.conflicts.length === 1 ? "" : "s"} were considered. The
            authoritative source is identified in the evidence view.
          </span>
        </div>
      )}
      {response.qualifications.some((item) => item.freshness !== "CURRENT") && (
        <div className="signal-panel stale">
          <strong>Freshness qualification</strong>
          <span>
            Some cited evidence is stale or superseded. Review the evidence
            details before acting.
          </span>
        </div>
      )}
      <button
        type="button"
        className="why-button"
        onClick={() => setShowWhy(!showWhy)}
        aria-expanded={showWhy}
      >
        Why this answer? <span>{showWhy ? "−" : "+"}</span>
      </button>
      {showWhy && <EvidenceView response={response} />}
    </article>
  );
}

function CitationChip({
  citation,
}: {
  citation: QueryResponse["citations"][number];
}): JSX.Element {
  return (
    <span className="citation-chip" title={citation.excerpt}>
      [{citation.evidence_id.slice(0, 14)}]
    </span>
  );
}

function EvidenceView({ response }: { response: QueryResponse }): JSX.Element {
  return (
    <section className="evidence-view" aria-label="Answer evidence">
      <div className="evidence-heading">
        <div>
          <span className="eyebrow">PROVENANCE</span>
          <h3>Evidence used</h3>
        </div>
        <span className="evidence-count">
          {response.citations.length} source
          {response.citations.length === 1 ? "" : "s"}
        </span>
      </div>
      <p className="quiet-copy">
        This view shows backend-selected evidence and policy metadata. It does
        not expose model reasoning.
      </p>
      {response.citations.map((citation) => (
        <article className="evidence-item" key={citation.evidence_id}>
          <div className="evidence-title">
            <strong>{citation.title}</strong>
            <span>{citation.source_type}</span>
          </div>
          <div className="evidence-details">
            <span>{citation.classification}</span>
            <time dateTime={citation.updated_at}>
              {formatDate(citation.updated_at)}
            </time>
          </div>
          <blockquote>{citation.excerpt}</blockquote>
          {citation.source_locator.length > 0 && (
            <small>Locator: {citation.source_locator.join(" / ")}</small>
          )}
        </article>
      ))}
    </section>
  );
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Date unavailable"
    : new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date);
}
