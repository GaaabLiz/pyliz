"""Read, validate, and export the project settings supplied by Make."""

import json
import re
import shlex
import sys
from collections.abc import Mapping
from pathlib import Path

from project_metadata import read_project_table
from release_artifacts import is_selected, parse_patterns

LEGACY_VALIDATION_ARGS = {
    "python_version": "CI_PYTHON_VERSION",
    "test_os_json": "CI_TEST_OS_MATRIX",
    "enable_pypi_publish": "CI_ENABLE_PYPI_PUBLISH",
    "enable_homebrew_publish": "CI_ENABLE_HOMEBREW_PUBLISH",
    "enable_dockerhub_publish": "CI_ENABLE_DOCKERHUB_PUBLISH",
    "dockerhub_image": "CI_DOCKERHUB_IMAGE",
    "enable_chocolatey_publish": "CI_ENABLE_CHOCOLATEY_PUBLISH",
    "enable_winget_publish": "CI_ENABLE_WINGET_PUBLISH",
    "enable_release_docs": "CI_ENABLE_RELEASE_DOCS",
    "build_linux": "CI_BUILD_LINUX",
    "build_macos": "CI_BUILD_MACOS",
    "build_windows": "CI_BUILD_WINDOWS",
    "enable_windows_installer": "ENABLE_WINDOWS_INSTALLER",
    "apps_list": "APPS_LIST",
    "release_artifacts": "RELEASE_ARTIFACTS",
    "installer_path": "CI_CONFIG_INSTALLER_PATH",
    "docker_push_latest": "CI_DOCKER_PUSH_LATEST",
    "homebrew_license": "CI_HOMEBREW_LICENSE",
    "winget_license": "CI_WINGET_LICENSE",
    "winget_license_url": "CI_WINGET_LICENSE_URL",
    "homebrew_homepage": "CI_HOMEBREW_HOMEPAGE",
    "homebrew_tap_repo": "CI_HOMEBREW_TAP_REPO",
    "chocolatey_project_url": "CI_CHOCOLATEY_PROJECT_URL",
    "chocolatey_license_url": "CI_CHOCOLATEY_LICENSE_URL",
    "chocolatey_installer_url": "CI_CHOCOLATEY_INSTALLER_URL",
    "winget_homepage": "CI_WINGET_HOMEPAGE",
    "winget_installer_url": "CI_WINGET_INSTALLER_URL",
    "winget_installer_file": "CI_WINGET_INSTALLER_FILE",
    "winget_fork_repo": "CI_WINGET_FORK_REPO",
    "winget_package_identifier": "CI_WINGET_PACKAGE_IDENTIFIER",
    "pyproject_path": "FILE_PROJECT_TOML",
    "homebrew_resources_file": "CI_HOMEBREW_RESOURCES_FILE",
    "pyinstaller_windowed": "PYINSTALLER_WINDOWED",
}

TOGGLES = (
    "CI_ENABLE_PYPI_PUBLISH",
    "CI_ENABLE_HOMEBREW_PUBLISH",
    "CI_ENABLE_DOCKERHUB_PUBLISH",
    "CI_ENABLE_CHOCOLATEY_PUBLISH",
    "CI_ENABLE_WINGET_PUBLISH",
    "CI_ENABLE_RELEASE_DOCS",
    "CI_BUILD_LINUX",
    "CI_BUILD_MACOS",
    "CI_BUILD_WINDOWS",
    "ENABLE_WINDOWS_INSTALLER",
    "CI_DOCKER_PUSH_LATEST",
    "PYINSTALLER_WINDOWED",
)

LOG_SETTINGS = (
    "PYTHON_MAIN_PACKAGE",
    "TESTS_PATH",
    "CI_PYTHON_VERSION",
    "CI_TEST_OS_MATRIX",
    "CI_UV_VERSION",
    "CI_QUALITY_TARGETS",
    "CI_TEST_COMMAND",
    "CI_DOCKER_ENTRYPOINT",
    "APPS_LIST",
    "ENABLE_WINDOWS_INSTALLER",
    "RELEASE_ARTIFACTS",
    "CI_ENABLE_WINGET_PUBLISH",
    "CI_WINGET_PACKAGE_IDENTIFIER",
)

OUTPUT_SETTINGS = {
    "python_version": "CI_PYTHON_VERSION",
    "test_os_matrix": "CI_TEST_OS_MATRIX",
    "uv_version": "CI_UV_VERSION",
    "build_linux": "CI_BUILD_LINUX",
    "build_macos": "CI_BUILD_MACOS",
    "build_windows": "CI_BUILD_WINDOWS",
    "enable_pypi_publish": "CI_ENABLE_PYPI_PUBLISH",
    "pypi_environment": "CI_PYPI_ENVIRONMENT",
    "enable_dockerhub_publish": "CI_ENABLE_DOCKERHUB_PUBLISH",
    "dockerhub_environment": "CI_DOCKERHUB_ENVIRONMENT",
    "enable_chocolatey_publish": "CI_ENABLE_CHOCOLATEY_PUBLISH",
    "chocolatey_environment": "CI_CHOCOLATEY_ENVIRONMENT",
    "enable_homebrew_publish": "CI_ENABLE_HOMEBREW_PUBLISH",
    "homebrew_environment": "CI_HOMEBREW_ENVIRONMENT",
    "enable_winget_publish": "CI_ENABLE_WINGET_PUBLISH",
    "winget_environment": "CI_WINGET_ENVIRONMENT",
    "enable_release_docs": "CI_ENABLE_RELEASE_DOCS",
    "release_notes_file": "CI_RELEASE_NOTES_FILE",
    "release_notes_filename": "CI_CONFIG_RELEASE_NOTES_FILENAME",
}


