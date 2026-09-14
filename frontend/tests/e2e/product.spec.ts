import { expect, test } from "@playwright/test";

test("login, query, and citations stay inside the product boundary", async ({
  page,
}) => {
  await page.route(
    "http://localhost:8080/realms/knowledge-local/protocol/openid-connect/auth**",
    async (route) => {
      const authUrl = new URL(route.request().url());
      const callback = `http://127.0.0.1:4173/auth/callback?code=playwright-code&state=${encodeURIComponent(authUrl.searchParams.get("state") ?? "")}`;
      await route.fulfill({
        status: 302,
        headers: { location: callback },
        body: "",
      });
    },
  );
  await page.route(
    "http://localhost:8080/realms/knowledge-local/protocol/openid-connect/token",
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          access_token: "browser-memory-token",
          expires_in: 300,
        }),
      });
    },
  );
  await page.route(
    "http://localhost:8000/api/v1/knowledge/query",
    async (route) => {
      expect(route.request().headers().authorization).toBe(
        "Bearer browser-memory-token",
      );
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          answer_mode: "INTERNAL",
          citations: [
            {
              classification: "INTERNAL",
              evidence_id: "e2e-evidence",
              excerpt: "Approved rollout is September 24.",
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
                  evidence_id: "e2e-evidence",
                  excerpt: "Approved rollout is September 24.",
                  source_locator: ["Release board"],
                  source_type: "document",
                  source_url: null,
                  title: "Acme release board",
                  updated_at: "2026-09-08T00:00:00Z",
                },
              ],
              text: "The approved rollout is September 24.",
            },
          ],
          conflicts: [],
          message: "Answer grounded in accessible evidence.",
          outcome: "ANSWERED",
          policy_status: "ALLOW",
          qualifications: [],
          trace: {
            authorization_fingerprint: "e2e-fingerprint",
            evidence_ids: ["e2e-evidence"],
            model_id: "local-e2e",
            model_version: "test",
            prompt_version: "v1",
            request_id: "e2e-request",
          },
          warnings: [],
        }),
      });
    },
  );

  await page.goto("/");
  await page.getByRole("button", { name: "Sign in with Keycloak" }).click();
  await expect(
    page.getByRole("heading", { name: "Evidence workspace" }),
  ).toBeVisible();
  await page
    .getByLabel("Ask across your authorized knowledge")
    .fill("What is the approved rollout?");
  await page.getByRole("button", { name: "Ask" }).click();
  await expect(
    page.getByText("The approved rollout is September 24."),
  ).toBeVisible();
  await page.getByRole("button", { name: /Why this answer/ }).click();
  await expect(
    page.getByText("Approved rollout is September 24.", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Request e2e-request")).toBeVisible();
});
