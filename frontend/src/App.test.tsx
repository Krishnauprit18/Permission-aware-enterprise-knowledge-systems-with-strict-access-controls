import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const mocks = vi.hoisted(() => ({
  beginLogin: vi.fn().mockResolvedValue(undefined),
  completeLogin: vi.fn().mockResolvedValue(undefined),
  getToken: vi.fn().mockReturnValue(null),
  logout: vi.fn(),
  queryKnowledge: vi.fn(),
}));

vi.mock("./auth/oidc", () => ({
  beginLogin: mocks.beginLogin,
  completeLogin: mocks.completeLogin,
  logout: mocks.logout,
  memoryTokenStore: { get: mocks.getToken },
}));
vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, queryKnowledge: mocks.queryKnowledge };
});

const answer = {
  answer_mode: "INTERNAL" as const,
  citations: [
    {
      classification: "INTERNAL",
      evidence_id: "evidence_1234567890",
      excerpt: "Approved date: September 24.",
      source_locator: ["Release board"],
      source_type: "document",
      source_url: null,
      title: "Acme release board",
      updated_at: "2026-09-08T00:00:00Z",
    },
  ],
  claims: [
    {
      citations: [
        {
          classification: "INTERNAL",
          evidence_id: "evidence_1234567890",
          excerpt: "Approved date: September 24.",
          source_locator: ["Release board"],
          source_type: "document",
          source_url: null,
          title: "Acme release board",
          updated_at: "2026-09-08T00:00:00Z",
        },
      ],
      text: "The approved rollout date is September 24.",
    },
  ],
  conflicts: [],
  message: "Answer grounded in accessible evidence.",
  outcome: "ANSWERED",
  policy_status: "ALLOW_WITH_WARNINGS",
  qualifications: [],
  trace: {
    authorization_fingerprint: "fingerprint",
    evidence_ids: ["evidence_1234567890"],
    model_id: "local-test",
    model_version: "test-v1",
    prompt_version: "v1",
    request_id: "request-123",
  },
  warnings: [
    {
      code: "INTERNAL_CONTENT_PRESENT",
      message:
        "This internal answer may include information that is not customer-shareable.",
      severity: "WARNING",
    },
  ],
};

afterEach(() => {
  cleanup();
  mocks.getToken.mockReturnValue(null);
  vi.clearAllMocks();
  window.history.replaceState({}, "", "/");
});

describe("product workspace", () => {
  it("keeps signed-out users at the authentication boundary", () => {
    render(<App />);
    expect(
      screen.getByRole("heading", { name: "Find the answer you can trust." }),
    ).toBeDefined();
    fireEvent.click(
      screen.getByRole("button", { name: "Sign in with Keycloak" }),
    );
    expect(mocks.beginLogin).toHaveBeenCalledOnce();
  });

  it("submits a mode-bound query and renders safe citations and policy warnings", async () => {
    mocks.getToken.mockReturnValue("memory-only-token");
    mocks.queryKnowledge.mockResolvedValue(answer);
    render(<App />);
    fireEvent.change(
      screen.getByLabelText("Ask across your authorized knowledge"),
      { target: { value: "What is the rollout date?" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() =>
      expect(
        screen.getByText("The approved rollout date is September 24."),
      ).toBeDefined(),
    );
    expect(mocks.queryKnowledge).toHaveBeenCalledWith(
      "What is the rollout date?",
      "INTERNAL",
      "memory-only-token",
    );
    expect(screen.getByText("INTERNAL CONTENT PRESENT")).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: /Why this answer/ }));
    expect(screen.getByText("Approved date: September 24.")).toBeDefined();
    expect(screen.getByText("Request request-123")).toBeDefined();
  });

  it("changes the backend mode instead of relying on a visual-only toggle", async () => {
    mocks.getToken.mockReturnValue("memory-only-token");
    mocks.queryKnowledge.mockResolvedValue({
      ...answer,
      answer_mode: "CUSTOMER_SAFE",
      warnings: [],
    });
    render(<App />);
    fireEvent.change(
      screen.getByLabelText("Ask across your authorized knowledge"),
      { target: { value: "Prepare a customer update" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Customer-safe" }));
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() =>
      expect(mocks.queryKnowledge).toHaveBeenCalledWith(
        "Prepare a customer update",
        "CUSTOMER_SAFE",
        "memory-only-token",
      ),
    );
  });

  it("renders source text as text, not executable markup", async () => {
    mocks.getToken.mockReturnValue("memory-only-token");
    mocks.queryKnowledge.mockResolvedValue({
      ...answer,
      citations: [
        { ...answer.citations[0], excerpt: "<img src=x onerror=alert(1)>" },
      ],
      claims: [
        {
          ...answer.claims[0],
          citations: [
            { ...answer.citations[0], excerpt: "<img src=x onerror=alert(1)>" },
          ],
        },
      ],
    });
    render(<App />);
    fireEvent.change(
      screen.getByLabelText("Ask across your authorized knowledge"),
      { target: { value: "Show source" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() =>
      fireEvent.click(screen.getByRole("button", { name: /Why this answer/ })),
    );
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeDefined();
    expect(document.querySelector("img")).toBeNull();
  });
});
