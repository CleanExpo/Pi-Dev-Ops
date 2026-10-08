import fs from "node:fs";
import path from "node:path";

/** Append-only audit log. One chain so lines are not interleaved. */
export function createAudit(dir) {
  fs.mkdirSync(dir, { recursive: true });
  const file = path.join(dir, "audit.jsonl");
  let chain = Promise.resolve();

  function record(entry) {
    const line = `${JSON.stringify({ ts: new Date().toISOString(), ...entry })}\n`;
    const run = chain.then(() => fs.promises.appendFile(file, line, "utf8"));
    chain = run.then(() => undefined, () => undefined);
    return run.then(() => undefined);
  }

  return { file, record };
}
