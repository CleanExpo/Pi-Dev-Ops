@echo off
REM ============================================================================
REM  update-skills.cmd  -  Pull latest Pi-Dev-Ops skills into ~/.claude/skills
REM
REM  - Fetches origin, fast-forwards when possible.
REM  - If upstream history was rewritten (force-push), auto-resets to origin/main
REM    (old commit stays recoverable via 'git reflog').
REM  - Re-links any brand-new skill folders as native symlinks.
REM  - Existing skills are symlinks into this repo, so a pull updates them with
REM    no copying. Machine-local skills (not in the repo) are left untouched.
REM
REM  Usage:  D:\Pi-Dev-Ops\update-skills.cmd
REM ============================================================================
setlocal
set "REPO=%~dp0"

REM --- Locate Git Bash (must be Git-for-Windows bash, NOT WSL/System32 bash) ---
set "GITBASH=C:\Program Files\Git\bin\bash.exe"
if not exist "%GITBASH%" set "GITBASH=C:\Program Files\Git\usr\bin\bash.exe"
if not exist "%GITBASH%" goto :nobash

echo [1/3] Fetching origin...
git -C "%REPO%." fetch origin
if errorlevel 1 goto :fail

git -C "%REPO%." merge-base --is-ancestor HEAD origin/main
if errorlevel 1 goto :reset
echo [2/3] Fast-forwarding to origin/main...
git -C "%REPO%." merge --ff-only origin/main
if errorlevel 1 goto :fail
goto :link

:reset
echo [2/3] History diverged - force-push detected - resetting to origin/main...
git -C "%REPO%." reset --hard origin/main
if errorlevel 1 goto :fail

:link
echo [3/3] Linking any new skill folders...
set "MSYS=winsymlinks:nativestrict"
"%GITBASH%" "%REPO%scripts\install_skills.sh"
if errorlevel 1 goto :fail
echo.
echo Done. Skills are up to date.
goto :eof

:nobash
echo ERROR: Git Bash not found. Edit the GITBASH path near the top of this script.
exit /b 1

:fail
echo ERROR: update failed - see output above.
exit /b 1
