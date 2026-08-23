from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import firmware  # noqa: E402


PROFILE_HASH = "739fdb18d93b143ffe6598c26177be73794f12052ad6018eca24d1912cbf22a8"
SOURCE_HASH = "57e7e3011111cfc98c740c32be386b85fab304edd1e458c090fad9d303ed8f2d"
HEX_HASH = "9e2df0a1190a1205c098889c455e5b76c4df18b5ccac2b7605da1575f05b64c5"


def source_document() -> dict:
    return {
        "schemaVersion": 1,
        "id": "arduino.uno-r3",
        "name": "Arduino Uno R3",
        "sketch": {
            "path": "boards/arduino-uno-r3.ino",
            "fqbn": "arduino:avr:uno",
        },
        "detect": {
            "usb": [
                {
                    "vid": "2341",
                    "pid": "0043",
                    "confidence": "exact",
                    "manufacturerAliases": ["Arduino LLC"],
                    "productAliases": ["Arduino Uno R3"],
                }
            ]
        },
        "wiring": [
            {
                "from": "D2",
                "to": "순간 누름 스위치 NO 단자",
                "note": "스위치 COM 단자는 GND에 연결",
            }
        ],
    }


def board_source() -> firmware.BoardSource:
    return firmware.BoardSource.from_document("arduino-uno-r3", source_document())


class BoardSourceTests(unittest.TestCase):
    def test_rejects_a_sketch_path_that_escapes_the_board_directory(self) -> None:
        document = source_document()
        document["sketch"]["path"] = "boards/../outside.ino"

        with self.assertRaisesRegex(ValueError, "sketch.path"):
            firmware.BoardSource.from_document("arduino-uno-r3", document)

    def test_rejects_a_human_supplied_generated_hash(self) -> None:
        document = source_document()
        document["sketch"]["sha256"] = "0" * 64

        with self.assertRaisesRegex(ValueError, "unknown"):
            firmware.BoardSource.from_document("arduino-uno-r3", document)


class RenderingTests(unittest.TestCase):
    def test_renders_the_literal_public_v2_manifest_contract(self) -> None:
        artifact = firmware.FirmwareArtifact(
            path="boards/arduino-uno-r3.hex",
            data=b":00000001FF\n",
            source_sha256=SOURCE_HASH,
            arduino_cli="1.5.1",
            platform="arduino:avr@1.8.8",
        )

        manifest = firmware.render_manifest(board_source(), artifact)

        self.assertEqual(
            manifest,
            {
                "schemaVersion": 2,
                "id": "arduino.uno-r3",
                "firmware": {
                    "path": "boards/arduino-uno-r3.hex",
                    "format": "intel-hex",
                    "size": 12,
                    "sha256": HEX_HASH,
                    "fqbn": "arduino:avr:uno",
                    "source": {
                        "path": "boards/arduino-uno-r3.ino",
                        "sha256": SOURCE_HASH,
                    },
                    "toolchain": {
                        "arduinoCli": "1.5.1",
                        "platform": "arduino:avr@1.8.8",
                    },
                },
                "wiring": [
                    {
                        "from": "D2",
                        "to": "순간 누름 스위치 NO 단자",
                        "note": "스위치 COM 단자는 GND에 연결",
                    }
                ],
            },
        )

    def test_registry_preserves_apps_and_increments_for_changed_boards(self) -> None:
        registry = {
            "schemaVersion": 1,
            "revision": 2,
            "apps": [
                {
                    "id": "pdf-viewer",
                    "path": "apps/pdf-viewer.json",
                    "sha256": PROFILE_HASH,
                }
            ],
            "boards": [],
        }
        board = {
            "id": "arduino.uno-r3",
            "name": "Arduino Uno R3",
            "manifest": "boards/arduino-uno-r3.json",
            "sha256": SOURCE_HASH,
            "detect": source_document()["detect"],
        }

        rendered = firmware.render_registry(registry, [board])

        self.assertEqual(rendered["apps"], registry["apps"])
        self.assertEqual(rendered["boards"], [board])
        self.assertEqual(rendered["revision"], 3)
        self.assertEqual(registry["revision"], 2)
        self.assertEqual(registry["boards"], [])

    def test_registry_keeps_revision_when_published_boards_are_unchanged(self) -> None:
        board = {
            "id": "arduino.uno-r3",
            "name": "Arduino Uno R3",
            "manifest": "boards/arduino-uno-r3.json",
            "sha256": SOURCE_HASH,
            "detect": source_document()["detect"],
        }
        registry = {
            "schemaVersion": 1,
            "revision": 9,
            "apps": [],
            "boards": [copy.deepcopy(board)],
        }

        rendered = firmware.render_registry(registry, [board])

        self.assertEqual(rendered["revision"], 9)

    def test_canonical_json_uses_utf8_two_spaces_and_one_final_lf(self) -> None:
        rendered = firmware.canonical_json({"label": "한번", "nested": {"value": 1}})

        self.assertEqual(
            rendered,
            b'{\n  "label": "\xed\x95\x9c\xeb\xb2\x88",\n  "nested": {\n    "value": 1\n  }\n}\n',
        )


