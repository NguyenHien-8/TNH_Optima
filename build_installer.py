"""Validate files required for manually compiling installer.iss."""

from __future__ import annotations

from pathlib import Path


APP_NAME = "TNH Optima"
FORBIDDEN_DATABASE_NAMES = {
    "configstorage.db",
    "sessiondata.db",
}


def is_forbidden_database_file(path: str | Path) -> bool:
    """Return whether a path can contain persisted application data."""
    file_name = Path(path).name.casefold()
    return any(
        file_name == database_name
        or file_name.startswith(f"{database_name}-")
        or file_name.startswith(f"{database_name}.")
        for database_name in FORBIDDEN_DATABASE_NAMES
    )


def validate_manual_installer_inputs(
    project_dir: str | Path,
) -> tuple[Path, Path]:
    """Check that PyInstaller output and installer.iss are ready."""
    project_path = Path(project_dir).resolve()
    application_executable = (
        project_path / "dist" / APP_NAME / f"{APP_NAME}.exe"
    )
    if not application_executable.is_file():
        raise FileNotFoundError(
            "PyInstaller application executable was not found at "
            f"{application_executable}"
        )

    application_dir = application_executable.parent
    bundled_databases = sorted(
        path
        for path in application_dir.rglob("*")
        if (
            path.is_file()
            and is_forbidden_database_file(path)
        )
    )
    if bundled_databases:
        relative_paths = ", ".join(
            str(path.relative_to(project_path))
            for path in bundled_databases
        )
        raise RuntimeError(
            "Runtime databases must not be bundled in the installer: "
            f"{relative_paths}"
        )

    installer_script = project_path / "installer.iss"
    if not installer_script.is_file():
        raise FileNotFoundError(f"Installer script was not found at {installer_script}")

    print(f"PyInstaller application is ready: {application_executable}")
    print(f"Open this script in Inno Setup Compiler: {installer_script}")
    return application_executable, installer_script


if __name__ == "__main__":
    validate_manual_installer_inputs(Path(__file__).resolve().parent)
