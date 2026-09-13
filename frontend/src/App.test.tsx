import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("scaffold application", () => {
  it("renders its health-check surface", () => {
    render(<App />);
    expect(
      screen.getByRole("heading", { name: "Knowledge system scaffold" }),
    ).toBeDefined();
  });
});
