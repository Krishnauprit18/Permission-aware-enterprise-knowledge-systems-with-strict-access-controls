/** Browser-side Authorization Code + PKCE client with memory-only tokens. */

export interface OidcConfig {
  issuer: string;
  clientId: string;
  redirectUri: string;
  scopes: string[];
}

export interface AccessTokenSet {
  accessToken: string;
  expiresAt: number;
}

export interface MemoryTokenStore {
  clear(): void;
  get(now?: number): string | null;
  set(tokens: AccessTokenSet): void;
}

const stateStorageKey = "knowledge.oidc.state";
const verifierStorageKey = "knowledge.oidc.verifier";

export function createMemoryTokenStore(): MemoryTokenStore {
  let tokens: AccessTokenSet | null = null;
  return {
    clear: (): void => {
      tokens = null;
    },
    get: (now = Date.now()): string | null => {
      if (tokens === null || tokens.expiresAt <= now) {
        tokens = null;
        return null;
      }
      return tokens.accessToken;
    },
    set: (nextTokens): void => {
      tokens = nextTokens;
    },
  };
}

export const memoryTokenStore = createMemoryTokenStore();

export function buildAuthorizationUrl(
  config: OidcConfig,
  state: string,
  codeChallenge: string,
): string {
  const url = new URL(`${config.issuer}/protocol/openid-connect/auth`);
  url.search = new URLSearchParams({
    client_id: config.clientId,
    code_challenge: codeChallenge,
    code_challenge_method: "S256",
    redirect_uri: config.redirectUri,
    response_type: "code",
    scope: config.scopes.join(" "),
    state,
  }).toString();
  return url.toString();
}

export async function beginLogin(
  config: OidcConfig,
  navigate: (url: string) => void = /* c8 ignore next */ (url) =>
    window.location.assign(url),
): Promise<void> {
  const verifier = randomString();
  const challenge = await sha256Base64Url(verifier);
  const state = randomString();
  sessionStorage.setItem(stateStorageKey, state);
  sessionStorage.setItem(verifierStorageKey, verifier);
  navigate(buildAuthorizationUrl(config, state, challenge));
}

export async function completeLogin(config: OidcConfig): Promise<void> {
  const query = new URLSearchParams(window.location.search);
  const code = query.get("code");
  const returnedState = query.get("state");
  const expectedState = sessionStorage.getItem(stateStorageKey);
  const verifier = sessionStorage.getItem(verifierStorageKey);
  if (
    code === null ||
    returnedState === null ||
    returnedState !== expectedState ||
    verifier === null
  ) {
    throw new Error("authentication failed");
  }
  const response = await fetch(
    `${config.issuer}/protocol/openid-connect/token`,
    {
      body: new URLSearchParams({
        client_id: config.clientId,
        code,
        code_verifier: verifier,
        grant_type: "authorization_code",
        redirect_uri: config.redirectUri,
      }),
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      method: "POST",
    },
  );
  if (!response.ok) {
    throw new Error("authentication failed");
  }
  const body: unknown = await response.json();
  if (!isTokenResponse(body)) {
    throw new Error("authentication failed");
  }
  memoryTokenStore.set({
    accessToken: body.access_token,
    expiresAt: Date.now() + body.expires_in * 1000,
  });
  sessionStorage.removeItem(stateStorageKey);
  sessionStorage.removeItem(verifierStorageKey);
  window.history.replaceState({}, document.title, "/");
}

export function clearLogin(): void {
  memoryTokenStore.clear();
  sessionStorage.removeItem(stateStorageKey);
  sessionStorage.removeItem(verifierStorageKey);
}

export function logout(
  config: OidcConfig,
  navigate: (url: string) => void = /* c8 ignore next */ (url) =>
    window.location.assign(url),
): void {
  clearLogin();
  const url = new URL(`${config.issuer}/protocol/openid-connect/logout`);
  url.search = new URLSearchParams({
    client_id: config.clientId,
    post_logout_redirect_uri: config.redirectUri.replace("/auth/callback", "/"),
  }).toString();
  navigate(url.toString());
}

function randomString(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return base64Url(bytes);
}

async function sha256Base64Url(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  return base64Url(
    new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
  );
}

function base64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary)
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replaceAll("=", "");
}

function isTokenResponse(
  value: unknown,
): value is { access_token: string; expires_in: number } {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    typeof record.access_token === "string" &&
    record.access_token.length > 0 &&
    typeof record.expires_in === "number" &&
    Number.isFinite(record.expires_in) &&
    record.expires_in > 0
  );
}
