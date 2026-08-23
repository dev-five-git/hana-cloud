# Firmware Supply Chain Design

Status: approved on 2026-08-24

## Goal

Hana Cloud accepts reviewable Arduino sketch sources from same-repository and
fork pull requests, then publishes an upload-ready Intel HEX whose bytes are
provably derived from those sources. HanBeon downloads the HEX and does not
need Arduino CLI on the user's computer.

## Trust boundary

Contributors may edit only authoring inputs:

- `sources/boards/<slug>.json`
- `boards/<slug>.ino`
- optional `boards/<slug>.png`

The following are generated outputs and pull-request validation rejects direct
changes to them:

- `boards/<slug>.hex`
- `boards/<slug>.json`
- the `boards` array in `registry.json`

Application profiles and the `apps` array remain human-managed. The protected
`main` branch requires pull requests and validation, blocks deletion and force
pushes, and grants an always-on bypass only to the repository's GitHub Actions
App so the trusted publisher can add generated output.

## Authoring input

`sources/boards/<slug>.json` contains schema version, stable board ID, display
name, sketch path and FQBN, USB detection metadata, wiring, and optional image
metadata. It contains no generated path, size, or hash. A repository-owned
toolchain lock maps the FQBN platform to Arduino AVR Core 1.8.8 and pins
Arduino CLI 1.5.1.

## Published contract

The publisher creates a schema-version 2 board manifest with this firmware
shape:

```json
{
  "path": "boards/arduino-uno-r3.hex",
  "format": "intel-hex",
  "size": 12345,
  "sha256": "64 lowercase hex characters",
  "fqbn": "arduino:avr:uno",
  "source": {
    "path": "boards/arduino-uno-r3.ino",
    "sha256": "64 lowercase hex characters"
  },
  "toolchain": {
    "arduinoCli": "1.5.1",
    "platform": "arduino:avr@1.8.8"
  }
}
```

The publisher emits the normal application HEX, never the bootloader-inclusive
HEX. It stores byte size and SHA-256 for download limits and integrity checks.
The root registry receives the generated manifest hash and increments revision
only when its published contents change.

## Data flow

Pull-request validation runs with read-only permissions. It rejects generated
output edits, validates authoring data, and clean-compiles every affected
sketch twice with the pinned toolchain to prove reproducible output.

After an accepted source change reaches `main`, the trusted publisher checks
out the latest `main`, performs the same two clean builds, compares the HEX
bytes, regenerates all derived files, and commits them atomically as
`github-actions[bot]`. A bot push made with `GITHUB_TOKEN` does not recursively
start another publisher run. Concurrent publishers serialize and regenerate
from the latest `main` before pushing.

Between the source merge and generated commit, existing boards remain on their
previous valid HEX and newly added boards remain absent from `registry.json`.
No client is pointed at an incomplete artifact.

## Failure handling

- Compile failure, nondeterministic output, malformed Intel HEX, missing output,
  unsafe path, schema failure, or hash mismatch stops publication.
- A failed publisher never changes `registry.json` or any public manifest.
- A non-fast-forward push causes a fresh generation attempt from current
  `origin/main`; retries are bounded.
- The workflow uses exact toolchain and action versions and minimal token
  permissions.

## Verification

Unit tests cover path validation, generated-file policy, canonical manifests,
hash/size calculation, registry revision behavior, and normal-versus-bootloader
artifact selection. Integration verification compiles the current Uno sketch
twice, compares bytes, checks Intel HEX syntax, and confirms regeneration leaves
the repository clean. The initial generated commit must contain a HEX whose
hash matches both the public manifest and a fresh pinned-toolchain build.

## Non-goals

This wave does not implement firmware upload in HanBeon, identify boards at
runtime, or bundle an uploader executable. Those remain in the separate
HanBeon uploader pull request.
