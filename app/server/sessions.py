import asyncio, json, os, shutil, time, uuid
from dataclasses import dataclass, field
from typing import Optional
from . import config
from . import persistence
from .brief import classify_intent, build_structured_brief

@dataclass
class BuildSession:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    repo_url: str = ""
    workspace: str = ""
    process: Optional[asyncio.subprocess.Process] = None
    started_at: float = 0.0
    status: str = "created"
    output_lines: list = field(default_factory=list)
    error: Optional[str] = None
    evaluator_enabled: bool = True
    evaluator_status: str = "pending"
    evaluator_score: Optional[float] = None

_sessions = {}
def get_session(sid): return _sessions.get(sid)
def list_sessions():
    return [{"id":s.id,"repo":s.repo_url,"status":s.status,"started":s.started_at,"lines":len(s.output_lines)} for s in _sessions.values()]

def restore_sessions():
    """Load persisted sessions from disk on server startup.
    Sessions that were mid-flight (cloning/building) are marked 'interrupted'."""
    count = 0
    for data in persistence.load_all_sessions():
        sid = data.get("id", "")
        if not sid or sid in _sessions:
            continue
        session = BuildSession(
            id=sid,
            repo_url=data.get("repo_url", ""),
            workspace=data.get("workspace", ""),
            started_at=data.get("started_at", 0.0),
            status=data.get("status", "unknown"),
            error=data.get("error"),
        )
        # Mark anything that was in-flight as interrupted
        if session.status in ("created", "cloning", "building"):
            session.status = "interrupted"
            persistence.save_session(session)
        _sessions[sid] = session
        count += 1
    if count:
        print(f"[persistence] Restored {count} session(s) from disk.")

def em(session, t, d):
    session.output_lines.append({"type":t,"text":d,"ts":time.time()})

async def run_cmd(cwd, *args, timeout=60):
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd)
    out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return proc.returncode, out.decode("utf-8",errors="replace"), err.decode("utf-8",errors="replace")

def parse_event(line, session):
    try: evt = json.loads(line)
    except:
        if line.strip(): em(session, "output", line)
        return
    t = evt.get("type","")
    if t == "system":
        m = evt.get("message","")
        if m: em(session, "system", f"  {m[:200]}")
    elif t == "assistant":
        msg = evt.get("message",{})
        c = msg.get("content","") if isinstance(msg,dict) else ""
        if isinstance(c, list):
            for b in c:
                if not isinstance(b,dict): continue
                bt = b.get("type","")
                if bt == "text":
                    for l in b.get("text","").split("\n"):
                        if l.strip(): em(session, "agent", f"  {l}")
                elif bt == "tool_use":
                    nm = b.get("name","")
                    inp = b.get("input",{})
                    if nm == "Bash": em(session, "tool", f"  $ {inp.get('command','')[:150]}")
                    elif nm in ("Write","Edit"): em(session, "tool", f"  {nm.lower()} {inp.get('file_path','')}")
                    elif nm == "Read": em(session, "tool", f"  read {inp.get('file_path','')}")
                    else: em(session, "tool", f"  {nm}")
    elif t in ("tool_result","result"):
        c = evt.get("content","") or evt.get("result","")
        if isinstance(c,list):
            for b in c:
                if isinstance(b,dict) and b.get("text"):
                    for l in b["text"].split("\n")[:20]:
                        if l.strip(): em(session, "output", f"    {l[:200]}")
        elif isinstance(c,str):
            for l in c.split("\n")[:20]:
                if l.strip(): em(session, "output", f"    {l[:200]}")
        cost = evt.get("cost_usd")
        if cost: em(session, "metric", f"  Cost: ${cost:.4f}")

