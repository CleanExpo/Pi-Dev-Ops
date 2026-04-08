import asyncio, json, os, shutil, time, uuid
from dataclasses import dataclass, field
from typing import Optional
from . import config
from . import persistence
from .brief import classify_intent, build_structured_brief
from .lessons import append_lesson

# TAO engine — loaded after brief.py sets up sys.path (project root injected there)
try:
    from src.tao.budget.tracker import BudgetTracker
    from src.tao.tiers.config import load_config as _load_tao_config
    from src.tao.schemas.artifacts import TaskSpec, TaskResult
    _TAO_AVAILABLE = True
except ImportError:
    _TAO_AVAILABLE = False

def _load_harness_config():
    """Load .harness/config.yaml via TAO TierConfig. Returns dict or None."""
    if not _TAO_AVAILABLE:
        return None
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "..", ".harness", "config.yaml")
    cfg_path = os.path.abspath(cfg_path)
    try:
        return _load_tao_config(cfg_path) if os.path.isfile(cfg_path) else None
    except Exception:
        return None

_HARNESS_CONFIG = _load_harness_config()


def _select_model(phase: str, explicit_model: str = "") -> str:
    """Select model for a build phase using harness config.
    phase: 'planner', 'generator', or 'evaluator'.
    Returns short model name (opus/sonnet/haiku)."""
    if explicit_model and explicit_model in config.ALLOWED_MODELS:
        return explicit_model
    if _HARNESS_CONFIG and "agents" in _HARNESS_CONFIG:
        agent_cfg = _HARNESS_CONFIG["agents"].get(phase, {})
        if isinstance(agent_cfg, dict):
            m = agent_cfg.get("model", "")
            if m in config.ALLOWED_MODELS:
                return m
    return "sonnet"


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
    parent_session_id: Optional[str] = None  # RA-464: fan-out parallelism
    budget: Optional[object] = None           # RA-465: BudgetTracker instance
    last_completed_phase: str = ""            # Phase tracking for resume (GROUP D/E)
    retry_count: int = 0                      # Evaluator retry count (GROUP C)

_sessions = {}
def get_session(sid): return _sessions.get(sid)
def list_sessions():
    return [
        {
            "id": s.id,
            "repo": s.repo_url,
            "status": s.status,
            "started": s.started_at,
            "lines": len(s.output_lines),
            "parent": s.parent_session_id,
            "last_phase": s.last_completed_phase,
            "evaluator_score": s.evaluator_score,
        }
        for s in _sessions.values()
    ]

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
            last_completed_phase=data.get("last_completed_phase", ""),
            retry_count=data.get("retry_count", 0),
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

def _parse_evaluator_dimensions(eval_text: str) -> dict:
    """Parse all 4 evaluator dimension scores from output text.
    Returns {dimension_name: (score, reason)}."""
    dimensions = {}
    for line in eval_text.split("\n"):
        line_upper = line.strip().upper()
        for dim in ("COMPLETENESS", "CORRECTNESS", "CONCISENESS", "FORMAT"):
            if line_upper.startswith(dim + ":"):
                try:
                    rest = line.split(":", 1)[1].strip()
                    score_str = rest.split("/")[0].strip()
                    reason = rest.split("\u2014", 1)[1].strip() if "\u2014" in rest else rest
                    dimensions[dim.lower()] = (float(score_str), reason[:200])
                except (ValueError, IndexError):
                    pass
    return dimensions


_PHASE_ORDER = ["clone", "analyze", "claude_check", "sandbox", "generator", "evaluator", "push"]


def _should_skip(phase: str, resume_from: str) -> bool:
    """Return True if this phase should be skipped (already completed before resume)."""
    if not resume_from:
        return False
    try:
        return _PHASE_ORDER.index(phase) <= _PHASE_ORDER.index(resume_from)
    except ValueError:
        return False


