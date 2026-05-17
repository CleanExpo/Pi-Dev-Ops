import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConnectionStatus } from "../ConnectionStatus";

describe("ConnectionStatus", () => {
  it("renders Reconnecting banner when state is reconnecting", () => {
    render(<ConnectionStatus state="reconnecting" />);
    expect(screen.getByText(/Reconnecting/i)).toBeInTheDocument();
  });

  it("renders nothing when state is connected", () => {
    const { container } = render(<ConnectionStatus state="connected" />);
    expect(container.firstChild).toBeNull();
  });

  it("renders error banner when state is error", () => {
    render(<ConnectionStatus state="error" message="Network unreachable" />);
    expect(screen.getByText(/Network unreachable/)).toBeInTheDocument();
  });
});