class CompilerTests(unittest.TestCase):
    VALID_HEX = b":0100000001FE\n:00000001FF\n"

    def compile_in_temporary_root(self, outputs: list[dict[str, bytes]]) -> bytes:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sketch = root / "boards" / "arduino-uno-r3.ino"
            sketch.parent.mkdir(parents=True)
            sketch.write_text("void setup() {}\nvoid loop() {}\n", encoding="utf-8")
            calls = 0

            def runner(
                cli: str,
                fqbn: str,
                staged_sketch: Path,
                output_dir: Path,
            ) -> None:
                nonlocal calls
                self.assertEqual(cli, "arduino-cli")
                self.assertEqual(fqbn, "arduino:avr:uno")
                self.assertEqual(
                    (staged_sketch / "arduino-uno-r3.ino").read_text(encoding="utf-8"),
                    "void setup() {}\nvoid loop() {}\n",
                )
                output_dir.mkdir(parents=True, exist_ok=True)
                for name, data in outputs[calls].items():
                    (output_dir / name).write_bytes(data)
                calls += 1

            result = firmware.compile_reproducible(
                root,
                board_source(),
                "arduino-cli",
                runner=runner,
            )
            self.assertEqual(calls, 2)
            return result

    def test_selects_the_normal_hex_and_never_the_bootloader_image(self) -> None:
        outputs = [
            {
                "arduino-uno-r3.ino.hex": self.VALID_HEX,
                "arduino-uno-r3.ino.with_bootloader.hex": b"bootloader",
            },
            {
                "arduino-uno-r3.ino.hex": self.VALID_HEX,
                "arduino-uno-r3.ino.with_bootloader.hex": b"different bootloader",
            },
        ]

        result = self.compile_in_temporary_root(outputs)

        self.assertEqual(result, self.VALID_HEX)

    def test_rejects_builds_that_only_emit_a_bootloader_image(self) -> None:
        outputs = [
            {"arduino-uno-r3.ino.with_bootloader.hex": self.VALID_HEX},
            {"arduino-uno-r3.ino.with_bootloader.hex": self.VALID_HEX},
        ]

        with self.assertRaisesRegex(ValueError, "normal application HEX"):
            self.compile_in_temporary_root(outputs)

    def test_rejects_nondeterministic_compiler_output(self) -> None:
        outputs = [
            {"arduino-uno-r3.ino.hex": self.VALID_HEX},
            {"arduino-uno-r3.ino.hex": b":00000001FF\n"},
        ]

        with self.assertRaisesRegex(ValueError, "not reproducible"):
            self.compile_in_temporary_root(outputs)

    def test_rejects_an_intel_hex_record_with_a_bad_checksum(self) -> None:
        with self.assertRaisesRegex(ValueError, "checksum"):
            firmware.validate_intel_hex(b":0100000001FD\n:00000001FF\n")


