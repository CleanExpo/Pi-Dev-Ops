import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SynthesisSidebar } from "../SynthesisSidebar";

describe("SynthesisSidebar", () => {
  it("renders topics list", () => {
    render(
      <SynthesisSidebar
        topics={["Q2 pricing", "Onboarding"]}
        actions={[]}
        synthesisPaused={false}
      />
    );
    expect(screen.getByText(/Q2 pricing/i)).toBeInTheDocument();
    expect(screen.getByText(/Onboarding/i)).toBeInTheDocument();
  });

  it("renders actions with description + priority badge", () => {
    render(
      <SynthesisSidebar
        topics={[]}
        actions={[
          { title: "Send proposal", description: "by Friday", priority: 2 },
          { title: "Review numbers", description: "", priority: 4 },
        ]}
        synthesisPaused={false}
      />
    );
    expect(screen.getByText(/Send proposal/i)).toBeInTheDocument();
    expect(screen.getByText(/by Friday/i)).toBeInTheDocument();
    expect(screen.getByText(/HIGH/i)).toBeInTheDocument();
    expect(screen.getByText(/LOW/i)).toBeInTheDocument();
  });

  it("renders synthesis-paused pill when paused", () => {
    render(<SynthesisSidebar topics={[]} actions={[]} synthesisPaused={true} />);
    expect(screen.getByText(/synthesis paused/i)).toBeInTheDocument();
  });

  it("renders empty-state when no data", () => {
    render(<SynthesisSidebar topics={[]} actions={[]} synthesisPaused={false} />);
    expect(screen.getAllByText(/none yet/i).length).toBeGreaterThan(0);
  });
});
