# Reviewer image — PROPOSAL §9 option (ii).
#
# Bakes the toolchain and node_modules so that:
#   - the per-round copy is SOURCE-ONLY (no 412-package tree crossing 9p every round)
#   - the 38s-per-run `apt-get install` measured on the stock image disappears
#   - the package registry leaves the runtime path entirely (§9.2)
#
# Versions match what the repo actually uses rather than newest-available:
#   node 20   — local runtime is v20.19.4; CI pins node-version "20"
#   python3.11 — CI pins python-version "3.11"; bookworm ships 3.11
#
# This image is IDENTIFIED BY DIGEST, not by tag (Control 4, §9.6.1). A tag is a mutable
# pointer; pinning to one is pinning to nothing. The digest is recorded in image.manifest.json
# and asserted before every run, fail-closed on anything unrecognised.
#
# It does NOT contain the repo. Source arrives at run time as a disposable copy.
FROM node:20-slim

# git      — prove-controls.sh tree_hash() runs `git status --porcelain`
# python3  — the loop invokes python
# curl     — handoff-loop.sh health probe
# ca-certs — TLS for the model endpoint and fonts.gstatic.com (§9.2)
RUN apt-get update \
 && apt-get install -y --no-install-recommends git python3 curl ca-certificates \
 && ln -sf /usr/bin/python3 /usr/local/bin/python \
 && rm -rf /var/lib/apt/lists/*

# node_modules baked from the lockfile.
#
# KNOWN DEVIATION, recorded rather than worked around silently. `npm ci` is the correct
# instruction here — it installs exactly the lockfile and fails on drift, which is what a
# reproducible image needs. It CANNOT be used on this branch:
#
#   npm error `npm ci` can only install packages when your package.json and
#   npm error package-lock.json ... are in sync.
#   npm error Missing: @testing-library/dom@10.4.1 from lock file   (+9 transitive)
#
# `@testing-library/dom` is a peer of `@testing-library/react`. origin/main's lock CONTAINS it;
# this branch's lock does not — the desync is BRANCH-ONLY and main is unaffected. Regenerating
# the lock is a dependency change that belongs in its own reviewed commit, not smuggled into an
# image build, so this uses `npm install` and the defect is reported instead.
#
# CONSEQUENCE, stated plainly: the image is reproducible BY DIGEST (Control 4) but NOT
# rebuildable-identical from the lockfile. That is exactly the limit §9.6.1 already names —
# "binds the image, not its contents' provenance". Switch back to `npm ci` once the lock is fixed.
WORKDIR /opt/reviewer/dashboard
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm install --no-audit --no-fund

# The repo mounts/copies to /work at run time; node_modules is symlinked in from the image so
# the copy never has to carry it.
WORKDIR /work