class PullRequestPolicyTests(unittest.TestCase):
    def test_rejects_direct_generated_file_changes(self) -> None:
        for path in ["boards/arduino-uno-r3.hex", "boards/arduino-uno-r3.json"]:
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "generated"):
                firmware.validate_changed_paths([path], None, None)

    def test_rejects_a_direct_registry_board_change(self) -> None:
        base = {"apps": [], "boards": []}
        current = {"apps": [], "boards": [{"id": "arduino.uno-r3"}]}

        with self.assertRaisesRegex(ValueError, "registry.json boards"):
            firmware.validate_changed_paths(["registry.json"], base, current)

    def test_allows_app_registry_changes_when_boards_are_unchanged(self) -> None:
        boards = [{"id": "arduino.uno-r3"}]
        base = {"apps": [], "boards": copy.deepcopy(boards)}
        current = {"apps": [{"id": "pdf-viewer"}], "boards": copy.deepcopy(boards)}

        firmware.validate_changed_paths(["registry.json", "apps/pdf-viewer.json"], base, current)


class WorkflowContractTests(unittest.TestCase):
    def test_pip_cache_tracks_the_actual_dev_requirements_file(self) -> None:
        for name in ("validate.yml", "publish-firmware.yml"):
            workflow = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
            self.assertIn("cache: pip", workflow, name)
            self.assertIn("cache-dependency-path: requirements-dev.txt", workflow, name)


class PublishedSchemaTests(unittest.TestCase):
    def test_public_schema_accepts_the_compiled_firmware_contract(self) -> None:
        schema = json.loads((ROOT / "schemas" / "board.schema.json").read_text(encoding="utf-8"))
        artifact = firmware.FirmwareArtifact(
            path="boards/arduino-uno-r3.hex",
            data=b":00000001FF\n",
            source_sha256=SOURCE_HASH,
            arduino_cli="1.5.1",
            platform="arduino:avr@1.8.8",
        )
        manifest = firmware.render_manifest(board_source(), artifact)
        validator = jsonschema.Draft202012Validator(schema)

        errors = [error.message for error in validator.iter_errors(manifest)]

        self.assertEqual(errors, [])


