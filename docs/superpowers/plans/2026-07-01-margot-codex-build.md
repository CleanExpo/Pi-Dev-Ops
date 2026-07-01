# Margot Codex Build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan one step at a time. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Codex-ready Margot build workflow that produces a full project/variant asset-generation packet for review and optional live generation follow-up.

**Architecture:** Extend the existing `scripts/margot_generate.py` substrate rather than adding a second generator. Single-asset mode remains unchanged; matrix mode builds every selected project/variant payload and writes a timestamped build packet under `.harness/margot/build-packets/`.

**Tech Stack:** Python stdlib, existing JSON manifest at `.harness/margot/assets/margot_identity.json`, pytest.

## Global Constraints

- Dry-run must remain the default.
- Live OpenAI generation must require `--live` and `OPENAI_API_KEY`.
- Matrix mode must not run live generation, to avoid accidental batch spend.
- No secrets committed or printed.
- Preserve unrelated dirty `.harness` files.
- No backend, dashboard, auth, database, or deployment changes.

---

### Task 1: Matrix Build Packet

**Files:**
- Modify: `scripts/margot_generate.py`
- Test: `tests/test_margot_asset_generator.py`

**Interfaces:**
- Consumes: `load_manifest(path) -> dict`, `build_image_payload(...) -> dict`, `output_paths(...) -> tuple[Path, Path]`, `build_provenance(...) -> dict`
- Produces: `build_matrix_packet(manifest, projects=None, variants=None, notes="") -> dict`

- [x] **Step 1: Add tests for matrix packet**

```python
def test_build_matrix_packet_includes_selected_pairs(tmp_path: Path):
    manifest = _manifest(tmp_path)
    packet = MG.build_matrix_packet(
        manifest,
        projects=["unite-group", "synthex"],
        variants=["avatar", "dashboard"],
    )
    assert packet["schema_version"] == 1
    assert packet["mode"] == "dry_run_matrix"
    assert packet["item_count"] == 4
    assert {(i["project"], i["variant"]) for i in packet["items"]} == {
        ("unite-group", "avatar"),
        ("unite-group", "dashboard"),
        ("synthex", "avatar"),
        ("synthex", "dashboard"),
    }
    assert all(i["payload"]["model"] == "gpt-image-2" for i in packet["items"])
```

- [x] **Step 2: Add matrix implementation**

```python
def build_matrix_packet(
    manifest: dict[str, Any],
    *,
    projects: list[str] | None = None,
    variants: list[str] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    selected_projects = projects or sorted(manifest["projects"].keys())
    selected_variants = variants or sorted(manifest["variants"].keys())
    items = []
    for project in selected_projects:
        _resolve_project(manifest, project)
        for variant in selected_variants:
            _resolve_variant(manifest, variant)
            payload = build_image_payload(manifest, project=project, variant=variant, notes=notes)
            image_path, provenance_path = output_paths(
                manifest, project=project, variant=variant, prompt=payload["prompt"]
            )
            provenance = build_provenance(
                manifest, project=project, variant=variant, payload=payload, output_path=image_path
            )
            items.append({
                "project": project,
                "variant": variant,
                "payload": payload,
                "provenance": provenance,
                "planned_image_path": str(image_path),
                "planned_provenance_path": str(provenance_path),
            })
    return {
        "schema_version": manifest["schema_version"],
        "mode": "dry_run_matrix",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "canonical_asset_path": manifest["canonical_asset_path"],
        "item_count": len(items),
        "items": items,
    }
```

- [x] **Step 3: Run matrix test**

Run: `python -m pytest tests/test_margot_asset_generator.py::test_build_matrix_packet_includes_selected_pairs -q`

Expected: one passing test.

### Task 2: CLI Build Packet Mode

**Files:**
- Modify: `scripts/margot_generate.py`
- Test: `tests/test_margot_asset_generator.py`

**Interfaces:**
- Consumes: `build_matrix_packet(...) -> dict`
- Produces: CLI flags `--all`, `--projects`, `--variants`, `--write-build-packet`

- [x] **Step 1: Add CLI test**

```python
def test_cli_all_writes_build_packet(tmp_path: Path, capsys):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest(tmp_path)), encoding="utf-8")
    packet_path = tmp_path / "packet.json"
    code = MG.main([
        "--manifest", str(manifest_path),
        "--all",
        "--projects", "unite-group,synthex",
        "--variants", "avatar",
        "--write-build-packet", str(packet_path),
    ])
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["build_packet"] == str(packet_path)
    packet = json.loads(packet_path.read_text())
    assert packet["item_count"] == 2
```

- [x] **Step 2: Add CLI flags and writer**

```python
parser.add_argument("--all", action="store_true", help="Build a dry-run packet for all selected projects and variants.")
parser.add_argument("--projects", default="", help="Comma-separated project slugs for --all.")
parser.add_argument("--variants", default="", help="Comma-separated variant slugs for --all.")
parser.add_argument("--write-build-packet", nargs="?", const="", default=None, help="Write matrix packet JSON to a path or default build-packets directory.")
```

- [x] **Step 3: Ensure matrix mode rejects live**

```python
if args.all and args.live:
    raise MargotGenerationError("--all cannot be combined with --live; run live generation one asset at a time")
```

- [x] **Step 4: Run CLI test**

Run: `python -m pytest tests/test_margot_asset_generator.py::test_cli_all_writes_build_packet -q`

Expected: one passing test.

### Task 3: Verify Full Workflow

**Files:**
- No source edits unless verification reveals a bug.

**Interfaces:**
- Consumes: CLI matrix mode and existing single-asset mode.
- Produces: local build packet under `.harness/margot/build-packets/`.

- [x] **Step 1: Run tests**

Run: `python -m pytest tests/test_margot_asset_generator.py -q`

Expected: all tests pass.

- [x] **Step 2: Run dry matrix build**

Run: `python scripts/margot_generate.py --all --write-build-packet`

Expected: prints a JSON summary with `item_count` equal to 28 and a build packet path.

- [x] **Step 3: Run compile and hygiene checks**

Run:

```bash
python -m py_compile scripts/margot_generate.py
git diff --check -- scripts/margot_generate.py tests/test_margot_asset_generator.py docs/superpowers/plans/2026-07-01-margot-codex-build.md
```

Also run the project credential-pattern scan from `AGENTS.md` against the changed files.

Expected: compile/checks pass and credential scan has no matches.

- [ ] **Step 4: Commit and push**

Run:

```bash
git add docs/superpowers/plans/2026-07-01-margot-codex-build.md scripts/margot_generate.py tests/test_margot_asset_generator.py
git commit -m "feat(margot): add Codex build packet workflow"
git push -u origin codex/margot-codex-build
```
