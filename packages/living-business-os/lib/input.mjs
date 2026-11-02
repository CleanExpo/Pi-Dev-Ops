// Bounded input reading. Bytes are counted while reading, before any parsing, and
// the whole read is bounded in time. Resolves with the text, or rejects with
// an Error whose .limit is true when a limit was hit.
import fs from 'node:fs';
import { LIMITS } from './envelope.mjs';

function limitError() {
  const e = new Error('LIMIT');
  e.limit = true;
  return e;
}

export function readBounded(stream) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let bytes = 0;
    let done = false;
    const finish = (fn, v) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      stream.removeAllListeners('data');
      stream.removeAllListeners('end');
      stream.removeAllListeners('error');
      fn(v);
    };
    const timer = setTimeout(() => finish(reject, limitError()), LIMITS.input_timeout_ms);
    stream.on('data', (chunk) => {
      bytes += chunk.length;
      if (bytes > LIMITS.max_input_bytes) return finish(reject, limitError());
      chunks.push(chunk);
    });
    stream.on('end', () => finish(resolve, Buffer.concat(chunks).toString('utf8')));
    stream.on('error', (e) => finish(reject, e));
  });
}

export function readInputText({ file, stdin }) {
  return readBounded(file === undefined ? stdin : fs.createReadStream(file));
}

/** True if the path can be opened for reading as a regular file. */
export function readableFile(file) {
  try {
    fs.accessSync(file, fs.constants.R_OK);
    return fs.statSync(file).isFile();
  } catch {
    return false;
  }
}
