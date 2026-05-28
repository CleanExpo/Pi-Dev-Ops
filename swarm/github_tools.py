"""Thin wrapper around the GitHub CLI for production handoff.

Tests stub a `GitHubClient` Protocol instead of shelling out. The
default `GhCliClient` calls `gh` via subprocess — used by the PR5
wiring layer.

Public surface kept tiny on purpose: the handoff orchestrator
in `swarm/intake/handoff.py` only needs to create a feature branch
on a project repo and open a PR. Everything else (issue creation,
status round-trip) belongs in `linear_tools.py` and the Vercel/GitHub
integration on the project repo itself.
"""
from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GhRepo:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @classmethod
    def parse(cls, full_name: str) -> "GhRepo":
        if "/" not in full_name:
            raise ValueError(f"repo must be 'owner/name', got {full_name!r}")
        owner, name = full_name.split("/", 1)
        if not owner or not name:
            raise ValueError(f"invalid repo {full_name!r}")
        return cls(owner=owner, name=name)


@dataclass(frozen=True)
class PullRequestResult:
    url: str
    number: int


class GitHubClient(Protocol):
    """What handoff.py needs from gh."""
    def create_branch(self, *, repo: GhRepo, base: str, new_branch: str) -> None: ...
    def open_pr(
        self,
        *,
        repo: GhRepo,
        head: str,
        base: str,
        title: str,
        body: str,
    ) -> PullRequestResult: ...


# ============================================================
# Real CLI implementation (used in production; not used by tests)
# ============================================================

class GhCliClient:
    """Shells out to the `gh` CLI. Requires `gh auth status` to be valid."""

    def __init__(self, *, gh_binary: str = "gh"):
        self._gh = gh_binary

    def _run(self, args: list[str], *, input_data: str | None = None) -> str:
        full = [self._gh] + args
        result = subprocess.run(
            full,
            input=input_data,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"gh failed: {' '.join(shlex.quote(a) for a in full)}\n"
                f"stderr: {result.stderr.strip()}"
            )
        return result.stdout

    def create_branch(self, *, repo: GhRepo, base: str, new_branch: str) -> None:
        sha_json = self._run([
            "api", f"repos/{repo.full_name}/git/refs/heads/{base}",
        ])
        sha = json.loads(sha_json)["object"]["sha"]
        # Idempotent: ignore "Reference already exists"
        try:
            self._run([
                "api", "--method", "POST",
                f"repos/{repo.full_name}/git/refs",
                "-f", f"ref=refs/heads/{new_branch}",
                "-f", f"sha={sha}",
            ])
        except RuntimeError as exc:
            if "Reference already exists" not in str(exc):
                raise

    def open_pr(
        self,
        *,
        repo: GhRepo,
        head: str,
        base: str,
        title: str,
        body: str,
    ) -> PullRequestResult:
        out = self._run([
            "pr", "create",
            "--repo", repo.full_name,
            "--head", head,
            "--base", base,
            "--title", title,
            "--body", body,
        ])
        url = out.strip().splitlines()[-1]
        number = int(url.rstrip("/").rsplit("/", 1)[-1])
        return PullRequestResult(url=url, number=number)
