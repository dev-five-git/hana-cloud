"""Build and validate generated Hana Cloud firmware artifacts."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FQBN_PATTERN = re.compile(r"^[A-Za-z0-9_-]+:[A-Za-z0-9_-]+:[A-Za-z0-9_-]+$")
USB_ID_PATTERN = re.compile(r"^[0-9a-f]{4}$")
CONFIDENCE_VALUES = {"exact", "likely", "ambiguous"}
FIRMWARE_LIMIT = 2 * 1024 * 1024


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _array(value: Any, field: str, *, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list) or (nonempty and not value):
        suffix = " a non-empty array" if nonempty else " an array"
        raise ValueError(f"{field} must be{suffix}")
    return value


def _keys(value: dict[str, Any], required: set[str], optional: set[str], field: str) -> None:
    missing = required - value.keys()
    unknown = value.keys() - required - optional
    if missing:
        raise ValueError(f"{field} is missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"{field} has unknown fields: {', '.join(sorted(unknown))}")


def _text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        raise ValueError(f"{field} must contain 1 to {maximum} characters")
    return value


def _aliases(value: Any, field: str) -> list[str]:
    aliases = _array(value, field)
    rendered = [_text(alias, field, 100) for alias in aliases]
    if len(set(rendered)) != len(rendered):
        raise ValueError(f"{field} contains duplicate aliases")
    return rendered


def _validate_detect(value: Any) -> dict[str, Any]:
    detect = _object(value, "detect")
    _keys(detect, {"usb"}, set(), "detect")
    usb = _array(detect["usb"], "detect.usb", nonempty=True)
    rendered = []
    for index, raw_matcher in enumerate(usb):
        field = f"detect.usb[{index}]"
        matcher = _object(raw_matcher, field)
        _keys(
            matcher,
            {"vid", "pid", "confidence"},
            {"manufacturerAliases", "productAliases"},
            field,
        )
        vid = matcher["vid"]
        pid = matcher["pid"]
        confidence = matcher["confidence"]
        if not isinstance(vid, str) or not USB_ID_PATTERN.fullmatch(vid):
            raise ValueError(f"{field}.vid must be four lowercase hex characters")
        if not isinstance(pid, str) or not USB_ID_PATTERN.fullmatch(pid):
            raise ValueError(f"{field}.pid must be four lowercase hex characters")
        if confidence not in CONFIDENCE_VALUES:
            raise ValueError(f"{field}.confidence is unsupported")
        item: dict[str, Any] = {"vid": vid, "pid": pid, "confidence": confidence}
        if "manufacturerAliases" in matcher:
            item["manufacturerAliases"] = _aliases(
                matcher["manufacturerAliases"], f"{field}.manufacturerAliases"
            )
        if "productAliases" in matcher:
            item["productAliases"] = _aliases(
                matcher["productAliases"], f"{field}.productAliases"
            )
        rendered.append(item)
    return {"usb": rendered}


def _validate_wiring(value: Any) -> list[dict[str, str]]:
    wiring = _array(value, "wiring", nonempty=True)
    rendered = []
    for index, raw_connection in enumerate(wiring):
        field = f"wiring[{index}]"
        connection = _object(raw_connection, field)
        _keys(connection, {"from", "to"}, {"note"}, field)
        item = {
            "from": _text(connection["from"], f"{field}.from", 40),
            "to": _text(connection["to"], f"{field}.to", 100),
        }
        if "note" in connection:
            item["note"] = _text(connection["note"], f"{field}.note", 200)
        rendered.append(item)
    return rendered


@dataclass(frozen=True)
class BoardSource:
    slug: str
    id: str
    name: str
    sketch_path: str
    fqbn: str
    detect: dict[str, Any]
    wiring: list[dict[str, str]]
    image: dict[str, str] | None = None

    @classmethod
    def from_document(cls, slug: str, raw: Any) -> "BoardSource":
        if not SLUG_PATTERN.fullmatch(slug):
            raise ValueError("source filename slug is invalid")
        document = _object(raw, "source")
        _keys(
            document,
            {"schemaVersion", "id", "name", "sketch", "detect", "wiring"},
            {"image"},
            "source",
        )
        if document["schemaVersion"] != 1:
            raise ValueError("source.schemaVersion must be 1")
        board_id = document["id"]
        if not isinstance(board_id, str) or not ID_PATTERN.fullmatch(board_id):
            raise ValueError("source.id is invalid")

        sketch = _object(document["sketch"], "sketch")
        _keys(sketch, {"path", "fqbn"}, set(), "sketch")
        expected_sketch_path = f"boards/{slug}.ino"
        if sketch["path"] != expected_sketch_path:
            raise ValueError(f"sketch.path must be {expected_sketch_path}")
        fqbn = sketch["fqbn"]
        if not isinstance(fqbn, str) or not FQBN_PATTERN.fullmatch(fqbn):
            raise ValueError("sketch.fqbn is invalid")

        image = None
        if "image" in document:
            raw_image = _object(document["image"], "image")
            _keys(raw_image, {"path", "alt"}, set(), "image")
            expected_image_path = f"boards/{slug}.png"
            if raw_image["path"] != expected_image_path:
                raise ValueError(f"image.path must be {expected_image_path}")
            image = {
                "path": expected_image_path,
                "alt": _text(raw_image["alt"], "image.alt", 300),
            }

        return cls(
            slug=slug,
            id=board_id,
            name=_text(document["name"], "source.name", 100),
            sketch_path=expected_sketch_path,
            fqbn=fqbn,
            detect=_validate_detect(document["detect"]),
            wiring=_validate_wiring(document["wiring"]),
            image=image,
        )


@dataclass(frozen=True)
class FirmwareArtifact:
    path: str
    data: bytes
    source_sha256: str
    arduino_cli: str
    platform: str
    image_sha256: str | None = None

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.data)

    @property
    def size(self) -> int:
        return len(self.data)


def load_sources(root: Path) -> list[BoardSource]:
    source_dir = root / "sources" / "boards"
    if not source_dir.is_dir():
        raise ValueError("sources/boards directory is missing")
    sources = []
    ids: set[str] = set()
    for path in sorted(source_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(f"cannot read {path.relative_to(root).as_posix()}: {error}") from error
        source = BoardSource.from_document(path.stem, raw)
        if source.id in ids:
            raise ValueError(f"duplicate source id: {source.id}")
        ids.add(source.id)
        sources.append(source)
    if not sources:
        raise ValueError("at least one board source is required")
    return sources


def render_manifest(source: BoardSource, artifact: FirmwareArtifact) -> dict[str, Any]:
    expected_path = f"boards/{source.slug}.hex"
    if artifact.path != expected_path:
        raise ValueError(f"firmware path must be {expected_path}")
    firmware = {
        "path": artifact.path,
        "format": "intel-hex",
        "size": artifact.size,
        "sha256": artifact.sha256,
        "fqbn": source.fqbn,
        "source": {
            "path": source.sketch_path,
            "sha256": artifact.source_sha256,
        },
        "toolchain": {
            "arduinoCli": artifact.arduino_cli,
            "platform": artifact.platform,
        },
    }
    manifest: dict[str, Any] = {
        "schemaVersion": 2,
        "id": source.id,
        "firmware": firmware,
        "wiring": copy.deepcopy(source.wiring),
    }
    if source.image is not None:
        if artifact.image_sha256 is None:
            raise ValueError("image sha256 is required when an image is configured")
        manifest["image"] = {
            "path": source.image["path"],
            "sha256": artifact.image_sha256,
            "alt": source.image["alt"],
        }
    return manifest


def render_registry(
    registry: dict[str, Any], published_boards: list[dict[str, Any]]
) -> dict[str, Any]:
    rendered = copy.deepcopy(registry)
    previous = rendered.get("boards")
    boards = copy.deepcopy(published_boards)
    if previous != boards:
        revision = rendered.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise ValueError("registry revision must be a positive integer")
        rendered["revision"] = revision + 1
    rendered["boards"] = boards
    return rendered


CompileRunner = Callable[[str, str, Path, Path], None]


def _run_arduino_cli(cli: str, fqbn: str, staged_sketch: Path, output_dir: Path) -> None:
    subprocess.run(
        [
            cli,
            "compile",
            "--clean",
            "--fqbn",
            fqbn,
            "--output-dir",
            str(output_dir),
            str(staged_sketch),
        ],
        check=True,
    )


def validate_intel_hex(data: bytes) -> None:
    if not data or len(data) > FIRMWARE_LIMIT:
        raise ValueError(f"firmware must contain 1 to {FIRMWARE_LIMIT} bytes")
    try:
        lines = data.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("firmware is not ASCII Intel HEX") from error
    if not lines:
        raise ValueError("firmware has no Intel HEX records")

    saw_end_of_file = False
    for line_number, line in enumerate(lines, start=1):
        if saw_end_of_file:
            raise ValueError("Intel HEX contains a record after end-of-file")
        if not line.startswith(":") or len(line) == 1 or len(line[1:]) % 2:
            raise ValueError(f"Intel HEX record {line_number} has invalid syntax")
        try:
            record = bytes.fromhex(line[1:])
        except ValueError as error:
            raise ValueError(f"Intel HEX record {line_number} is not hexadecimal") from error
        if len(record) < 5 or len(record) != record[0] + 5:
            raise ValueError(f"Intel HEX record {line_number} has an invalid byte count")
        if sum(record) & 0xFF:
            raise ValueError(f"Intel HEX record {line_number} has an invalid checksum")
        record_type = record[3]
        if record_type not in {0, 1, 2, 3, 4, 5}:
            raise ValueError(f"Intel HEX record {line_number} has an unsupported type")
        if record_type == 1:
            if record[0] != 0 or record[1:3] != b"\x00\x00":
                raise ValueError("Intel HEX end-of-file record is malformed")
            saw_end_of_file = True
    if not saw_end_of_file:
        raise ValueError("Intel HEX end-of-file record is missing")


def _read_normal_hex(output_dir: Path, slug: str) -> bytes:
    path = output_dir / f"{slug}.ino.hex"
    if not path.is_file():
        raise ValueError(f"compiler did not emit the normal application HEX for {slug}")
    data = path.read_bytes()
    validate_intel_hex(data)
    return data


def compile_reproducible(
    root: Path,
    source: BoardSource,
    cli: str,
    *,
    runner: CompileRunner = _run_arduino_cli,
) -> bytes:
    source_path = root / source.sketch_path
    if not source_path.is_file():
        raise ValueError(f"sketch is missing: {source.sketch_path}")

    with tempfile.TemporaryDirectory(prefix=f"hana-{source.slug}-") as directory:
        build_root = Path(directory)
        results = []
        for attempt in (1, 2):
            staged_sketch = build_root / f"sketch-{attempt}" / source.slug
            staged_sketch.mkdir(parents=True)
            shutil.copyfile(source_path, staged_sketch / f"{source.slug}.ino")
            output_dir = build_root / f"output-{attempt}"
            runner(cli, source.fqbn, staged_sketch, output_dir)
            results.append(_read_normal_hex(output_dir, source.slug))

    if results[0] != results[1]:
        raise ValueError(f"compiler output is not reproducible for {source.id}")
    return results[0]


def validate_changed_paths(
    changed_paths: list[str],
    base_registry: dict[str, Any] | None,
    current_registry: dict[str, Any] | None,
) -> None:
    for raw_path in changed_paths:
        path = raw_path.replace("\\", "/")
        if path.startswith("boards/") and (path.endswith(".hex") or path.endswith(".json")):
            raise ValueError(f"generated file cannot be changed in a pull request: {path}")

    if "registry.json" in {path.replace("\\", "/") for path in changed_paths}:
        if not isinstance(base_registry, dict) or not isinstance(current_registry, dict):
            raise ValueError("registry.json comparison requires both revisions")
        if base_registry.get("boards") != current_registry.get("boards"):
            raise ValueError("registry.json boards are generated and cannot be changed directly")
