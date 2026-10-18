import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sa_agent.config import default_config_path, load_config, validate_config
from sa_agent.provenance import file_hash, fingerprint, make_manifest

ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def config(self):
        return load_config(ROOT / "configs/benchmark.json")

    def test_local_settings_take_precedence_without_merging_or_mutating_defaults(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "configs").mkdir()
            base, local = root / "configs/benchmark.json", root / "configs/benchmark.local.json"
            base.write_text(json.dumps(self.config()), encoding="utf-8")
            self.assertEqual(base, default_config_path(root))
            override = self.config()
            override["agent"]["proxy"] = "socks5h://127.0.0.1:10808"
            local.write_text(json.dumps(override), encoding="utf-8")
            self.assertEqual(local, default_config_path(root))
            self.assertEqual(override, load_config(default_config_path(root)))
            self.assertIsNone(load_config(base)["agent"]["proxy"])

    def test_rejects_nonfinite_timing_mismatched_video_and_inline_keys(self):
        mutations = [("agent", "request_timeout_seconds", float("nan")),
            ("game", "startup_countdown_seconds", -1),
            ("recording", "width", 640), ("recording", "post_success_seconds", 121),
            ("recording", "post_success_second", 15),
            ("agent", "api_key_env", "not-an-env-name"),
            ("agent", "api_key", "test-not-a-real-credential")]
        for section, key, value in mutations:
            config = self.config()
            config[section][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_config(config)

    def test_fingerprints_ignore_object_key_order_but_detect_rule_changes(self):
        self.assertEqual(fingerprint({"a": 1, "b": 2}), fingerprint({"b": 2, "a": 1}))
        self.assertNotEqual(fingerprint({"hold_seconds": 2}), fingerprint({"hold_seconds": 3}))

    def test_manifest_hashes_task_without_machine_specific_source_path(self):
        task = {"id": "test", "version": 1, "source_file": "local/path.json"}
        manifest = make_manifest(task, self.config(), "primitive_actions")
        changed = copy.deepcopy(task)
        changed["source_file"] = "other/path.json"
        other = make_manifest(changed, self.config(), "primitive_actions")
        self.assertEqual(manifest["task"]["sha256"], other["task"]["sha256"])
        self.assertFalse(manifest["scenario_deterministic"])
        self.assertNotIn("api_key", manifest)

    def test_unavailable_optional_binary_hash_does_not_abort_a_run(self):
        with patch.object(Path, "is_file", return_value=True), \
             patch.object(Path, "open", side_effect=PermissionError("in use")):
            self.assertIsNone(file_hash("game.exe"))
