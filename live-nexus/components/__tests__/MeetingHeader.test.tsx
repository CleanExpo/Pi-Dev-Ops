import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MeetingHeader } from "../MeetingHeader";

describe("MeetingHeader", () => {
  it("shows brand wordmark", () => {
    render(<MeetingHeader state="recording" elapsedSeconds={0} clockTime="14:32" />);
    expect(screen.getByText(/UNITE GROUP NEXUS/i)).toBeInTheDocument();
  });

  it("renders elapsed timer in mm:ss for short meetings", () => {
    render(<MeetingHeader state="recording" elapsedSeconds={62} clockTime="14:33" />);
    expect(screen.getByText("01:02")).toBeInTheDocument();
  });

  it("renders elapsed timer in h:mm:ss for long meetings", () => {
    render(<MeetingHeader state="recording" elapsedSeconds={3725} clockTime="14:33" />);
    expect(screen.getByText("1:02:05")).toBeInTheDocument();
  });

  it("LIVE dot is animated in recording state", () => {
    const { container } = render(
      <MeetingHeader state="recording" elapsedSeconds={0} clockTime="14:32" />
    );
    const dot = container.querySelector(".live-dot");
    expect(dot).toBeTruthy();
    expect(dot?.classList.contains("live-dot--paused")).toBe(false);
  });

  it("LIVE dot is paused (grey) when state is ended", () => {
    const { container } = render(
      <MeetingHeader state="ended" elapsedSeconds={3600} clockTime="14:32" />
    );
    const dot = container.querySelector(".live-dot--paused");
    expect(dot).toBeTruthy();
  });
});