def validate(settings: Mapping[str, str]) -> None:
    enable_homebrew_publish = settings["CI_ENABLE_HOMEBREW_PUBLISH"]
    dockerhub_image = settings["CI_DOCKERHUB_IMAGE"]
    build_windows = settings["CI_BUILD_WINDOWS"]
    enable_windows_installer = settings["ENABLE_WINDOWS_INSTALLER"]
    installer_path = settings["CI_CONFIG_INSTALLER_PATH"]
    winget_license_url = settings["CI_WINGET_LICENSE_URL"]
    homebrew_homepage = settings["CI_HOMEBREW_HOMEPAGE"]
    homebrew_tap_repo = settings["CI_HOMEBREW_TAP_REPO"]
    chocolatey_installer_url = settings["CI_CHOCOLATEY_INSTALLER_URL"]
    winget_installer_url = settings["CI_WINGET_INSTALLER_URL"]
    winget_fork_repo = settings["CI_WINGET_FORK_REPO"]

    if not re.fullmatch(r"\d+\.\d+", settings["CI_PYTHON_VERSION"]):
        raise ValueError("CI_PYTHON_VERSION must be one fixed major.minor version, such as 3.14.")

    test_os = json.loads(settings["CI_TEST_OS_MATRIX"])
    if not isinstance(test_os, list) or not test_os:
        raise ValueError("CI_TEST_OS_MATRIX must be a non-empty JSON array.")
    if any(not isinstance(item, str) or not item.strip() for item in test_os):
        raise ValueError("CI_TEST_OS_MATRIX must contain only non-empty strings.")
    if len(set(test_os)) != len(test_os):
        raise ValueError("CI_TEST_OS_MATRIX contains duplicate values.")

    for label in TOGGLES:
        value = settings[label]
        if value not in {"0", "1"}:
            raise ValueError(f"{label} must be 0 or 1.")

    if enable_homebrew_publish == "1" and settings["CI_ENABLE_PYPI_PUBLISH"] != "1":
        raise ValueError("Homebrew publication requires PyPI publication to be enabled.")

    apps = shlex.split(settings["APPS_LIST"])
    if len(set(apps)) != len(apps):
        raise ValueError("APPS_LIST contains duplicate application identifiers.")
    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", app) for app in apps):
        raise ValueError("APPS_LIST identifiers must contain only letters, numbers, and underscores.")

    native_build_enabled = any(value == "1" for value in (settings["CI_BUILD_LINUX"], settings["CI_BUILD_MACOS"], build_windows))
    if native_build_enabled and not apps:
        raise ValueError("CI_BUILD_* requires at least one app in APPS_LIST.")
    artifact_patterns = parse_patterns(settings["RELEASE_ARTIFACTS"]) if native_build_enabled else []

    if enable_windows_installer == "1" and not apps:
        raise ValueError("ENABLE_WINDOWS_INSTALLER requires at least one app in APPS_LIST.")

    if enable_windows_installer == "1" and build_windows != "1":
        raise ValueError("ENABLE_WINDOWS_INSTALLER requires CI_BUILD_WINDOWS=1.")

    if enable_windows_installer == "1" and not is_selected(installer_path, artifact_patterns, ignore_case=True):
        raise ValueError(f"RELEASE_ARTIFACTS must include the configured Inno Setup installer ({installer_path}) when ENABLE_WINDOWS_INSTALLER=1.")

    installer_publishers = settings["CI_ENABLE_CHOCOLATEY_PUBLISH"] == "1" or settings["CI_ENABLE_WINGET_PUBLISH"] == "1"
    if installer_publishers:
        if build_windows != "1" or enable_windows_installer != "1":
            raise ValueError("Chocolatey and WinGet publication require CI_BUILD_WINDOWS=1 and ENABLE_WINDOWS_INSTALLER=1.")
    if enable_homebrew_publish == "1" and not settings["CI_HOMEBREW_LICENSE"].strip():
        raise ValueError("CI_HOMEBREW_LICENSE must be configured before enabling Homebrew publication.")
    if enable_homebrew_publish == "1":
        lower_homepage = homebrew_homepage.lower()
        if not homebrew_homepage.startswith("https://") or any(placeholder in lower_homepage for placeholder in ("your-org", "your-repo", "example.com")):
            raise ValueError("CI_HOMEBREW_HOMEPAGE must be set to the project's real HTTPS homepage.")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/homebrew-[A-Za-z0-9_.-]+", homebrew_tap_repo):
            raise ValueError("CI_HOMEBREW_TAP_REPO must use the owner/homebrew-<tap> format.")
        if "your-org" in homebrew_tap_repo.lower():
            raise ValueError("CI_HOMEBREW_TAP_REPO must name the project's real Homebrew tap.")
        project_metadata = read_project_table(Path(settings["FILE_PROJECT_TOML"]))
        resource_path = Path(settings["CI_HOMEBREW_RESOURCES_FILE"])
        resource_text = resource_path.read_text(encoding="utf-8") if resource_path.is_file() else ""
        if project_metadata.get("dependencies") and 'resource "' not in resource_text:
            raise ValueError(
                "Homebrew publication needs a resource file for the project's runtime "
                "dependencies. Set CI_HOMEBREW_RESOURCES_FILE and include all pinned direct "
                "and transitive resource "
                "blocks with SHA-256 values."
            )

    def require_project_url(label: str, value: str) -> None:
        lower_value = value.lower()
        if not value.startswith("https://") or any(placeholder in lower_value for placeholder in ("your-org", "your-repo", "example.com")):
            raise ValueError(f"{label} must be set to the project's real HTTPS URL.")

    if settings["CI_ENABLE_CHOCOLATEY_PUBLISH"] == "1":
        require_project_url("CI_CHOCOLATEY_PROJECT_URL", settings["CI_CHOCOLATEY_PROJECT_URL"])
        require_project_url("CI_CHOCOLATEY_LICENSE_URL", settings["CI_CHOCOLATEY_LICENSE_URL"])
        require_project_url("CI_CHOCOLATEY_INSTALLER_URL", chocolatey_installer_url)
        if "{version}" not in chocolatey_installer_url:
            raise ValueError("CI_CHOCOLATEY_INSTALLER_URL must contain the {version} placeholder.")

    if settings["CI_ENABLE_WINGET_PUBLISH"] == "1":
        if not settings["CI_WINGET_LICENSE"].strip():
            raise ValueError("CI_WINGET_LICENSE must be configured before enabling WinGet publication.")
        if not winget_license_url.startswith("https://"):
            raise ValueError("CI_WINGET_LICENSE_URL must be an HTTPS URL before enabling WinGet.")
        require_project_url("CI_WINGET_LICENSE_URL", winget_license_url)
        require_project_url("CI_WINGET_HOMEPAGE", settings["CI_WINGET_HOMEPAGE"])
        require_project_url("CI_WINGET_INSTALLER_URL", winget_installer_url)
        if "{version}" not in winget_installer_url:
            raise ValueError("CI_WINGET_INSTALLER_URL must contain the {version} placeholder.")
        if settings["CI_WINGET_INSTALLER_FILE"] != installer_path:
            raise ValueError(f"CI_WINGET_INSTALLER_FILE must match the Inno Setup output path ({installer_path}) so its checksum matches the published installer.")
        if "your-github-user" in winget_fork_repo or len(winget_fork_repo.split("/")) != 2:
            raise ValueError("CI_WINGET_FORK_REPO must point to your GitHub winget-pkgs fork.")
        publisher, separator, package = settings["CI_WINGET_PACKAGE_IDENTIFIER"].partition(".")
        if not separator or not publisher or not package or publisher == "YourCompany":
            raise ValueError("CI_WINGET_PACKAGE_IDENTIFIER must be your unique Publisher.Package identifier.")

    if settings["CI_ENABLE_DOCKERHUB_PUBLISH"] == "1" and ("/" not in dockerhub_image or "your-dockerhub-user" in dockerhub_image):
        raise ValueError("CI_DOCKERHUB_IMAGE must be configured before enabling Docker Hub publication.")


