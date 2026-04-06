import asyncio, json, os, shutil, time, uuid
from dataclasses import dataclass, field
from typing import Optional
from . import config

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

_sessions = {}
def get_session(sid): return _sessions.get(sid)
def list_sessions():
    return [{"id":s.id,"repo":s.repo_url,"status":s.status,"started":s.started_at,"lines":len(s.output_lines)} for s in _sessions.values()]

def em(session, t, d):
    session.output_lines.append({"type":t,"text":d,"ts":time.time()})

async def run_cmd(cwd, *args, timeout=60):
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd)
    out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return proc.returncode, out.decode("utf-8",errors="replace"), err.decode("utf-8",errors="replace")

def parse_claude_event(line, session):
    try:
        evt = json.loads(line)
    except:
        if line.strip():
            em(session, "output", line)
        return
    etype = evt.get("type", "")
    if etype == "assistant" and "message" in evt:
        msg = evt["message"]
        if isinstance(msg, dict):
            content = msg.get("content", "")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            for tl in block.get("text","").split("\n"):
                                if tl.strip(): em(session, "agent", tl)
                        elif block.get("type") == "tool_use":
                            name = block.get("name","tool")
                            inp = block.get("input",{})
                            if name == "Bash":
                                cmd = inp.get("command","")
                                em(session, "tool", f"  $ {cmd[:120]}")
                            elif name == "Write":
                                path = inp.get("file_path","")
                                em(session, "tool", f"  write {path}")
                            elif name == "Edit":
                                path = inp.get("file_path","")
                                em(session, "tool", f"  edit {path}")
                            elif name == "Read":
                                path = inp.get("file_path","")
                                em(session, "tool", f"  read {path}")
                            else:
                                em(session, "tool", f"  {name}: {json.dumps(inp)[:100]}")
            elif isinstance(content, str) and content.strip():
                for tl in content.split("\n"):
                    if tl.strip(): em(session, "agent", tl)
    elif etype == "result":
        txt = evt.get("result","")
        if isinstance(txt, str):
            for tl in txt.split("\n"):
                if tl.strip(): em(session, "output", f"  {tl[:200]}")
        cost = evt.get("cost_usd")
        if cost: em(session, "metric", f"  Cost: ")
        tokens = evt.get("total_tokens")
        if tokens: em(session, "metric", f"  Tokens: {tokens}")

