# Runtime dependency lock

`requirements.txt` declares the existing runtime and test dependencies.
`requirements.lock` is their hash-verified Linux/Python 3.12 resolution, shared
by the deployment image and the main Python/local-smoke CI jobs.

The initial reconciliation preserves compatible registry versions from the
existing `uv.lock`, then pins existing locally installed versions of PyGithub,
tenacity, pytest, pytest-asyncio and setuptools where the root lock
had no entry. The installed SDK 0.2.96 was yanked and scheduled for deletion
on or after 2026-09-19; the lock therefore resolves its existing declaration
to 0.2.157. Dependencies absent from both baselines are resolved from their
existing declarations. No new direct dependency was introduced. The root
`uv.lock` still serves the separate `pyproject.toml` package graph; it is not
the server deployment lock.

Reconciliation with current Main retains all prior compatible pins and adds only
its existing `psycopg[binary]==3.3.5` declaration (`psycopg` and
`psycopg-binary`). The deployment graph contains 97 pinned distributions.

Refresh from the existing output so compatible pins are retained:

```sh
uv pip compile app/requirements.txt --python-version 3.12 --python-platform linux --generate-hashes --no-header --output-file app/requirements.lock
```

Review dependency changes and run the regression suite before accepting a
refresh. CI and Docker install with `pip install --require-hashes -r
app/requirements.lock`. The Claude CLI is separately pinned in `Dockerfile`
to the observed workstation version, 2.1.267. Pinning establishes identity;
it does not prove sandbox support, subscription authorization or compatibility.

The image's operating-system packages/base image are not fully locked by this
file. Validate the actual Linux image in CI before deployment; Windows unit
tests cannot establish Linux runtime compatibility.
