from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import runtime_paths


class RuntimePathsTests(unittest.TestCase):
    def setUp(self) -> None:
        runtime_paths._models_dir_cache = None

    def tearDown(self) -> None:
        runtime_paths._models_dir_cache = None

    def test_frozen_models_dir_uses_local_app_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.dict(os.environ, {"LOCALAPPDATA": temp_dir}),
            ):
                actual = runtime_paths.models_dir()

            self.assertEqual(actual, Path(temp_dir) / "Peel" / "models")
            self.assertTrue(actual.is_dir())

    def test_development_models_dir_stays_in_project(self) -> None:
        with patch.object(runtime_paths, "is_frozen", return_value=False):
            actual = runtime_paths.models_dir()

        self.assertEqual(actual, runtime_paths.app_root() / "models")


if __name__ == "__main__":
    unittest.main()
