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
}));

vi.mock("./auth/oidc", () => ({
  beginLogin: mocks.beginLogin,
  completeLogin: mocks.completeLogin,
  logout: mocks.logout,
  memoryTokenStore: { get: mocks.getToken },
}));

afterEach(() => {
  cleanup();
  mocks.getToken.mockReturnValue(null);
  vi.clearAllMocks();
  window.history.replaceState({}, "", "/");
});

describe("scaffold application", () => {
  it("renders its health-check surface", () => {
    render(<App />);
    expect(
      screen.getByRole("heading", { name: "Knowledge system scaffold" }),
    ).toBeDefined();
  });

  it("starts the login flow from the sign-in control", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(mocks.beginLogin).toHaveBeenCalledOnce();
  });

  it("clears the authenticated session from the sign-out control", () => {
    mocks.getToken.mockReturnValue("access-token");
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(mocks.logout).toHaveBeenCalledOnce();
    mocks.getToken.mockReturnValue(null);
  });

  it("shows the authenticated state after a successful callback", async () => {
    window.history.pushState({}, "", "/auth/callback");
    render(<App />);
    await waitFor(() => {
      expect(mocks.completeLogin).toHaveBeenCalledOnce();
      expect(screen.getByRole("button", { name: "Sign out" })).toBeDefined();
    });
  });

  it("returns to signed-out state when the callback fails", async () => {
    mocks.completeLogin.mockRejectedValueOnce(new Error("invalid callback"));
    window.history.pushState({}, "", "/auth/callback");
    render(<App />);
    await waitFor(() => {
      expect(mocks.completeLogin).toHaveBeenCalledOnce();
      expect(screen.getByRole("button", { name: "Sign in" })).toBeDefined();
    });
  });
});
