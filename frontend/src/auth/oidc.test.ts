import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  beginLogin,
  buildAuthorizationUrl,
  completeLogin,
  createMemoryTokenStore,
  logout,
  memoryTokenStore,
  type OidcConfig,
} from "./oidc";

const config: OidcConfig = {
  issuer: "http://localhost:8080/realms/knowledge-local",
  clientId: "knowledge-web-local",
  redirectUri: "http://localhost:5173/auth/callback",
  scopes: ["openid", "profile"],
};

describe("OIDC browser boundary", () => {
  beforeEach(() => {
    clearStorage();
    vi.restoreAllMocks();
  });

  it("builds an S256 authorization-code request", () => {
    const url = new URL(buildAuthorizationUrl(config, "state", "challenge"));
    expect(url.searchParams.get("response_type")).toBe("code");
    expect(url.searchParams.get("code_challenge_method")).toBe("S256");
    expect(url.searchParams.get("code_challenge")).toBe("challenge");
  });

  it("keeps access tokens in memory and expires them", () => {
    const store = createMemoryTokenStore();
    store.set({ accessToken: "synthetic-token", expiresAt: 2_000 });
    expect(store.get(1_999)).toBe("synthetic-token");
    expect(store.get(2_000)).toBeNull();
  });

  it("clears an in-memory token explicitly", () => {
    const store = createMemoryTokenStore();
    store.set({ accessToken: "synthetic-token", expiresAt: 2_000 });
    store.clear();
    expect(store.get(1_000)).toBeNull();
  });

  it("stores transient PKCE state and navigates to Keycloak", async () => {
    const navigate = vi.fn<(url: string) => void>();
    await beginLogin(config, navigate);
    const url = new URL(navigate.mock.calls[0]?.[0] ?? "");
    expect(url.searchParams.get("code_challenge_method")).toBe("S256");
    expect(url.searchParams.get("state")).toBe(
      sessionStorage.getItem("knowledge.oidc.state"),
    );
    expect(sessionStorage.getItem("knowledge.oidc.verifier")).not.toBeNull();
  });

  it("exchanges a valid callback and retains the token only in memory", async () => {
    sessionStorage.setItem("knowledge.oidc.state", "state");
    sessionStorage.setItem("knowledge.oidc.verifier", "verifier");
    window.history.pushState({}, "", "/auth/callback?code=code&state=state");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ access_token: "access-token", expires_in: 60 }),
      }),
    );
    await completeLogin(config);
    expect(memoryTokenStore.get()).toBe("access-token");
    expect(sessionStorage.getItem("knowledge.oidc.verifier")).toBeNull();
    expect(localStorage.length).toBe(0);
  });

  it("rejects callback state and malformed token responses", async () => {
    sessionStorage.setItem("knowledge.oidc.state", "expected");
    sessionStorage.setItem("knowledge.oidc.verifier", "verifier");
    window.history.pushState({}, "", "/auth/callback?code=code&state=wrong");
    await expect(completeLogin(config)).rejects.toThrow(
      "authentication failed",
    );

    window.history.pushState({}, "", "/auth/callback?code=code&state=expected");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) }),
    );
    await expect(completeLogin(config)).rejects.toThrow(
      "authentication failed",
    );

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => null }),
    );
    await expect(completeLogin(config)).rejects.toThrow(
      "authentication failed",
    );
  });

  it("clears memory and navigates through the provider logout endpoint", () => {
    memoryTokenStore.set({
      accessToken: "access-token",
      expiresAt: Date.now() + 60_000,
    });
    const navigate = vi.fn<(url: string) => void>();
    logout(config, navigate);
    expect(memoryTokenStore.get()).toBeNull();
    expect(navigate.mock.calls[0]?.[0]).toContain(
      "/protocol/openid-connect/logout",
    );
  });
});

function clearStorage(): void {
  sessionStorage.clear();
  localStorage.clear();
  memoryTokenStore.clear();
  window.history.replaceState({}, "", "/");
}
