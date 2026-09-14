import { describe, expect, it, vi } from "vitest";
import { ApiError, queryKnowledge } from "./api";

const validBody = {
  answer_mode: "CUSTOMER_SAFE",
  citations: [
    {
      classification: "PUBLIC",
      evidence_id: "e1",
      excerpt: "Safe excerpt",
      source_locator: ["Policy", "section:1"],
      source_type: "document",
      source_url: null,
      title: "Customer policy",
      updated_at: "2026-09-01T00:00:00Z",
    },
  ],
  claims: [
    {
      citations: [
        {
          classification: "PUBLIC",
          evidence_id: "e1",
          excerpt: "Safe excerpt",
          source_locator: ["Policy", "section:1"],
          source_type: "document",
          source_url: null,
          title: "Customer policy",
          updated_at: "2026-09-01T00:00:00Z",
        },
      ],
      text: "The policy is current.",
    },
  ],
  conflicts: [
    { evidence_ids: ["e1", "e2"], most_authoritative_evidence_id: "e1" },
  ],
  message: "Answer grounded in accessible evidence.",
  outcome: "ANSWERED",
  policy_status: "ALLOW",
  qualifications: [
    { decision_status: "APPROVED", evidence_id: "e1", freshness: "CURRENT" },
  ],
  trace: {
    authorization_fingerprint: "f",
    evidence_ids: ["e1"],
    model_id: "local",
    model_version: "v1",
    prompt_version: "v1",
    request_id: "r1",
  },
  warnings: [
    {
      code: "CUSTOMER_SAFE_POLICY_APPLIED",
      message: "Customer-safe policy applied.",
      severity: "INFO",
    },
  ],
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("product API client", () => {
  it("validates and returns the complete typed response", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(response(validBody));
    const result = await queryKnowledge(
      "question",
      "CUSTOMER_SAFE",
      "memory-token",
      fetchImpl,
    );
    expect(result.answer_mode).toBe("CUSTOMER_SAFE");
    expect(result.citations[0]?.title).toBe("Customer policy");
    expect(fetchImpl).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/knowledge/query",
      expect.objectContaining({ method: "POST" }),
    );
    const linkedBody = {
      ...validBody,
      citations: [
        {
          ...validBody.citations[0],
          source_url: "https://docs.example.invalid/policy",
        },
      ],
      claims: [
        {
          ...validBody.claims[0],
          citations: [
            {
              ...validBody.claims[0]!.citations[0]!,
              source_url: "https://docs.example.invalid/policy",
            },
          ],
        },
      ],
    };
    const linked = await queryKnowledge(
      "question",
      "CUSTOMER_SAFE",
      "memory-token",
      vi.fn().mockResolvedValue(response(linkedBody)),
    );
    expect(linked.citations[0]?.source_url).toBe(
      "https://docs.example.invalid/policy",
    );
  });

  it("turns service failures into a generic error with request ID", async () => {
    await expect(
      queryKnowledge(
        "question",
        "INTERNAL",
        "memory-token",
        vi
          .fn()
          .mockResolvedValue(
            response(
              { code: "QUERY_SERVICE_UNAVAILABLE", request_id: "r2" },
              503,
            ),
          ),
      ),
    ).rejects.toMatchObject({
      code: "QUERY_SERVICE_UNAVAILABLE",
      requestId: "r2",
    });
  });

  it("rejects malformed success payloads and non-object errors", async () => {
    await expect(
      queryKnowledge(
        "question",
        "INTERNAL",
        "memory-token",
        vi.fn().mockResolvedValue(response({ outcome: "ANSWERED" })),
      ),
    ).rejects.toBeInstanceOf(ApiError);
    await expect(
      queryKnowledge(
        "question",
        "INTERNAL",
        "memory-token",
        vi.fn().mockResolvedValue(response("bad", 500)),
      ),
    ).rejects.toMatchObject({ code: "REQUEST_FAILED", requestId: "unknown" });
    await expect(
      queryKnowledge(
        "question",
        "INTERNAL",
        "memory-token",
        vi
          .fn()
          .mockResolvedValue(response({ ...validBody, answer_mode: "OTHER" })),
      ),
    ).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });
});
