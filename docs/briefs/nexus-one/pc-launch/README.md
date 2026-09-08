# Nexus One PC launch supplement

Prepared 8 September 2026. This is launch preparation, not a deployed runtime.

## Start

Save `Start-Nexus-PC.ps1` to Downloads, alongside the original `Nexus-One-Implementation-Package.zip`. Open a normal (not administrator) PowerShell in the existing Pi-Dev-Ops checkout. Do not close or alter unrelated work.

Run:

```powershell
& "$HOME\Downloads\Start-Nexus-PC.ps1"
```

Custom Downloads or checkout location:

```powershell
& "FULL-PATH-TO\Start-Nexus-PC.ps1" -PackagePath "FULL-PATH-TO\Nexus-One-Implementation-Package.zip" -RepositoryPath "FULL-PATH-TO\Pi-Dev-Ops"
```

The script checks the selected repository, validates the exact ZIP and its twelve packaged checksums, creates a new reference directory under LocalAppData, writes the supplemental prompt and an observation manifest, and opens Claude in plan mode outside the repository. It does not fetch, checkout, clean, stash, edit source, install dependencies, change accounts, change existing permissions, enrol workers or activate production. The CLI's existing native/user/managed hooks are not disabled; startup therefore remains supervised. Plan mode is not an OS sandbox. `--add-dir` makes the selected repository accessible for inspection and can grant edit access in other modes, so do not switch modes before admission.

Check `/status` for the retained Claude Max account and `/usage`. Do not paste credentials into the session. Then paste:

```text
Read ./NEXUS-PC-BOOTSTRAP.txt and ./BOOTSTRAP-MANIFEST.json. Perform the finite startup inspection and Slice A planning only.
```

If Windows blocks the unsigned script under its execution policy, do not change that policy to Bypass or run as administrator. Read the script or the standalone text, verify/extract the original ZIP using the operator's approved tools, and use the text as the finite read-only startup instruction. Windows worker execution still requires the existing admission evidence.

## From inspection to unattended operation

The finite bootstrap identifies the current task, exact pilot, host readiness, billing identity, effective hooks and authoritative continuation owner. The current package keeps Windows review-only. An already admitted Mac worker is the first pilot's preferred execution path. WSL2 is a supported Claude sandbox platform, but must be separately enrolled and proved; installing WSL2 does not grant authority.

A bounded build needs a current accepted spec, exact workspace, permitted operations/data destinations, parent budget/time envelope, tested containment and cancellation, and independent review. No second continuation owner or indefinite retry wrapper should be started. No native `/goal` until its overlap with the repo skill and existing Stop hooks is resolved. Native goal completion is not independent inspection; native goal counters can reset on resume. Durable Mission Control checkpoints and budgets remain authoritative.

Inside a proved admitted sandbox, auto-approved sandboxed commands can remove many interruptions. Auto mode may be useful where the exact CLI/account/model supports it, but neither it nor a prompt is a security boundary. `acceptEdits` is not full unattended automation. Do not use `--dangerously-skip-permissions` for this rebuild.

Use one builder initially, then an independent reviewer. Keep API fallback, overage and new spending disabled unless explicitly authorised. Do not confuse `--max-budget-usd` (documented for API/print-mode spend) with a hard cap on interactive Max subscription consumption.

Keep the execution host awake and connected during a foreground run. A named resumed session restores conversation, not lost authority. Before claiming reboot-safe 24/7 operation, test the supervisor, checkpoint restoration, re-authentication, fencing, cancellation and independent verification on an eligible host. No such supervisor is installed by this supplement.

## What was checked here

All twelve internal package checksums matched. The separately supplied MASTER_BLUEPRINT.md matched the archived copy. The launcher text and paths were reviewed, but PowerShell/Claude execution was NOT tested on the user's PC; no native Windows runtime was available in this environment. The JSON report concerns package integrity only. These checks do not prove source cleanliness, sandboxing, account quotas or live-system readiness.

## Primary documentation used

- Claude Code Windows and WSL setup: https://code.claude.com/docs/en/setup
- CLI reference, plan mode, account status and resume: https://code.claude.com/docs/en/cli-reference
- Bash sandbox and escape/failure options: https://code.claude.com/docs/en/sandboxing
- Settings and precedence: https://code.claude.com/docs/en/settings
- Permission modes: https://code.claude.com/docs/en/permission-modes
- Native goal continuation and counter reset: https://code.claude.com/docs/en/goal
- Pro/Max authentication and usage: https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan

Documentation is evidence of a vendor feature, not evidence that the exact host has it. Recheck the installed version and actual behaviour.
