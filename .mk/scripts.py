#!/usr/bin/env python
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

import ci_config
import release_artifacts
import winget
from inno import generate_inno_iss
from project_metadata import generate_project_module, read_project_table

PNG_SIZES = [16, 32, 48, 64, 128, 256, 512, 1024]
JPG_SIZES = [64, 128, 256, 512, 1024]
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
ICNS_SIZES = [16, 32, 64, 128, 256, 512, 1024]

ICNS_TYPES: dict[int, bytes] = {
    16: b"icp4",
    32: b"icp5",
    64: b"icp6",
    128: b"ic07",
    256: b"ic08",
    512: b"ic09",
    1024: b"ic10",
}


def _render_svg(svg_path: Path, size: int) -> bytes:
    import skia  # type: ignore[import-untyped]

    svg_bytes = svg_path.read_bytes()
    stream = skia.MemoryStream(svg_bytes)
    svg_dom = skia.SVGDOM.MakeFromStream(stream)
    if svg_dom is None:
        raise RuntimeError(f"Skia could not parse SVG: {svg_path}")

    surface = skia.Surface(size, size)
    with surface as canvas:
        canvas.clear(skia.ColorTRANSPARENT)
        svg_dom.setContainerSize(skia.Size.Make(size, size))
        svg_dom.render(canvas)

    image = surface.makeImageSnapshot()
    png_data = image.encodeToData()
    return bytes(png_data)


def _open_rgba(png_bytes: bytes):
    from PIL import Image  # type: ignore[import-untyped]

    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


def _resize(base_img, size: int):
    from PIL import Image  # type: ignore[import-untyped]

    return base_img.resize((size, size), Image.LANCZOS)


def _to_png_bytes(img) -> bytes:
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _build_icns(png_map: dict[int, bytes]) -> bytes:
    body = b""
    for size in sorted(png_map):
        ostype = ICNS_TYPES.get(size)
        if ostype is None:
            continue
        data = png_map[size]
        body += ostype + struct.pack(">I", 8 + len(data)) + data
    return b"icns" + struct.pack(">I", 8 + len(body)) + body


