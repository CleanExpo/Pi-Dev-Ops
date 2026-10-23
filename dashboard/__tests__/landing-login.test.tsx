/**
 * / landing page — sign-in surface.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("next/image", () => ({
  // eslint-disable-next-line @next/next/no-img-element
  default: ({ alt, src }: { alt: string; src: string }) => <img alt={alt} src={src} />,
}));

import LandingPage from "@/app/page";

afterEach(() => cleanup());

describe("landing page", () => {
  it("does not advertise a stale model name", () => {
    render(<LandingPage />);
    expect(document.body.textContent).not.toMatch(/OPUS 4\.8/i);
  });
});
