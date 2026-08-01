// Minimal sandbox probe. Prints one line per capability. No side effects outside this dir.
const { execSync } = require('child_process');
const fs = require('fs'), path = require('path');
const out = [];
// 1. Nested process spawn — exactly what vite's optimizeSafeRealPathSync does.
try { execSync('net use', { stdio: 'pipe' }); out.push('SPAWN_NET_USE: OK'); }
catch (e) { out.push('SPAWN_NET_USE: FAIL ' + e.code + ' ' + (e.message||'').split('\n')[0]); }
// 2. Any nested spawn at all.
try { execSync('cmd /c echo hi', { stdio: 'pipe' }); out.push('SPAWN_CMD: OK'); }
catch (e) { out.push('SPAWN_CMD: FAIL ' + e.code); }
// 3. Write + unlink inside the workspace.
const f = path.join(__dirname, 'probe-tmp.txt');
try { fs.writeFileSync(f, 'x'); out.push('WRITE: OK'); } catch (e) { out.push('WRITE: FAIL ' + e.code); }
try { fs.unlinkSync(f); out.push('UNLINK: OK'); } catch (e) { out.push('UNLINK: FAIL ' + e.code); }
// 4. Unlink the exact .next artifact that failed (recreate it first so this is non-destructive).
const nx = path.resolve(__dirname, '../../dashboard/.next/probe-unlink.json');
try { fs.writeFileSync(nx, '{}'); fs.unlinkSync(nx); out.push('NEXT_DIR_UNLINK: OK'); }
catch (e) { out.push('NEXT_DIR_UNLINK: FAIL ' + e.code); }
console.log(out.join('\n'));