def log(settings: Mapping[str, str]) -> None:
    prefix = "[ci-log-config]"
    print(f"{prefix} Project configuration summary")
    for key in LOG_SETTINGS:
        value = settings[key]
        if key == "APPS_LIST" and not value.strip():
            value = "<empty>"
        print(f"{prefix} {key}={value}")
    print(f"{prefix} Hint: leave APPS_LIST empty and CI_BUILD_* at 0 for package-only releases.")
    print(f"{prefix} Hint: RELEASE_ARTIFACTS covers optional platform assets; package distributions are uploaded by CI.")


def export(settings: Mapping[str, str], output: str) -> None:
    if not output:
        raise ValueError("GITHUB_OUTPUT is not set.")
    contents = "".join(f"{name}={settings[key]}\n" for name, key in OUTPUT_SETTINGS.items())
    with Path(output).open("a", encoding="utf-8", newline="\n") as file_handle:
        file_handle.write(contents)
    print(f"[ci-export-config] Exporting CI configuration to {output}")


def run(action: str, settings: Mapping[str, str], output: str = "") -> int:
    try:
        if action == "export":
            export(settings, output)
        elif action == "log":
            log(settings)
        else:
            validate(settings)
    except (OSError, ValueError, KeyError) as error:
        print(f"CI configuration error: {error}", file=sys.stderr)
        return 1
    return 0