async def run_build(session, brief="", model="sonnet", intent="", resume_from=""):
    em(session, "phase", "  Pi CEO Solo DevOps Tool")
    em(session, "system", f"  Session: {session.id}")
    em(session, "system", f"  Repo:    {session.repo_url}")
    em(session, "system", f"  Model:   {model}")
    if resume_from:
        em(session, "system", f"  Resuming from: {resume_from}")
    # ── TAO engine initialisation (RA-465) ────────────────────────────────────
    if _TAO_AVAILABLE:
        total_budget = (_HARNESS_CONFIG or {}).get("total_token_budget", 100000)
        session.budget = BudgetTracker(total_budget=total_budget)
        em(session, "system", f"  TAO:     budget={total_budget:,} tokens | config={'loaded' if _HARNESS_CONFIG else 'default'}")
    em(session, "system", "")
    if not _should_skip("clone", resume_from):
        em(session, "phase", "[1/5] Cloning repository...")
        session.status = "cloning"
        persistence.save_session(session)
        session.workspace = os.path.join(config.WORKSPACE_ROOT, session.id)
        os.makedirs(session.workspace, exist_ok=True)
        clone_ok = False
        for clone_attempt in range(3):
            try:
                rc, _, stderr = await run_cmd(
                    session.workspace, "git", "clone", "--depth", "1",
                    session.repo_url, session.workspace, timeout=60
                )
                if rc == 0:
                    clone_ok = True
                    em(session, "success", "  Clone complete")
                    break
                em(session, "error", f"  Clone attempt {clone_attempt + 1}/3 failed: {stderr[:200]}")
            except asyncio.TimeoutError:
                em(session, "error", f"  Clone attempt {clone_attempt + 1}/3 timed out")
            except FileNotFoundError:
                em(session, "error", "  Git not in PATH")
                session.status = "failed"
                persistence.save_session(session)
                return
            if clone_attempt < 2:
                backoff = 2 * (2 ** clone_attempt)
                em(session, "system", f"  Retrying in {backoff}s...")
                await asyncio.sleep(backoff)
                if os.path.exists(session.workspace):
                    shutil.rmtree(session.workspace, ignore_errors=True)
                    os.makedirs(session.workspace, exist_ok=True)
        if not clone_ok:
            em(session, "error", "  Clone failed after 3 attempts")
            session.status = "failed"
            persistence.save_session(session)
            return
        session.last_completed_phase = "clone"
        persistence.save_session(session)
    else:
        em(session, "system", "  [SKIP] Clone (already completed)")
        if not session.workspace:
            session.workspace = os.path.join(config.WORKSPACE_ROOT, session.id)
    if not _should_skip("analyze", resume_from):
        em(session, "phase", "[2/5] Analyzing workspace...")
        files = [f for f in os.listdir(session.workspace) if not f.startswith(".")]
        em(session, "system", f"  Files: {', '.join(files[:15]) or '(empty)'}")
        session.last_completed_phase = "analyze"
        persistence.save_session(session)
    else:
        em(session, "system", "  [SKIP] Analyze (already completed)")

    if not _should_skip("claude_check", resume_from):
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
        session.last_completed_phase = "claude_check"
        persistence.save_session(session)
    else:
        em(session, "system", "  [SKIP] Claude check (already completed)")

    if not _should_skip("sandbox", resume_from):
        # ── Sandbox enforcement (RA-468) ─────────────────────────────────────────
        em(session, "phase", "[3.5/5] Verifying sandbox...")
        if not session.workspace or not os.path.isdir(session.workspace):
            em(session, "system", "  Sandbox missing — auto-regenerating workspace...")
            session.workspace = os.path.join(config.WORKSPACE_ROOT, session.id)
            os.makedirs(session.workspace, exist_ok=True)
            try:
                proc_reclone = await asyncio.create_subprocess_exec(
                    "git", "clone", "--depth", "1", session.repo_url, session.workspace,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                _, stderr = await asyncio.wait_for(proc_reclone.communicate(), timeout=60)
                if proc_reclone.returncode != 0:
                    em(session, "error", f"  Sandbox re-clone failed: {stderr.decode()[:200]}")
                    session.status = "failed"
                    persistence.save_session(session)
                    return
                em(session, "success", "  Sandbox restored via re-clone")
            except Exception as e:
                em(session, "error", f"  Sandbox regeneration error: {e}")
                session.status = "failed"
                persistence.save_session(session)
                return
        else:
            em(session, "success", f"  Sandbox verified: {session.workspace}")
        session.last_completed_phase = "sandbox"
        persistence.save_session(session)
    else:
        em(session, "system", "  [SKIP] Sandbox (already completed)")

    em(session, "phase", "[4/5] Running Claude Code (live)...")
    em(session, "system", "")
    session.status = "building"
    persistence.save_session(session)
    if not brief:
        brief = "Analyze this codebase fully. Read every skill in skills/. Read the engine in src/tao/. Produce a detailed analysis in .harness/spec.md. Suggest improvements. Git commit changes."
    resolved_intent = intent or classify_intent(brief)
    em(session, "system", f"  Intent: {resolved_intent.upper()}")
    spec = build_structured_brief(brief, resolved_intent, session.repo_url)

    # ── Generator execution with retry (GROUP D) ─────────────────────────────
    gen_ok = False
    for gen_attempt in range(2):
        current_spec = spec if gen_attempt == 0 else spec[:4000] + "\n\n[NOTE: Simplified due to previous failure. Focus on core task only.]"
        try:
            cmd = [config.CLAUDE_CMD, "-p", current_spec, "--model", model, "--verbose", "--output-format", "stream-json"]
            em(session, "tool", f"  $ claude --model {model} --verbose --stream-json")
            em(session, "system", "")
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=session.workspace)
            session.process = proc
            async def _read_stdout(p, s):
                while True:
                    line = await p.stdout.readline()
                    if not line: break
                    parse_event(line.decode("utf-8", errors="replace").rstrip(), s)
            async def _read_stderr(p, s):
                while True:
                    line = await p.stderr.readline()
                    if not line: break
                    t = line.decode("utf-8", errors="replace").rstrip()
                    if t and "warn" not in t.lower(): em(s, "stderr", f"  {t[:200]}")
            await asyncio.gather(_read_stdout(proc, session), _read_stderr(proc, session))
            await proc.wait()
            em(session, "system", "")
            if proc.returncode == 0:
                gen_ok = True
                em(session, "success", "  Claude Code completed")
                break
            em(session, "error", f"  Claude exited code {proc.returncode} (attempt {gen_attempt + 1}/2)")
            if gen_attempt == 0:
                em(session, "system", "  Retrying with simplified prompt...")
        except Exception as e:
            em(session, "error", f"  Error: {e} (attempt {gen_attempt + 1}/2)")
            if gen_attempt > 0:
                session.status = "failed"
                persistence.save_session(session)
                return
    if not gen_ok:
        em(session, "error", "  Generator failed after 2 attempts")
        session.status = "failed"
        persistence.save_session(session)
        return
    session.last_completed_phase = "generator"
    persistence.save_session(session)

    # ── Phase 4.5: Quality Gate — closed-loop evaluator retry (GROUP C) ──────
    if session.evaluator_enabled and config.EVALUATOR_ENABLED:
        total_phases = 6
        max_retries = config.EVALUATOR_MAX_RETRIES
        for eval_attempt in range(max_retries + 1):
            em(session, "phase", f"[5/{total_phases}] Running Evaluator (attempt {eval_attempt + 1}/{max_retries + 1})...")
            session.status = "evaluating"
            session.evaluator_status = "running"
            session.retry_count = eval_attempt
            persistence.save_session(session)
            try:
                rc, diff_out, _ = await run_cmd(session.workspace, "git", "diff", "HEAD~1", "--stat", timeout=10)
                _, diff_full, _ = await run_cmd(session.workspace, "git", "diff", "HEAD~1", timeout=30)
                diff_context = diff_full[:8000] if diff_full else "(no diff available)"
                eval_spec = (
                    "You are a code evaluator. Grade the following changes on 4 dimensions "
                    "(each scored 1-10):\n"
                    "1. Completeness \u2014 does it address the full brief?\n"
                    "2. Correctness \u2014 are there bugs, logic errors, or security issues?\n"
                    "3. Conciseness \u2014 is the code clean without unnecessary bloat?\n"
                    "4. Format compliance \u2014 follows project conventions and style?\n\n"
                    "DIFF SUMMARY:\n" + (diff_out or "(empty)") + "\n\n"
                    "DIFF DETAIL (truncated):\n" + diff_context + "\n\n"
                    "OUTPUT FORMAT: Respond with exactly 4 lines, one per dimension:\n"
                    "COMPLETENESS: <score>/10 \u2014 <reason>\n"
                    "CORRECTNESS: <score>/10 \u2014 <reason>\n"
                    "CONCISENESS: <score>/10 \u2014 <reason>\n"
                    "FORMAT: <score>/10 \u2014 <reason>\n"
                    "Then a final line: OVERALL: <average>/10 \u2014 PASS or FAIL (threshold: "
                    + str(config.EVALUATOR_THRESHOLD) + "/10)"
                )
                eval_cmd = [config.CLAUDE_CMD, "-p", eval_spec, "--model", config.EVALUATOR_MODEL, "--output-format", "text"]
                em(session, "tool", f"  $ claude --model {config.EVALUATOR_MODEL} (evaluator)")
                eval_proc = await asyncio.create_subprocess_exec(
                    *eval_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=session.workspace
                )
                eval_out, _ = await asyncio.wait_for(eval_proc.communicate(), timeout=120)
                eval_text = eval_out.decode("utf-8", errors="replace").strip()
                session.evaluator_score = None
                for line in eval_text.split("\n"):
                    em(session, "agent", f"  {line.strip()[:200]}")
                    if line.upper().startswith("OVERALL:"):
                        try:
                            session.evaluator_score = float(line.split(":")[1].strip().split("/")[0].strip())
                        except (ValueError, IndexError):
                            pass
                if session.evaluator_score is not None:
                    passed = session.evaluator_score >= config.EVALUATOR_THRESHOLD
                    # Auto-learning from evaluator
                    try:
                        dimensions = _parse_evaluator_dimensions(eval_text)
                        threshold = config.EVALUATOR_THRESHOLD
                        for dim_name, (score, reason) in dimensions.items():
                            if score < threshold:
                                append_lesson(source="evaluator", category=resolved_intent,
                                    lesson=f"{dim_name} scored {score}/10: {reason}",
                                    severity="warn" if score < threshold - 1 else "info")
                        if not passed:
                            weak = ", ".join(d for d, (s, _) in dimensions.items() if s < threshold)
                            append_lesson(source="evaluator", category=resolved_intent,
                                lesson=f"Build scored {session.evaluator_score}/10 (below {threshold}). Weak: {weak}",
                                severity="warn")
                    except Exception:
                        pass
                    if passed:
                        session.evaluator_status = "passed"
                        em(session, "success", f"  Evaluator: {session.evaluator_score}/10 \u2014 PASS")
                        break
                    elif eval_attempt >= max_retries:
                        session.evaluator_status = "warned"
                        em(session, "error", f"  Evaluator: {session.evaluator_score}/10 \u2014 BELOW THRESHOLD (exhausted {max_retries + 1} attempts)")
                        break
                    else:
                        # Build retry prompt with evaluator critique
                        weak_dims = [f"{d}: {s}/10 \u2014 {r}" for d, (s, r) in dimensions.items() if s < threshold]
                        retry_brief = (
                            spec + "\n\n--- RETRY INSTRUCTIONS ---\n"
                            f"Previous attempt scored {session.evaluator_score}/10 (threshold: {threshold}).\n"
                            "Issues found:\n" + "\n".join(f"- {w}" for w in weak_dims) + "\n"
                            "Fix these specific issues. Do not rewrite everything.\n--- END RETRY ---"
                        )
                        em(session, "error", f"  Evaluator: {session.evaluator_score}/10 \u2014 RETRYING")
                        em(session, "phase", f"[4/{total_phases}] Re-running Claude Code (retry {eval_attempt + 1})...")
                        session.status = "building"
                        persistence.save_session(session)
                        retry_cmd = [config.CLAUDE_CMD, "-p", retry_brief, "--model", model, "--verbose", "--output-format", "stream-json"]
                        retry_proc = await asyncio.create_subprocess_exec(
                            *retry_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=session.workspace
                        )
                        session.process = retry_proc
                        await asyncio.gather(_read_stdout(retry_proc, session), _read_stderr(retry_proc, session))
                        await retry_proc.wait()
                        if retry_proc.returncode != 0:
                            em(session, "error", "  Retry generation failed")
                            break
                        em(session, "success", "  Retry generation complete")
                        continue
                else:
                    session.evaluator_status = "error"
                    em(session, "error", "  Evaluator: could not parse score")
                    break
            except asyncio.TimeoutError:
                session.evaluator_status = "timeout"
                em(session, "error", "  Evaluator timed out (120s)")
                break
            except Exception as e:
                session.evaluator_status = "error"
                em(session, "error", f"  Evaluator error: {e}")
                break
        session.last_completed_phase = "evaluator"
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
            # ── Push with retry (RA-471) ──────────────────────────────────────
            push_ok = False
            for push_attempt in range(3):
                rc, _, err = await run_cmd(session.workspace, "git", "push", "origin", "HEAD", timeout=30)
                if rc == 0:
                    push_ok = True
                    em(session, "success", "  Pushed to GitHub!")
                    em(session, "success", f"  https://github.com/CleanExpo/Pi-Dev-Ops")
                    break
                err_lower = err.lower()
                # Auth failures are permanent — no point retrying
                if any(s in err_lower for s in ("authentication failed", "could not read username", "permission denied", "403", "401")):
                    em(session, "error", f"  Push auth error (not retrying): {err[:200]}")
                    break
                em(session, "error", f"  Push attempt {push_attempt + 1}/3 failed: {err[:200]}")
                if push_attempt < 2:
                    backoff = 2 * (2 ** push_attempt)
                    em(session, "system", f"  Retrying push in {backoff}s...")
                    await asyncio.sleep(backoff)
            if not push_ok:
                em(session, "error", "  Push failed — changes committed locally, push manually")
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
    session.last_completed_phase = "push"
    session.status = "complete"
    persistence.save_session(session)
    em(session, "system", "")
    em(session, "phase", "  Summary")
    em(session, "system", f"    Duration: {time.time()-session.started_at:.0f}s")
    em(session, "system", f"    Files: {len(af) if 'af' in locals() else '?'}")
    em(session, "success", "  === SESSION COMPLETE ===")

async def create_session(repo_url, brief="", model="", evaluator_enabled=True, intent="", parent_session_id=""):
    if len(_sessions) >= config.MAX_CONCURRENT_SESSIONS:
        raise RuntimeError("Max sessions reached")
    resolved_model = _select_model("generator", model)
    session = BuildSession(
        repo_url=repo_url,
        started_at=time.time(),
        evaluator_enabled=evaluator_enabled,
        parent_session_id=parent_session_id or None,
    )
    _sessions[session.id] = session
    persistence.save_session(session)
    asyncio.create_task(run_build(session, brief, resolved_model, intent=intent))
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
