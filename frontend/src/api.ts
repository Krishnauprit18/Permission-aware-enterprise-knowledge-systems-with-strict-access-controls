export type AnswerMode = "INTERNAL" | "CUSTOMER_SAFE";

export interface Citation {
  evidence_id: string;
  title: string;
  source_type: string;
  source_locator: string[];
  source_url: string | null;
  updated_at: string;
  classification: string;
  excerpt: string;
}

export interface Claim {
  text: string;
  citations: Citation[];
}

export interface QueryResponse {
  outcome: string;
  message: string;
  answer_mode: AnswerMode;
  policy_status: string;
  claims: Claim[];
  citations: Citation[];
  conflicts: Array<{
    evidence_ids: string[];
    most_authoritative_evidence_id: string;
  }>;
  qualifications: Array<{
    evidence_id: string;
    decision_status: string;
    freshness: string;
  }>;
  warnings: Array<{ code: string; severity: string; message: string }>;
  trace: {
    request_id: string;
    authorization_fingerprint: string;
    evidence_ids: string[];
    prompt_version: string;
    model_id: string;
    model_version: string;
  };
}

export class ApiError extends Error {
  readonly code: string;
  readonly requestId: string;

  constructor(code: string, message: string, requestId: string) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.requestId = requestId;
  }
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function queryKnowledge(
  question: string,
  mode: AnswerMode,
  token: string,
  fetchImpl: typeof fetch = fetch,
): Promise<QueryResponse> {
  const response = await fetchImpl(`${apiBaseUrl}/api/v1/knowledge/query`, {
    body: JSON.stringify({ question, mode }),
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    method: "POST",
  });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const errorBody = isRecord(body) ? body : {};
    throw new ApiError(
      readString(errorBody, "code", "REQUEST_FAILED"),
      "The knowledge service could not complete that request.",
      readString(errorBody, "request_id", "unknown"),
    );
  }
  return parseQueryResponse(body);
}

function parseQueryResponse(value: unknown): QueryResponse {
  const record = recordValue(value);
  return {
    answer_mode: readAnswerMode(record.answer_mode),
    citations: readArray(record.citations, parseCitation),
    claims: readArray(record.claims, parseClaim),
    conflicts: readArray(record.conflicts, (item) => {
      const itemRecord = recordValue(item);
      return {
        evidence_ids: stringArray(itemRecord.evidence_ids),
        most_authoritative_evidence_id: readString(
          itemRecord,
          "most_authoritative_evidence_id",
        ),
      };
    }),
    message: readString(record, "message"),
    outcome: readString(record, "outcome"),
    policy_status: readString(record, "policy_status"),
    qualifications: readArray(record.qualifications, (item) => {
      const itemRecord = recordValue(item);
      return {
        decision_status: readString(itemRecord, "decision_status"),
        evidence_id: readString(itemRecord, "evidence_id"),
        freshness: readString(itemRecord, "freshness"),
      };
    }),
    trace: parseTrace(record.trace),
    warnings: readArray(record.warnings, (item) => {
      const itemRecord = recordValue(item);
      return {
        code: readString(itemRecord, "code"),
        message: readString(itemRecord, "message"),
        severity: readString(itemRecord, "severity"),
      };
    }),
  };
}

function parseClaim(value: unknown): Claim {
  const record = recordValue(value);
  return {
    citations: readArray(record.citations, parseCitation),
    text: readString(record, "text"),
  };
}

function parseCitation(value: unknown): Citation {
  const record = recordValue(value);
  return {
    classification: readString(record, "classification"),
    evidence_id: readString(record, "evidence_id"),
    excerpt: readString(record, "excerpt"),
    source_locator: stringArray(record.source_locator),
    source_type: readString(record, "source_type"),
    source_url: nullableString(record.source_url),
    title: readString(record, "title"),
    updated_at: readString(record, "updated_at"),
  };
}

function parseTrace(value: unknown): QueryResponse["trace"] {
  const record = recordValue(value);
  return {
    authorization_fingerprint: readString(record, "authorization_fingerprint"),
    evidence_ids: stringArray(record.evidence_ids),
    model_id: readString(record, "model_id"),
    model_version: readString(record, "model_version"),
    prompt_version: readString(record, "prompt_version"),
    request_id: readString(record, "request_id"),
  };
}

function readArray<T>(value: unknown, parser: (item: unknown) => T): T[] {
  if (!Array.isArray(value)) throw invalidResponse();
  return value.map(parser);
}
function stringArray(value: unknown): string[] {
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string"))
    throw invalidResponse();
  return value;
}
function readAnswerMode(value: unknown): AnswerMode {
  if (value === "INTERNAL" || value === "CUSTOMER_SAFE") return value;
  throw invalidResponse();
}
function readString(
  record: Record<string, unknown>,
  key: string,
  fallback?: string,
): string {
  const value = record[key];
  if (typeof value === "string") return value;
  if (fallback !== undefined) return fallback;
  throw invalidResponse();
}
function nullableString(value: unknown): string | null {
  if (value === null || typeof value === "string") return value;
  throw invalidResponse();
}
function recordValue(value: unknown): Record<string, unknown> {
  if (!isRecord(value)) throw invalidResponse();
  return value;
}
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function invalidResponse(): ApiError {
  return new ApiError(
    "INVALID_RESPONSE",
    "The knowledge service returned an invalid response.",
    "unknown",
  );
}
