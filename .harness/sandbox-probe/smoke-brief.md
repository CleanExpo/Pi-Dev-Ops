# Smoke brief — wrapper verification only

This is NOT a code review. It verifies that the reviewer can execute.

Do exactly this:

1. Run: `node .harness/sandbox-probe/probe.cjs` — report its output verbatim.
2. Run: `cd dashboard; npx vitest run __tests__/command-centre-auth-coverage.test.ts` — report
   the summary lines verbatim.
3. Do not edit, create or delete any file.

End with exactly one line: `VERDICT: PASS` if both commands ran, or
`VERDICT: FAIL — <reason>` if either could not.
