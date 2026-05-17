import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PreflightCheck } from "../PreflightCheck";

describe("PreflightCheck", () => {
  it("renders all 3 checks", () => {
    render(<PreflightCheck mic="ok" network="ok" browser="ok" />);
    expect(screen.getByText(/microphone/i)).toBeInTheDocument();
    expect(screen.getByText(/network/i)).toBeInTheDocument();
    expect(screen.getByText(/browser/i)).toBeInTheDocument();
  });

  it("shows error state for failed check", () => {
    render(<PreflightCheck mic="fail" network="ok" browser="ok" />);
    const micRow = screen.getByText(/microphone/i).closest("li");
    expect(micRow?.textContent).toContain("✗");
  });
});
