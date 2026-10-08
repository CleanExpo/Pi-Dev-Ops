import { timingSafeEqual } from "node:crypto";

/** Constant-time bearer check. Missing and wrong tokens both fail. */
export function bearerOk(authorization, token) {
  const match = /^Bearer\s+(\S+)\s*$/i.exec(String(authorization || ""));
  if (!match || !token) return false;
  const given = Buffer.from(match[1]);
  const want = Buffer.from(token);
  if (given.length !== want.length) return false;
  return timingSafeEqual(given, want);
}

export function unauthorized(res) {
  res
    .status(401)
    .set("WWW-Authenticate", 'Bearer realm="estate-mcp"')
    .json({ error: "unauthorized" });
}
