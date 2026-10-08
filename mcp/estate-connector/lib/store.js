import fs from "node:fs";
import path from "node:path";

const EMPTY = () => ({ notes: [], queue: [] });

function readState(file) {
  try {
    const parsed = JSON.parse(fs.readFileSync(file, "utf8"));
    return {
      notes: Array.isArray(parsed.notes) ? parsed.notes : [],
      queue: Array.isArray(parsed.queue) ? parsed.queue : [],
    };
  } catch {
    return EMPTY();
  }
}

function atomicWrite(file, state) {
  const tmp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(state));
  fs.renameSync(tmp, file);
}

/** File-backed notes and queue. One chain so two bots cannot overwrite each other. */
export function createStore(dir) {
  fs.mkdirSync(dir, { recursive: true });
  const file = path.join(dir, "state.json");
  let chain = Promise.resolve();

  function withState(mutator, write) {
    const run = chain.then(async () => {
      const state = readState(file);
      const result = mutator(state);
      if (write) atomicWrite(file, state);
      return result;
    });
    chain = run.then(() => undefined, () => undefined);
    return run;
  }

  return {
    read(mutator) {
      return withState(mutator, false);
    },
    update(mutator) {
      return withState(mutator, true);
    },
    file,
  };
}
