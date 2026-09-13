import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "../proxy";

const BASE = "https://pi.invalid";

async function outcome(path: string): Promise<"redirect" | "401" | "through"> {
  const res = await proxy(new NextRequest(new URL(path, BASE)));
  if (res.status === 401) return "401";
  if (res.status >= 300 && res.status < 400 && res.headers.get("location")) return "redirect";
  return "through";
}

describe("placecards proxy auth", () => {
  it("CONTROL: a known-protected page still redirects", async () => {
    expect(await outcome("/control")).toBe("redirect");
  });

  it("sends /placecards-prototype to login without a session", async () => {
    expect(await outcome("/placecards-prototype")).toBe("redirect");
  });

  it("sends the founder .html alias to login without a session", async () => {
    expect(await outcome("/placecards-prototype.html")).toBe("redirect");
  });
});