class PublicationTests(unittest.TestCase):
    VALID_HEX = b":0100000001FE\n:00000001FF\n"

    def create_root(self, directory: str) -> Path:
        root = Path(directory)
        (root / "sources" / "boards").mkdir(parents=True)
        (root / "boards").mkdir()
        (root / ".github").mkdir()
        (root / "sources" / "boards" / "arduino-uno-r3.json").write_text(
            json.dumps(source_document(), ensure_ascii=False),
            encoding="utf-8",
        )
        (root / "boards" / "arduino-uno-r3.ino").write_text(
            "void setup() {}\nvoid loop() {}\n",
            encoding="utf-8",
        )
        (root / ".github" / "firmware-toolchain.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "arduinoCli": "1.5.1",
                    "platforms": {"arduino:avr": "1.8.8"},
                }
            ),
            encoding="utf-8",
        )
        (root / "registry.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "revision": 2,
                    "apps": [{"id": "pdf-viewer"}],
                    "boards": [],
                }
            ),
            encoding="utf-8",
        )
        return root

    def test_generation_writes_one_atomic_board_set_then_becomes_a_noop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.create_root(directory)
            compiles = 0

            def compiler(path: Path, source: firmware.BoardSource, cli: str) -> bytes:
                nonlocal compiles
                self.assertEqual(path, root)
                self.assertEqual(source.id, "arduino.uno-r3")
                self.assertEqual(cli, "arduino-cli")
                compiles += 1
                return self.VALID_HEX

            first_changes = firmware.generate(root, "arduino-cli", compiler=compiler)
            second_changes = firmware.generate(root, "arduino-cli", compiler=compiler)

            self.assertEqual(
                first_changes,
                [
                    "boards/arduino-uno-r3.hex",
                    "boards/arduino-uno-r3.json",
                    "registry.json",
                ],
            )
            self.assertEqual(second_changes, [])
            self.assertEqual(compiles, 2)
            self.assertEqual(
                (root / "boards" / "arduino-uno-r3.hex").read_bytes(),
                self.VALID_HEX,
            )
            manifest_bytes = (root / "boards" / "arduino-uno-r3.json").read_bytes()
            manifest = json.loads(manifest_bytes)
            registry = json.loads((root / "registry.json").read_bytes())
            self.assertEqual(manifest["firmware"]["format"], "intel-hex")
            self.assertEqual(registry["apps"], [{"id": "pdf-viewer"}])
            self.assertEqual(registry["revision"], 3)
            self.assertEqual(registry["boards"][0]["sha256"], firmware.sha256_bytes(manifest_bytes))

    def test_rejects_a_symlinked_source_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.create_root(directory)
            descriptor = root / "sources" / "boards" / "arduino-uno-r3.json"
            target = root / "descriptor-target.json"
            target.write_bytes(descriptor.read_bytes())
            descriptor.unlink()
            descriptor.symlink_to(target)

            with self.assertRaisesRegex(ValueError, "symbolic link"):
                firmware.load_sources(root)

    def test_rejects_a_symlinked_sketch_before_compilation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.create_root(directory)
            sketch = root / "boards" / "arduino-uno-r3.ino"
            target = root / "boards" / "other.ino"
            target.write_bytes(sketch.read_bytes())
            sketch.unlink()
            sketch.symlink_to(target)

            with self.assertRaisesRegex(ValueError, "symbolic link"):
                firmware.generate(root, "arduino-cli", compiler=lambda *_: self.VALID_HEX)

    def test_rejects_a_symlinked_board_image_before_hashing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.create_root(directory)
            descriptor = root / "sources" / "boards" / "arduino-uno-r3.json"
            document = json.loads(descriptor.read_text(encoding="utf-8"))
            document["image"] = {
                "path": "boards/arduino-uno-r3.png",
                "alt": "Arduino Uno R3 wiring",
            }
            descriptor.write_text(json.dumps(document), encoding="utf-8")
            target = root / "boards" / "other.png"
            target.write_bytes(b"not-a-real-image")
            (root / "boards" / "arduino-uno-r3.png").symlink_to(target)

            with self.assertRaisesRegex(ValueError, "symbolic link"):
                firmware.generate(root, "arduino-cli", compiler=lambda *_: self.VALID_HEX)

    def test_generation_failure_leaves_every_published_file_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.create_root(directory)
            old_manifest = b'{"legacy":true}\n'
            (root / "boards" / "arduino-uno-r3.json").write_bytes(old_manifest)
            old_registry = (root / "registry.json").read_bytes()

            def failed_compiler(path: Path, source: firmware.BoardSource, cli: str) -> bytes:
                raise ValueError("compile failed")

            with self.assertRaisesRegex(ValueError, "compile failed"):
                firmware.generate(root, "arduino-cli", compiler=failed_compiler)

            self.assertEqual(
                (root / "boards" / "arduino-uno-r3.json").read_bytes(),
                old_manifest,
            )
            self.assertEqual((root / "registry.json").read_bytes(), old_registry)
            self.assertFalse((root / "boards" / "arduino-uno-r3.hex").exists())

    def test_toolchain_rejects_an_unlocked_fqbn_platform(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.create_root(directory)
            document = source_document()
            document["sketch"]["fqbn"] = "vendor:other:board"
            (root / "sources" / "boards" / "arduino-uno-r3.json").write_text(
                json.dumps(document),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "not locked"):
                firmware.generate(root, "arduino-cli", compiler=lambda *_: self.VALID_HEX)

    def test_generation_removes_artifacts_for_a_deleted_board_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.create_root(directory)
            second = source_document()
            second["id"] = "arduino.other"
            second["name"] = "Arduino Other"
            second["sketch"]["path"] = "boards/arduino-other.ino"
            (root / "sources" / "boards" / "arduino-other.json").write_text(
                json.dumps(second),
                encoding="utf-8",
            )
            (root / "boards" / "arduino-other.ino").write_text(
                "void setup() {}\nvoid loop() {}\n",
                encoding="utf-8",
            )
            compiler = lambda *_: self.VALID_HEX
            firmware.generate(root, "arduino-cli", compiler=compiler)
            (root / "sources" / "boards" / "arduino-other.json").unlink()
            (root / "boards" / "arduino-other.ino").unlink()

            changes = firmware.generate(root, "arduino-cli", compiler=compiler)

            self.assertIn("boards/arduino-other.hex", changes)
            self.assertIn("boards/arduino-other.json", changes)
            self.assertFalse((root / "boards" / "arduino-other.hex").exists())
            self.assertFalse((root / "boards" / "arduino-other.json").exists())

    def test_verify_detects_a_tampered_published_hex(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.create_root(directory)
            compiler = lambda *_: self.VALID_HEX
            firmware.generate(root, "arduino-cli", compiler=compiler)
            (root / "boards" / "arduino-uno-r3.hex").write_bytes(b":00000001FF\n")

            with self.assertRaisesRegex(ValueError, "out of date"):
                firmware.verify(root, "arduino-cli", compiler=compiler)

    def test_validate_pr_compares_registry_boards_against_the_real_git_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.create_root(directory)

            def git(*arguments: str) -> None:
                subprocess.run(
                    ["git", "-c", "commit.gpgSign=false", *arguments],
                    cwd=root,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

            git("init")
            git("config", "user.name", "Hana Test")
            git("config", "user.email", "hana-test@example.invalid")
            git("add", ".")
            git("commit", "-m", "base")
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()

            registry = json.loads((root / "registry.json").read_text(encoding="utf-8"))
            registry["apps"] = [{"id": "music-app"}]
            (root / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
            git("add", "registry.json")
            git("commit", "-m", "change apps")

            # The trusted pull_request_target guard must inspect the requested
            # Git object, never an untrusted or dirty working tree checkout.
            app_head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip()
            registry["boards"] = [{"id": "working-tree-only-tamper"}]
            (root / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
            firmware.validate_pr(root, base, head=app_head)

            git("restore", "registry.json")
            firmware.validate_pr(root, base)

            registry["boards"] = [{"id": "arduino.uno-r3"}]
            (root / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
            git("add", "registry.json")
            git("commit", "-m", "change boards")

            with self.assertRaisesRegex(ValueError, "registry.json boards"):
                firmware.validate_pr(root, base)

    def test_validate_pr_rejects_renaming_a_generated_file_out_of_boards(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.create_root(directory)
            (root / "boards" / "arduino-uno-r3.json").write_text(
                json.dumps({"schemaVersion": 1}), encoding="utf-8"
            )

            def git(*arguments: str) -> None:
                subprocess.run(
                    ["git", "-c", "commit.gpgSign=false", *arguments],
                    cwd=root,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

            git("init")
            git("config", "user.name", "Hana Test")
            git("config", "user.email", "hana-test@example.invalid")
            git("add", ".")
            git("commit", "-m", "base")
            base = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip()

            (root / "archive").mkdir()
            git(
                "mv",
                "boards/arduino-uno-r3.json",
                "archive/arduino-uno-r3-manifest.txt",
            )
            git("commit", "-m", "rename generated manifest")

            with self.assertRaisesRegex(ValueError, "generated file"):
                firmware.validate_pr(root, base)


if __name__ == "__main__":
    unittest.main()
