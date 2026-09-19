"""Bounded cleanup for the process tree owned by one build command."""
import asyncio

async def stop_process_tree(proc, process_options, os):
    # Like workspace verification, own the entire command tree. Never signal
    # the server's console/process group, and never leave cleanup unbounded.
    killer = None
    try:
        if os.name == "nt":
            killer = await asyncio.create_subprocess_exec(
                "taskkill", "/PID", str(proc.pid), "/T", "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                **process_options,
            )
            await asyncio.wait_for(killer.wait(), timeout=5)
        else:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, asyncio.TimeoutError):
        pass
    finally:
        if killer is not None and killer.returncode is None:
            try:
                killer.kill()
                await asyncio.wait_for(killer.wait(), timeout=5)
            except (OSError, asyncio.TimeoutError):
                pass
        if proc.returncode is None:
            try:
                proc.kill()
            except OSError:
                pass
        try:
            await asyncio.wait_for(proc.communicate(), timeout=5)
        except (OSError, asyncio.TimeoutError):
            pass