def convert_logo(svg_path: Path) -> int:
    if not svg_path.exists():
        print(f"ERROR: file not found: {svg_path}", file=sys.stderr)
        return 1
    if svg_path.suffix.lower() != ".svg":
        print(f"ERROR: expected a .svg file, got: {svg_path}", file=sys.stderr)
        return 1

    out_dir = svg_path.parent
    stem = svg_path.stem

    print(f"Source : {svg_path}")
    print(f"Output : {out_dir}/")
    print()

    max_size = max(PNG_SIZES + ICNS_SIZES)
    print(f"Rendering SVG at {max_size}x{max_size} px (skia-python) ...")
    base_img = _open_rgba(_render_svg(svg_path, max_size))
    print()

    from PIL import Image as pil_image  # type: ignore[import-untyped]

    print("PNG files:")
    for size in PNG_SIZES:
        img = _resize(base_img, size)
        out_path = out_dir / f"{stem}-{size}x{size}.png"
        img.save(out_path, format="PNG", optimize=True)
        print(f"  {out_path}")
    print()

    print("JPG files:")
    for size in JPG_SIZES:
        rgba = _resize(base_img, size)
        background = pil_image.new("RGB", (size, size), (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[3])
        out_path = out_dir / f"{stem}-{size}x{size}.jpg"
        background.save(out_path, format="JPEG", quality=95, optimize=True)
        print(f"  {out_path}")
    print()

    print("ICO file:")
    ico_path = out_dir / f"{stem}.ico"
    base_img.save(
        ico_path,
        format="ICO",
        sizes=[(size, size) for size in ICO_SIZES],
    )
    print(f"  {ico_path}")
    print()

    print("ICNS file:")
    icns_png_map = {size: _to_png_bytes(_resize(base_img, size)) for size in ICNS_SIZES}
    icns_path = out_dir / f"{stem}.icns"
    icns_path.write_bytes(_build_icns(icns_png_map))
    print(f"  {icns_path}")
    print()

    print("Done.")
    return 0


def generate_homebrew_formula(
    pyproject_path: Path,
    output_path: Path,
    version: str,
    formula_name: str,
    description: str,
    homepage: str,
    license_name: str,
    python_version: str,
    executable: str,
    resources_file: Path | None,
) -> int:
    try:
        project = read_project_table(pyproject_path)
        package_name = project.get("name")
        if not package_name:
            raise ValueError("pyproject.toml must define project.name.")
        if not license_name.strip():
            raise ValueError("Set CI_HOMEBREW_LICENSE to the project's SPDX license identifier.")
        if not homepage.startswith("https://"):
            raise ValueError("Set CI_HOMEBREW_HOMEPAGE to the project's HTTPS homepage.")
        resources = resources_file.read_text(encoding="utf-8").strip() if resources_file else ""

        api_url = "https://pypi.org/pypi/{}/{}/json".format(
            urllib.parse.quote(package_name, safe=""),
            urllib.parse.quote(version, safe=""),
        )
        request = urllib.request.Request(
            api_url,
            headers={"User-Agent": "python-ci-make-template-homebrew-formula/1"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            release = json.load(response)

        source_distributions = [item for item in release.get("urls", []) if item.get("packagetype") == "sdist" and item.get("filename", "").endswith(".tar.gz")]
        if len(source_distributions) != 1:
            raise ValueError(f"Expected one published .tar.gz sdist for {package_name} {version}; found {len(source_distributions)}.")
        source = source_distributions[0]
        checksum = source.get("digests", {}).get("sha256")
        if not checksum:
            raise ValueError("PyPI did not return a SHA-256 digest for the sdist.")

        class_name = re.sub(r"[^A-Za-z0-9]", "", formula_name.title())
        if not class_name or not class_name[0].isalpha():
            raise ValueError(f"Invalid Homebrew formula name: {formula_name!r}.")

        def ruby_string(value: str) -> str:
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            escaped = escaped.replace("\r", "\\r").replace("\n", "\\n")
            return f'"{escaped}"'

        if executable:
            test_lines = [
                "  test do",
                f'    system bin/{ruby_string(executable)}, "--version"',
                "  end",
            ]
        else:
            python_test = f"import importlib.metadata; assert importlib.metadata.version({package_name!r}) == {version!r}"
            test_lines = [
                "  test do",
                f'    system libexec/"bin/python", "-c", {ruby_string(python_test)}',
                "  end",
            ]

        lines = [
            f"class {class_name} < Formula",
            "  include Language::Python::Virtualenv",
            "",
            f"  desc {ruby_string(description)}",
            f"  homepage {ruby_string(homepage)}",
            f"  url {ruby_string(source['url'])}",
            f"  sha256 {ruby_string(checksum)}",
            f"  license {ruby_string(license_name)}",
            f"  pypi_packages package_name: {ruby_string(package_name)}",
            "",
            f"  depends_on {ruby_string(f'python@{python_version}')}",
            "",
            *([*resources.splitlines(), ""] if resources else []),
            "  def install",
            "    virtualenv_install_with_resources",
            "  end",
            "",
            *test_lines,
            "end",
        ]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Generated {output_path} for {package_name} {version} with PyPI SHA-256.")
        return 0
    except Exception as error:
        print(f"Homebrew formula generation failed: {error}", file=sys.stderr)
        return 1


def smoke_install_artifacts(dist_dir: Path, import_name: str) -> int:
    artifacts = sorted([*dist_dir.glob("*.whl"), *dist_dir.glob("*.tar.gz")])
    if not artifacts:
        print(f"No wheel or sdist found in {dist_dir}.", file=sys.stderr)
        return 1

    uv_path = shutil.which("uv")
    if uv_path is None:
        print("uv is required to smoke-test built distributions.", file=sys.stderr)
        return 1

    for artifact in artifacts:
        print(f"[ci-smoke-build] Installing {artifact.name} in an isolated environment")
        environment = os.environ.copy()
        for key in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "UV_RUN_RECURSION_DEPTH"):
            environment.pop(key, None)

        with tempfile.TemporaryDirectory(prefix="python-package-smoke-") as temp_dir:
            command = [
                uv_path,
                "run",
                "--isolated",
                "--no-project",
                "--with",
                str(artifact.resolve()),
                "python",
                "-c",
                f"import importlib; importlib.import_module({import_name!r})",
            ]
            result = subprocess.run(command, cwd=temp_dir, env=environment, check=False)
            if result.returncode != 0:
                print(f"Smoke test failed for {artifact.name}.", file=sys.stderr)
                return result.returncode

    print(f"[ci-smoke-build] Installed and imported {len(artifacts)} distributions successfully.")
    return 0


def make_settings() -> dict[str, str]:
    prefix = "TEMPLATE_SETTING_"
    return {key.removeprefix(prefix): value for key, value in os.environ.items() if key.startswith(prefix)}


def run_release_artifacts(expected_paths: list[Path], stage: bool) -> int:
    try:
        files = release_artifacts.verify(make_settings()["RELEASE_ARTIFACTS"], expected_paths)
        if stage:
            release_artifacts.stage(files, os.getenv("GITHUB_OUTPUT", ""))
    except (KeyError, OSError, ValueError) as error:
        print(f"[ci-verify-release-artifacts] Error: {error}", file=sys.stderr)
        return 1
    return 0


def print_project_version(path: Path) -> int:
    try:
        print(read_project_table(path).get("version", "latest"))
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Utility entrypoint for template helper scripts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    gen_project_py_parser = subparsers.add_parser(
        "gen-project-module",
        help="Generate a Python module from pyproject.toml metadata.",
    )
    gen_project_py_parser.add_argument("pyproject_toml", type=Path)
    gen_project_py_parser.add_argument("output_py", type=Path)
    gen_project_py_parser.set_defaults(handler=lambda args: generate_project_module(args.pyproject_toml, args.output_py))

    version_parser = subparsers.add_parser("project-version", help="Print the project version.")
    version_parser.add_argument("pyproject_toml", type=Path)
    version_parser.set_defaults(handler=lambda args: print_project_version(args.pyproject_toml))

    gen_inno_iss_parser = subparsers.add_parser(
        "gen-inno-iss",
        help="Generate an Inno Setup script from Makefile metadata.",
    )
    gen_inno_iss_parser.add_argument("output_iss", type=Path)
    gen_inno_iss_parser.add_argument("version_define")
    gen_inno_iss_parser.add_argument("app_name")
    gen_inno_iss_parser.add_argument("app_publisher")
    gen_inno_iss_parser.add_argument("app_icon")
    gen_inno_iss_parser.add_argument("app_exe")
    gen_inno_iss_parser.add_argument("default_dir_name")
    gen_inno_iss_parser.add_argument("default_group_name")
    gen_inno_iss_parser.add_argument("output_dir")
    gen_inno_iss_parser.add_argument("output_base_filename")
    gen_inno_iss_parser.add_argument("compression")
    gen_inno_iss_parser.add_argument("solid_compression")
    gen_inno_iss_parser.add_argument("app_version")
    gen_inno_iss_parser.set_defaults(
        handler=lambda args: generate_inno_iss(
            args.output_iss,
            args.version_define,
            args.app_name,
            args.app_publisher,
            args.app_icon,
            args.app_exe,
            args.default_dir_name,
            args.default_group_name,
            args.output_dir,
            args.output_base_filename,
            args.compression,
            args.solid_compression,
            args.app_version,
        )
    )

    convert_logo_parser = subparsers.add_parser(
        "convert-logo",
        help="Convert an SVG logo into PNG, JPG, ICO, and ICNS assets.",
    )
    convert_logo_parser.add_argument("svg_path", type=Path)
    convert_logo_parser.set_defaults(handler=lambda args: convert_logo(args.svg_path))

    validate_ci_parser = subparsers.add_parser(
        "validate-ci-config",
        help="Validate the CI Python version, OS matrix, and publication dependencies.",
    )
    for argument in ci_config.LEGACY_VALIDATION_ARGS:
        validate_ci_parser.add_argument(argument)
    validate_ci_parser.set_defaults(
        handler=lambda args: ci_config.run(
            "validate",
            {key: getattr(args, argument) for argument, key in ci_config.LEGACY_VALIDATION_ARGS.items()},
        )
    )

    config_parser = subparsers.add_parser("ci-config", help="Read effective CI settings exported by Make.")
    config_parser.add_argument("action", choices=("log", "validate", "export"))
    config_parser.set_defaults(handler=lambda args: ci_config.run(args.action, make_settings(), os.getenv("GITHUB_OUTPUT", "")))

    artifacts_parser = subparsers.add_parser(
        "release-artifacts",
        help="Verify native release files and optionally stage them for upload.",
    )
    artifacts_parser.add_argument("expected", nargs="*", type=Path)
    artifacts_parser.add_argument("--stage", action="store_true")
    artifacts_parser.set_defaults(handler=lambda args: run_release_artifacts(args.expected, args.stage))

    homebrew_parser = subparsers.add_parser(
        "gen-homebrew-formula",
        help="Generate a Homebrew formula with the published PyPI sdist URL and SHA-256.",
    )
    homebrew_parser.add_argument("pyproject_toml", type=Path)
    homebrew_parser.add_argument("output_rb", type=Path)
    homebrew_parser.add_argument("version")
    homebrew_parser.add_argument("formula_name")
    homebrew_parser.add_argument("description")
    homebrew_parser.add_argument("homepage")
    homebrew_parser.add_argument("license")
    homebrew_parser.add_argument("python_version")
    homebrew_parser.add_argument("executable", nargs="?", default="")
    homebrew_parser.add_argument("--resources-file", type=Path, default=None)
    homebrew_parser.set_defaults(
        handler=lambda args: generate_homebrew_formula(
            args.pyproject_toml,
            args.output_rb,
            args.version,
            args.formula_name,
            args.description,
            args.homepage,
            args.license,
            args.python_version,
            args.executable,
            args.resources_file,
        )
    )

    winget_parser = subparsers.add_parser("gen-winget-manifests", help="Generate manifests for the verified WinGet installer.")
    winget_parser.add_argument("version")
    winget_parser.set_defaults(handler=lambda args: winget.generate_manifests(args.version, make_settings()))

    winget_path_parser = subparsers.add_parser("winget-manifest-path", help="Print the local or repository-relative WinGet manifest path.")
    winget_path_parser.add_argument("identifier")
    winget_path_parser.add_argument("version")
    winget_path_parser.add_argument("--local", action="store_true")
    winget_path_parser.set_defaults(handler=lambda args: winget.print_manifest_path(args.identifier, args.version, args.local))

    smoke_parser = subparsers.add_parser(
        "smoke-install-artifacts",
        help="Install built wheel and sdist files in isolated environments and import a package.",
    )
    smoke_parser.add_argument("dist_dir", type=Path)
    smoke_parser.add_argument("import_name")
    smoke_parser.set_defaults(handler=lambda args: smoke_install_artifacts(args.dist_dir, args.import_name))

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