async def run_build(session, brief="", model="sonnet"):
    em(session, "system", f"=== Pi CEO Session {session.id} ===")
    em(session, "system", f"Repo: {session.repo_url}")
    em(session, "system", f"Model: {model}")
    em(session, "system", "")
    em(session, "phase", "[1/5] Cloning repository...")
    session.status = "cloning"
    session.workspace = os.path.join(config.WORKSPACE_ROOT, session.id)
    os.makedirs(session.workspace, exist_ok=True)
    try:
        proc = await asyncio.create_subprocess_exec("git","clone","--depth","1",session.repo_url,session.workspace,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        if proc.returncode != 0:
            em(session, "error", f"Clone failed: {stderr.decode()[:300]}")
            session.status = "failed"
            return
        em(session, "success", "  Clone complete")
    except asyncio.TimeoutError:
        em(session, "error", "Clone timed out")
        session.status = "failed"
        return
    except FileNotFoundError:
        em(session, "error", "Git not in PATH")
        session.status = "failed"
        return
    em(session, "phase", "[2/5] Analyzing workspace...")
    files = [f for f in os.listdir(session.workspace) if not f.startswith(".")]
    em(session, "system", f"  {len(files)} files: {', '.join(files[:10]) or '(empty)'}")
    em(session, "phase", "[3/5] Checking Claude Code...")
    try:
        rc, out, err = await run_cmd(session.workspace, config.CLAUDE_CMD, "--version", timeout=10)
        if rc == 0:
            em(session, "success", f"  {(out.strip() or err.strip())[:80]}")
        else:
            em(session, "error", "  Claude Code error")
            session.status = "failed"
            return
    except FileNotFoundError:
        em(session, "error", "  Claude Code NOT FOUND")
        session.status = "failed"
        return
    em(session, "phase", "[4/5] Running Claude Code (live stream)...")
    em(session, "system", "")
    session.status = "building"
    if not brief:
        brief = "This repo has basic files. Create a proper project structure with .harness/spec.md, add useful scaffolding. Git add and commit all changes."
    spec = f"You are Pi CEO orchestrator on Claude Max.\nProject: {session.repo_url}\nTASK:\n{brief}\nRULES:\n- Create files as needed\n- Run: git add -A && git commit -m 'message' after each change\n- Show what you are doing at each step"
    try:
        cmd = [config.CLAUDE_CMD, "-p", spec, "--model", model, "--output-format", "stream-json"]
        em(session, "tool", f"  $ claude --model {model} --output-format stream-json")
        em(session, "system", "")
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=session.workspace)
        session.process = proc
        async def read_stdout():
            while True:
                line = await proc.stdout.readline()
                if not line: break
                text = line.decode("utf-8",errors="replace").rstrip()
                if text: parse_claude_event(text, session)
        async def read_stderr():
            while True:
                line = await proc.stderr.readline()
                if not line: break
                text = line.decode("utf-8",errors="replace").rstrip()
                if text: em(session, "stderr", text)
        await asyncio.gather(read_stdout(), read_stderr())
        await proc.wait()
        em(session, "system", "")
        if proc.returncode == 0:
            em(session, "success", "  Claude Code finished")
        else:
            em(session, "error", f"  Claude exited code {proc.returncode}")
    except asyncio.TimeoutError:
        em(session, "error", "  Timed out")
        session.status = "failed"
        return
    except Exception as e:
        em(session, "error", f"  Error: {e}")
        session.status = "failed"
        return
    em(session, "phase", "[5/5] Pushing to GitHub...")
    try:
        rc, out, _ = await run_cmd(session.workspace, "git", "status", "--porcelain")
        if out.strip():
            await run_cmd(session.workspace, "git", "add", "-A")
            await run_cmd(session.workspace, "git", "commit", "-m", "feat: Pi CEO build")
        rc, out, _ = await run_cmd(session.workspace, "git", "log", "--oneline", "-5")
        for line in out.strip().split("\n"):
            if line.strip(): em(session, "system", f"  {line.strip()}")
        commits = len([l for l in out.strip().split("\n") if l.strip()])
        if commits > 0:
            em(session, "system", f"  Pushing {commits} commit(s)...")
            rc, out, err = await run_cmd(session.workspace, "git", "push", "origin", "HEAD", timeout=30)
            if rc == 0:
                em(session, "success", "  Pushed to GitHub!")
                em(session, "success", f"  {session.repo_url.replace('.git','')}")
            else:
                em(session, "error", f"  Push failed: {err[:200]}")
        else:
            em(session, "system", "  Nothing to push")
    except Exception as e:
        em(session, "error", f"  Push error: {e}")
    session.status = "complete"
    em(session, "metric", f"=== Done in {time.time()-session.started_at:.0f}s ===")

async def create_session(repo_url, brief="", model="sonnet"):
    if len(_sessions) >= config.MAX_CONCURRENT_SESSIONS:
        raise RuntimeError(f"Max {config.MAX_CONCURRENT_SESSIONS} sessions")
    session = BuildSession(repo_url=repo_url, started_at=time.time())
    _sessions[session.id] = session
    asyncio.create_task(run_build(session, brief, model))
    return session

async def kill_session(sid):
    s = _sessions.get(sid)
    if not s or not s.process: return False
    try:
        s.process.terminate()
        await asyncio.sleep(2)
        if s.process.returncode is None: s.process.kill()
        s.status = "killed"
        em(s, "error", "Killed by user")
        return True
    except: return False

def cleanup_session(sid):
    s = _sessions.pop(sid, None)
    if s and s.workspace and os.path.exists(s.workspace):
        shutil.rmtree(s.workspace, ignore_errors=True)
