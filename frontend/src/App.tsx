import type { JSX } from "react";
import { useEffect, useState } from "react";

import {
  beginLogin,
  completeLogin,
  logout,
  memoryTokenStore,
  type OidcConfig,
} from "./auth/oidc";

const oidcConfig: OidcConfig = {
  issuer: "http://localhost:8080/realms/knowledge-local",
  clientId: "knowledge-web-local",
  redirectUri: `${window.location.origin}/auth/callback`,
  scopes: ["openid", "profile", "email"],
};

export default function App(): JSX.Element {
  const [authenticated, setAuthenticated] = useState(
    memoryTokenStore.get() !== null,
  );

  useEffect(() => {
    if (window.location.pathname !== "/auth/callback") {
      return;
    }
    void completeLogin(oidcConfig)
      .then(() => setAuthenticated(true))
      .catch(() => setAuthenticated(false));
  }, []);

  const startLogin = (): void => {
    void beginLogin(oidcConfig);
  };

  return (
    <main>
      <h1>Knowledge system scaffold</h1>
      <p>Repository quality gates are ready for product implementation.</p>
      {authenticated ? (
        <button type="button" onClick={() => logout(oidcConfig)}>
          Sign out
        </button>
      ) : (
        <button type="button" onClick={startLogin}>
          Sign in
        </button>
      )}
    </main>
  );
}
