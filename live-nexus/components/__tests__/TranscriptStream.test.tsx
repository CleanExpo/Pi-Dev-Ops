import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TranscriptStream } from "../TranscriptStream";

describe("TranscriptStream", () => {
  it("renders finalized transcript lines with timestamps", () => {
    render(
      <TranscriptStream
        lines={[
          { timestamp: "14:28", speaker: "A", text: "hello there" },
          { timestamp: "14:30", speaker: "B", text: "how are you" },
        ]}
        partial=""
      />
    );
    expect(screen.getByText(/hello there/)).toBeInTheDocument();
    expect(screen.getByText(/how are you/)).toBeInTheDocument();
    expect(screen.getByText(/Speaker A/i)).toBeInTheDocument();
  });

  it("renders partial transcript with live cursor", () => {
    const { container } = render(
      <TranscriptStream lines={[]} partial="this is being said" />
    );
    expect(screen.getByText(/this is being said/)).toBeInTheDocument();
    expect(container.querySelector(".live-cursor")).toBeTruthy();
  });

  it("does not render cursor when no partial", () => {
    const { container } = render(
      <TranscriptStream
        lines={[{ timestamp: "14:28", speaker: "A", text: "done" }]}
        partial=""
      />
    );
    expect(container.querySelector(".live-cursor")).toBeFalsy();
  });

  it("renders empty state when no lines and no partial", () => {
    render(<TranscriptStream lines={[]} partial="" />);
    expect(screen.getByText(/listening/i)).toBeInTheDocument();
  });
});
