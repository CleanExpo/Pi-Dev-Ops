import { timingSafeEqual } from "node:crypto";

export const MIN_TOKEN_LENGTH = 16;

/** A missing or short token means the server is misconfigured and must fail closed. */
export function configuredToken(raw) {
  const token = String(raw || "").trim();
  if (token.length < MIN_TOKEN_LENGTH) return "";
  return token;
}

export function bearerMatches(header, expected) {
  const token = configuredToken(expected);
  if (!token) return false;
  if (typeof header !== "string" || !header.startsWith("Bearer ")) return false;
  const presented = header.slice("Bearer ".length);
  if (presented.length !== token.length || presented.length > 512) return false;
  return timingSafeEqual(Buffer.from(presented), Buffer.from(token));
}
