import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from App.Infrastructure.Repositories import StoragePath
from App.Infrastructure.Repositories.ConfigRepository import ConfigRepository
from App.Infrastructure.Repositories.SessionRepository import SessionRepository
from App.Infrastructure.Repositories.StoragePath import (
    persistent_database_path,
)
from build_installer import (
    is_forbidden_database_file,
    validate_manual_installer_inputs,
)


class DatabaseStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_source_runtime_uses_isolated_development_storage(self):
        with (
            patch.dict(
                StoragePath.os.environ,
                {"LOCALAPPDATA": str(self.root)},
                clear=True,
            ),
            patch.object(StoragePath.sys, "frozen", False, create=True),
        ):
            result = persistent_database_path("SessionData.db")

        self.assertEqual(
            Path(result),
            self.root
            / "TNH Optima Development"
            / "Data"
            / "SessionData.db",
        )

    def test_frozen_runtime_uses_production_storage(self):
        with (
            patch.dict(
                StoragePath.os.environ,
                {"LOCALAPPDATA": str(self.root)},
                clear=True,
            ),
            patch.object(StoragePath.sys, "frozen", True, create=True),
        ):
            result = persistent_database_path("ConfigStorage.db")

        self.assertEqual(
            Path(result),
            self.root / "TNH Optima" / "Data" / "ConfigStorage.db",
        )

    def test_repository_schema_creation_is_lazy(self):
        config_path = self.root / "config" / "ConfigStorage.db"
        session_path = self.root / "session" / "SessionData.db"

        config_repository = ConfigRepository(str(config_path))
        session_repository = SessionRepository(str(session_path))

        self.assertFalse(config_path.exists())
        self.assertFalse(session_path.exists())

        self.assertIsNone(config_repository.load_camera_index())
        self.assertIsNone(session_repository.load_session("missing"))
        self.assertTrue(config_path.is_file())
        self.assertTrue(session_path.is_file())


class InstallerValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.application_dir = self.root / "dist" / "TNH Optima"
        self.application_dir.mkdir(parents=True)
        (self.application_dir / "TNH Optima.exe").touch()
        (self.root / "installer.iss").touch()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_clean_distribution_is_accepted(self):
        executable, installer = validate_manual_installer_inputs(self.root)

        self.assertEqual(executable, self.application_dir / "TNH Optima.exe")
        self.assertEqual(installer, self.root / "installer.iss")

    def test_distribution_with_runtime_database_is_rejected(self):
        persistence_dir = (
            self.application_dir
            / "_internal"
            / "App"
            / "Infrastructure"
            / "Persistence"
        )
        persistence_dir.mkdir(parents=True)
        (persistence_dir / "SessionData.db").touch()

        with self.assertRaisesRegex(
            RuntimeError,
            "Runtime databases must not be bundled",
        ):
            validate_manual_installer_inputs(self.root)

    def test_distribution_with_sqlite_sidecar_is_rejected(self):
        (self.application_dir / "ConfigStorage.db-wal").touch()

        with self.assertRaisesRegex(
            RuntimeError,
            "Runtime databases must not be bundled",
        ):
            validate_manual_installer_inputs(self.root)

    def test_database_name_matching_is_case_insensitive_and_scoped(self):
        forbidden_names = (
            "ConfigStorage.db",
            "configstorage.DB-wal",
            "SessionData.db-shm",
            "SESSIONDATA.DB-journal",
            "SessionData.db.backup",
        )
        for file_name in forbidden_names:
            with self.subTest(file_name=file_name):
                self.assertTrue(is_forbidden_database_file(file_name))

        self.assertFalse(is_forbidden_database_file("unrelated.db"))
        self.assertFalse(is_forbidden_database_file("SessionData.sqlite"))


class InstallerScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = (
            Path(__file__).resolve().parents[1] / "installer.iss"
        ).read_text(encoding="utf-8")

    def test_installer_excludes_runtime_databases_and_sidecars(self):
        self.assertIn("Excludes:", self.script)
        for pattern in (
            "ConfigStorage.db",
            "ConfigStorage.db-*",
            "SessionData.db",
            "SessionData.db-*",
        ):
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, self.script)

    def test_uninstaller_removes_production_runtime_databases(self):
        self.assertIn("[UninstallDelete]", self.script)
        for relative_path in (
            r"{localappdata}\{#MyAppName}\Data\ConfigStorage.db",
            r"{localappdata}\{#MyAppName}\Data\SessionData.db",
        ):
            with self.subTest(relative_path=relative_path):
                self.assertIn(relative_path, self.script)

        self.assertNotIn(
            r"{localappdata}\TNH Optima Development",
            self.script,
        )

    def test_clean_install_removes_state_left_by_legacy_uninstaller(self):
        self.assertIn("[InstallDelete]", self.script)
        self.assertIn(
            r'{localappdata}\{#MyAppName}\Data\SessionData.db"; '
            "Check: IsCleanInstall",
            self.script,
        )
        self.assertIn("function IsCleanInstall: Boolean;", self.script)
        self.assertIn("'unins000.exe'", self.script)


if __name__ == "__main__":
    unittest.main()
