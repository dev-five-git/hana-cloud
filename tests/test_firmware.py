from __future__ import annotations

import copy
import json
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


if __name__ == "__main__":
    unittest.main()
