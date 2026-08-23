# Hana Cloud Firmware Publisher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compile Hana Cloud Arduino sources into trusted Intel HEX artifacts and publish their manifests and registry hashes automatically.

**Architecture:** Fork pull requests can change authoring inputs but never generated firmware. A read-only validator compiles proposed sketches, while a post-merge GitHub Actions publisher using the sole write-enabled deploy-key bypass performs two clean builds and atomically commits generated HEX, manifests, and registry board metadata.

**Tech Stack:** Python 3 standard library, Arduino CLI, Arduino AVR Core, JSON Schema 2020-12, GitHub Actions.

**Spec:** `docs/designs/firmware-supply-chain.md`

## Global Constraints

- `docs/superpowers` must not be created or tracked.
- Fork pull-request jobs have read-only repository permissions.
- Arduino CLI and every platform core use exact versions from `.github/firmware-toolchain.json`.
- Only the normal application Intel HEX is published; `with_bootloader.hex` is forbidden.
- Generated JSON is UTF-8, two-space indented, key-order stable, and ends with one LF.
- Generated HEX is capped at 2 MiB and hashed as exact repository bytes.
- Human pull requests cannot change `boards/*.hex`, `boards/*.json`, or `registry.json#/boards`.
- HanBeon uploader code is outside this plan.

---

### Task 1: Authoring schema and deterministic metadata renderer

**Files:**
- Create: `sources/boards/arduino-uno-r3.json`
- Create: `schemas/board-source.schema.json`
- Create: `.github/firmware-toolchain.json`
- Create: `scripts/firmware.py`
- Create: `tests/test_firmware.py`

**Interfaces:**
- Consumes: source descriptors and toolchain lock JSON.
- Produces: `load_sources(root: Path)`, `render_manifest(source, firmware)`, and `render_registry(registry, published_boards)`.

- [ ] **Step 1: Write failing unit tests** for unsafe paths, missing source fields, canonical schema-version 2 manifest output, registry app preservation, and revision increments only on board changes.
- [ ] **Step 2: Run `python -m unittest -v tests.test_firmware`** and confirm failures are caused by missing production functions.
- [ ] **Step 3: Implement strict dataclasses, validators, canonical JSON, manifest rendering, and registry rendering** in `scripts/firmware.py`.
- [ ] **Step 4: Run `python -m unittest -v tests.test_firmware`** and confirm all Task 1 tests pass.
- [ ] **Step 5: Commit** with `feat: define firmware publishing inputs`.

### Task 2: Reproducible Arduino compiler and generated-file policy

**Files:**
- Modify: `scripts/firmware.py`
- Modify: `tests/test_firmware.py`
- Modify: `.gitattributes`

**Interfaces:**
- Consumes: `BoardSource`, Arduino CLI path, and a temporary build root.
- Produces: `compile_reproducible(root: Path, source: BoardSource, cli: str) -> bytes`, `is_intel_hex(data: bytes) -> bool`, and `validate_pr_changes(root: Path, base: str) -> None`.

- [ ] **Step 1: Write failing tests** proving normal `.ino.hex` selection, rejection of bootloader-only output, byte mismatch rejection, Intel HEX validation, and generated path/registry-board edit rejection.
- [ ] **Step 2: Run the focused unit tests** and verify expected failures.
- [ ] **Step 3: Implement staged sketch directories, two `arduino-cli compile --clean` invocations, exact byte comparison, size limits, Intel HEX checks, and semantic PR diff policy.**
- [ ] **Step 4: Run the full unit suite** and verify it passes.
- [ ] **Step 5: Commit** with `feat: build reproducible Arduino firmware`.

### Task 3: Published schema and current Uno artifact verification

**Files:**
- Modify: `schemas/board.schema.json`
- Modify: `README.md`
- Generated after merge: `boards/arduino-uno-r3.hex`
- Generated after merge: `boards/arduino-uno-r3.json`
- Generated after merge: `registry.json`

**Interfaces:**
- Consumes: the current `boards/arduino-uno-r3.ino` and pinned toolchain.
- Produces: schema-version 2 public manifest and verified Intel HEX bytes.

- [ ] **Step 1: Add failing schema/renderer fixtures** for `format`, `size`, source provenance, and toolchain provenance.
- [ ] **Step 2: Run tests and confirm the legacy public schema fails the new fixtures.**
- [ ] **Step 3: Update the public schema and documentation without manually adding generated output.**
- [ ] **Step 4: Install the locked toolchain in a temporary directory, compile the Uno sketch twice, and compare the exact HEX bytes.**
- [ ] **Step 5: Run generation in check/temporary mode and verify the prospective manifest and registry hashes.**
- [ ] **Step 6: Commit** with `docs: define compiled firmware contract`.

### Task 4: Fork-safe validation and trusted publisher workflows

**Files:**
- Create: `.github/workflows/validate.yml`
- Create: `.github/workflows/publish-firmware.yml`
- Create: `.github/CODEOWNERS`
- Modify: `scripts/firmware.py`
- Modify: `tests/test_firmware.py`

**Interfaces:**
- Consumes: pull-request base SHA or protected `main` head.
- Produces: required `validate` check and an atomic `github-actions[bot]` generated commit.

- [ ] **Step 1: Write failing tests** for no-op generation, bounded stale-main retry decisions, and generated commit contents.
- [ ] **Step 2: Run tests and verify expected failures.**
- [ ] **Step 3: Implement `validate-pr`, `compile`, `generate`, and `verify` CLI commands.**
- [ ] **Step 4: Add read-only fork PR validation and serialized `main` publisher workflows with exact action/toolchain versions and minimal permissions.**
- [ ] **Step 5: Run unit tests, workflow syntax checks, descriptor validation, and a clean local generation verification.**
- [ ] **Step 6: Commit** with `ci: publish compiled firmware from trusted sources`.

### Task 5: Merge, bot publication, and repository enforcement

**Files:**
- No additional source files unless verification reveals a defect.

**Interfaces:**
- Consumes: merged workflow and the dedicated publisher deploy key.
- Produces: published Uno HEX on `main` and an active main-branch ruleset.

- [ ] **Step 1: Run all local verification**: unit tests, Python compilation, JSON parsing/schema checks, two-build HEX comparison, and `git diff --check`.
- [ ] **Step 2: Open the Hana Cloud pull request and wait for the fork-safe validation check.**
- [ ] **Step 3: Merge the PR using its exact head SHA.**
- [ ] **Step 4: Observe the publisher bot commit and verify HEX size/hash, manifest hash, registry revision, and fresh-build byte equality.**
- [ ] **Step 5: Create an active `main` ruleset requiring pull requests, `validate`, and `guard-generated-files`, blocking deletion/force pushes, and granting always-on bypass only to the publisher deploy key.**
- [ ] **Step 6: Audit the ruleset and repository tree, then record final SHAs and URLs.**