async def run_build(session, brief="", model="sonnet", intent=""):
    em(session, "phase", "  Pi CEO Solo DevOps Tool")
    em(session, "system", f"  Session: {session.id}")
    em(session, "system", f"  Repo:    {session.repo_url}")
    em(session, "system", f"  Model:   {model}")
    em(session, "system", "")
    em(session, "phase", "[1/5] Cloning repository...")
    session.status = "cloning"
    persistence.save_session(session)
    session.workspace = os.path.join(config.WORKSPACE_ROOT, session.id)
    os.makedirs(session.workspace, exist_ok=True)
    try:
        proc = await asyncio.create_subprocess_exec("git","clone","--depth","1",session.repo_url,session.workspace,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        if proc.returncode != 0:
            em(session, "error", f"  Clone failed: {stderr.decode()[:300]}")
            session.status = "failed"
            persistence.save_session(session)
            return
        em(session, "success", "  Clone complete")
    except asyncio.TimeoutError:
        em(session, "error", "  Clone timed out")
        session.status = "failed"
        persistence.save_session(session)
        return
    except FileNotFoundError:
        em(session, "error", "  Git not in PATH")
        session.status = "failed"
        persistence.save_session(session)
        return
    em(session, "phase", "[2/5] Analyzing workspace...")
    files = [f for f in os.listdir(session.workspace) if not f.startswith(".")]
    em(session, "system", f"  Files: {', '.join(files[:15]) or '(empty)'}")
    em(session, "phase", "[3/5] Checking Claude Code...")
    try:
        rc, out, err = await run_cmd(session.workspace, config.CLAUDE_CMD, "--version", timeout=10)
        if rc == 0: em(session, "success", f"  {(out.strip() or err.strip())[:80]}")
        else:
            em(session, "error", "  Claude Code error")
            session.status = "failed"
            persistence.save_session(session)
            return
    except FileNotFoundError:
        em(session, "error", "  Claude Code NOT FOUND")
        session.status = "failed"
        persistence.save_session(session)
        return
    em(session, "phase", "[4/5] Running Claude Code (live)...")
    em(session, "system", "")
    session.status = "building"
    persistence.save_session(session)
    if not brief:
        brief = "Analyze this codebase fully. Read every skill in skills/. Read the engine in src/tao/. Produce a detailed analysis in .harness/spec.md. Suggest improvements. Git commit changes."
    # Classify intent and build structured spec
    resolved_intent = intent or classify_intent(brief)
    em(session, "system", f"  Intent: {resolved_intent.upper()}")
    spec = build_structured_brief(brief, resolved_intent, session.repo_url)
    try:
        cmd = [config.CLAUDE_CMD, "-p", spec, "--model", model, "--verbose", "--output-format", "stream-json"]
        em(session, "tool", f"  $ claude --model {model} --verbose --stream-json")
        em(session, "system", "")
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=session.workspace)
        session.process = proc
        async def read_out():
            while True:
                line = await proc.stdout.readline()
                if not line: break
                parse_event(line.decode("utf-8",errors="replace").rstrip(), session)
        async def read_err():
            while True:
                line = await proc.stderr.readline()
                if not line: break
                t = line.decode("utf-8",errors="replace").rstrip()
                if t and "warn" not in t.lower(): em(session, "stderr", f"  {t[:200]}")
        await asyncio.gather(read_out(), read_err())
        await proc.wait()
        em(session, "system", "")
        if proc.returncode == 0: em(session, "success", "  Claude Code completed")
        else: em(session, "error", f"  Claude exited code {proc.returncode}")
    except Exception as e:
        em(session, "error", f"  Error: {e}")
        session.status = "failed"
        persistence.save_session(session)
        return
    # ── Phase 4.5: Evaluator tier (optional) ─────────────────────────────────
    if session.evaluator_enabled and config.EVALUATOR_ENABLED:
        total_phases = 6
        em(session, "phase", f"[5/{total_phases}] Running Evaluator...")
        session.status = "evaluating"
        session.evaluator_status = "running"
        persistence.save_session(session)
        try:
            # Get the diff of what Claude changed
            rc, diff_out, _ = await run_cmd(session.workspace, "git", "diff", "HEAD~1", "--stat", timeout=10)
            rc2, diff_full, _ = await run_cmd(session.workspace, "git", "diff", "HEAD~1", timeout=30)
            diff_context = diff_full[:8000] if diff_full else "(no diff available)"

            eval_spec = (
                "You are a code evaluator. Grade the following changes on 4 dimensions "
                "(each scored 1-10):\n"
                "1. Completeness — does it address the full brief?\n"
                "2. Correctness — are there bugs, logic errors, or security issues?\n"
                "3. Conciseness — is the code clean without unnecessary bloat?\n"
                "4. Format compliance — follows project conventions and style?\n\n"
                "DIFF SUMMARY:\n" + (diff_out or "(empty)") + "\n\n"
                "DIFF DETAIL (truncated):\n" + diff_context + "\n\n"
                "OUTPUT FORMAT: Respond with exactly 4 lines, one per dimension:\n"
                "COMPLETENESS: <score>/10 — <reason>\n"
                "CORRECTNESS: <score>/10 — <reason>\n"
                "CONCISENESS: <score>/10 — <reason>\n"
                "FORMAT: <score>/10 — <reason>\n"
                "Then a final line: OVERALL: <average>/10 — PASS or FAIL (threshold: "
                + str(config.EVALUATOR_THRESHOLD) + "/10)"
            )
            eval_cmd = [config.CLAUDE_CMD, "-p", eval_spec, "--model", config.EVALUATOR_MODEL, "--output-format", "text"]
            em(session, "tool", f"  $ claude --model {config.EVALUATOR_MODEL} (evaluator)")
            eval_proc = await asyncio.create_subprocess_exec(
                *eval_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=session.workspace
            )
            eval_out, eval_err = await asyncio.wait_for(eval_proc.communicate(), timeout=120)
            eval_text = eval_out.decode("utf-8", errors="replace").strip()

            # Parse overall score from output
            for line in eval_text.split("\n"):
                em(session, "agent", f"  {line.strip()[:200]}")
                if line.upper().startswith("OVERALL:"):
                    try:
                        score_str = line.split(":")[1].strip().split("/")[0].strip()
                        session.evaluator_score = float(score_str)
                    except (ValueError, IndexError):
                        pass

            if session.evaluator_score is not None:
                passed = session.evaluator_score >= config.EVALUATOR_THRESHOLD
                session.evaluator_status = "passed" if passed else "warned"
                status_msg = "PASS" if passed else "BELOW THRESHOLD (non-blocking)"
                em(session, "success" if passed else "error",
                   f"  Evaluator: {session.evaluator_score}/10 — {status_msg}")
            else:
                session.evaluator_status = "error"
                em(session, "error", "  Evaluator: could not parse score")
            persistence.save_session(session)
        except asyncio.TimeoutError:
            session.evaluator_status = "timeout"
            em(session, "error", "  Evaluator timed out (120s)")
            persistence.save_session(session)
        except Exception as e:
            session.evaluator_status = "error"
            em(session, "error", f"  Evaluator error: {e}")
            persistence.save_session(session)
    else:
        total_phases = 5

    # ── Phase: Push to GitHub ──────────────────────────────────────────────────
    em(session, "phase", f"[{total_phases}/{total_phases}] Pushing to GitHub...")
    try:
        rc, out, _ = await run_cmd(session.workspace, "git", "status", "--porcelain")
        if out.strip():
            await run_cmd(session.workspace, "git", "add", "-A")
            await run_cmd(session.workspace, "git", "commit", "-m", "feat: Pi CEO build")
        rc, out, _ = await run_cmd(session.workspace, "git", "log", "--oneline", "-10")
        commits = [l.strip() for l in out.strip().split("\n") if l.strip()]
        if commits:
            for c in commits: em(session, "system", f"  {c}")
            em(session, "system", f"  Pushing {len(commits)} commits...")
            rc, _, err = await run_cmd(session.workspace, "git", "push", "origin", "HEAD", timeout=30)
            if rc == 0:
                em(session, "success", "  Pushed to GitHub!")
                em(session, "success", f"  https://github.com/CleanExpo/Pi-Dev-Ops")
            else: em(session, "error", f"  Push failed: {err[:200]}")
        em(session, "system", "")
        em(session, "phase", "  Project structure:")
        af = []
        for r, dirs, fns in os.walk(session.workspace):
            dirs[:] = [d for d in dirs if d not in (".git","node_modules","__pycache__","workspaces")]
            for fn in fns: af.append(os.path.relpath(os.path.join(r,fn), session.workspace))
        for x in sorted(af)[:30]: em(session, "system", f"    {x}")
        if len(af) > 30: em(session, "system", f"    ...+{len(af)-30} more")
    except Exception as e:
        em(session, "error", f"  Push error: {e}")
    session.status = "complete"
    persistence.save_session(session)
    em(session, "system", "")
    em(session, "phase", "  Summary")
    em(session, "system", f"    Duration: {time.time()-session.started_at:.0f}s")
    em(session, "system", f"    Files: {len(af) if 'af' in locals() else '?'}")
    em(session, "success", "  === SESSION COMPLETE ===")

async def create_session(repo_url, brief="", model="sonnet", evaluator_enabled=True, intent=""):
    if len(_sessions) >= config.MAX_CONCURRENT_SESSIONS:
        raise RuntimeError("Max sessions reached")
    session = BuildSession(repo_url=repo_url, started_at=time.time(), evaluator_enabled=evaluator_enabled)
    _sessions[session.id] = session
    persistence.save_session(session)
    asyncio.create_task(run_build(session, brief, model, intent=intent))
    return session

async def kill_session(sid):
    s = _sessions.get(sid)
    if not s or not s.process: return False
    try:
        s.process.terminate()
        await asyncio.sleep(2)
        if s.process.returncode is None: s.process.kill()
        s.status = "killed"
        persistence.save_session(s)
        em(s, "error", "Killed by user")
        return True
    except: return False

def cleanup_session(sid):
    s = _sessions.pop(sid, None)
    if s and s.workspace and os.path.exists(s.workspace):
        shutil.rmtree(s.workspace, ignore_errors=True)
    persistence.delete_session_file(sid)
