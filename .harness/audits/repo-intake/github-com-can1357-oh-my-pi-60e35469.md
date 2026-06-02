# Repo Intake Audit

- Created: 2026-06-01T21:01:45+00:00
- Source URL: https://github.com/can1357/oh-my-pi.git
- Route: repo-intake
- Status: intake-required
- No build started: True
- Fit classification: tool-adoption
- Recommended next lane: spike-or-feature-with-tests

## Founder command

https://github.com/can1357/oh-my-pi.git this repo has 40+ providers, 32 built-in tools, LSP/DAP ops, and Rust core

## Captured capability claims

- 40+ providers
- 32 built-in
- providers
- built-in
- tools
- LSP/DAP
- Rust

## Initial integration risks

- Do not vendor, fork, or implement until read-only scan is complete.
- Verify license, maintenance activity, security posture, and overlap with existing Pi-Dev-Ops components.

## Read-only scan evidence

- Sandbox path: D:\Pi-Dev-Ops\.harness\tmp\repo-intake\github-com-can1357-oh-my-pi-60e35469
- Clone command: git clone --depth 1 --filter=blob:none <source_url> <sandbox_path>
- Build started: False
- License: MIT
- Detected stack:
  - typescript/javascript
  - rust
  - docker
  - github-actions
- Manifests:
  - package.json
  - Cargo.toml
  - Dockerfile
  - .github/workflows/ci.yml
- CI/test commands:
  - pytest
  - ruff
- Scan risk flags:
  - node-manifest-without-lockfile

## README/docs summary

<p align="center">
  <img src="https://github.com/can1357/oh-my-pi/blob/main/assets/hero.png?raw=true" alt="omp">
</p>

<p align="center">
  <strong>A coding agent with the IDE wired in.</strong>
  <strong><a href="https://omp.sh">omp.sh</a></strong>
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/@oh-my-pi/pi-coding-agent"><img src="https://img.shields.io/npm/v/@oh-my-pi/pi-coding-agent?style=flat&colorA=222222&colorB=CB3837" alt="npm version"></a>
  <a href="https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/CHANGELOG.md"><img src="https://img.shields.io/badge/changelog-keep-E05735?style=flat&colorA=222222" alt="Changelog"></a>
  <a href="https://github.com/can1357/oh-my-pi/actions"><img src="https://img.shields.io/github/actions/workflow/status/can1357/oh-my-pi/ci.yml?style=flat&colorA=222222&colorB=3FB950" alt="CI"></a>
  <a href="https://github.com/can1357/oh-my-pi/blob/main/LICENSE"><img src="https://img.shields.io/github/license/can1357/oh-my-pi?style=flat&colorA=222222&colorB=58A6FF" alt="License"></a>
  <a href="https://www.typescriptlang.org"><img src="https://img.shields.io/badge/TypeScript-3178C6?style=flat&colorA=222222&logo=typescrip

## Next required evidence before build

- README/docs summary
- manifest/package map
- license finding
- CI/test commands
- fit classification: reference-only/tool-adoption/fork-and-adapt/vendor-risk/not-fit
