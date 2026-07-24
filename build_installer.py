"""Validate files required for manually compiling installer.iss."""

from __future__ import annotations

from pathlib import Path


APP_NAME = "TNH Optima"


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

    installer_script = project_path / "installer.iss"
    if not installer_script.is_file():
        raise FileNotFoundError(f"Installer script was not found at {installer_script}")

    print(f"PyInstaller application is ready: {application_executable}")
    print(f"Open this script in Inno Setup Compiler: {installer_script}")
    return application_executable, installer_script


if __name__ == "__main__":
    validate_manual_installer_inputs(Path(__file__).resolve().parent)
