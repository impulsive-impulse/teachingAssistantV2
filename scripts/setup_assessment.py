"""Create the pinned assessment environment and acquire its required inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
LOCK = Path("requirements") / "assessment-windows-py312-cpu.lock"
EXTRAS = "assessment,app,online-generation,dev"
OWNERSHIP_MARKER = ".assessment-environment.json"
MAX_SETUP_PATH_LENGTH = 60


def clean_environment() -> dict[str, str]:
    """Keep normal transport settings, but not user Python/package configuration."""
    environment = {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith(("PIP_", "NPM_CONFIG_"))
        and key.upper() not in {
            "PYTHONPATH", "PYTHONHOME", "OPENAI_API_KEY", "AZURE_OPENAI_API_KEY",
            "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN",
        }
    }
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PIP_CONFIG_FILE"] = os.devnull
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    environment["PIP_EXTRA_INDEX_URL"] = ""
    return environment


def require_supported_python() -> None:
    if sys.version_info[:2] != (3, 12) or sysconfig.get_platform() != "win-amd64":
        raise RuntimeError(
            "The locked profile requires x64 CPython 3.12 on Windows. "
            "On Windows ARM64, run an x64 Python, not the native ARM64 interpreter. "
            "No repository-local temp runtime is discovered or substituted automatically."
        )


def validate_index(index: str) -> None:
    parsed = urlparse(index)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query:
        raise ValueError("Package index must be an HTTPS URL without credentials or query tokens.")


def validate_setup_paths(root: Path, directory: Path) -> None:
    # Pinned Torch license paths must fit Windows' default MAX_PATH.
    for label, path in (("checkout", root), ("virtual environment", directory)):
        if len(str(path)) > MAX_SETUP_PATH_LENGTH:
            raise RuntimeError(
                f"The {label} path is too long for this Windows profile "
                f"(maximum {MAX_SETUP_PATH_LENGTH} characters): {path}. "
                "Use a shorter checkout and/or --venv path. "
                "Git core.longpaths does not enable long paths for Python packages."
            )


def run(command: list[str], *, root: Path, environment: dict[str, str]) -> None:
    subprocess.run(command, cwd=root, env=environment, check=True)


def create_environment(root: Path, directory: Path, environment: dict[str, str]) -> Path:
    marker = directory / OWNERSHIP_MARKER
    if directory.exists():
        if not marker.is_file() or not (directory / "pyvenv.cfg").is_file():
            raise RuntimeError(
                f"Refusing to modify an existing unowned environment: {directory}. "
                "Choose a new --venv directory."
            )
        owned = json.loads(marker.read_text(encoding="utf-8"))
        if owned.get("profile") != "assessment-windows-py312-cpu" or owned.get("project_root") != str(root):
            raise RuntimeError("The existing environment belongs to a different profile or project.")
    else:
        run([sys.executable, "-I", "-m", "venv", str(directory)], root=root, environment=environment)
        marker.write_text(json.dumps({"profile": "assessment-windows-py312-cpu", "project_root": str(root), "state": "created"}) + "\n",
                          encoding="utf-8", newline="\n")
    python = directory / "Scripts" / "python.exe"
    if not python.is_file():
        raise RuntimeError("The assessment virtual environment is incomplete.")
    inspection = subprocess.run(
        [str(python), "-I", "-c",
         "import json,sys,sysconfig; print(json.dumps({'version':list(sys.version_info[:2]),"
         "'platform':sysconfig.get_platform(),'isolated':sys.prefix!=sys.base_prefix}))"],
        cwd=root, env=environment, check=True, capture_output=True, text=True,
    )
    details = json.loads(inspection.stdout)
    if details != {"version": [3, 12], "platform": "win-amd64", "isolated": True}:
        raise RuntimeError("The virtual environment does not match the locked Python profile.")
    config = (directory / "pyvenv.cfg").read_text(encoding="utf-8")
    if "include-system-site-packages = false" not in config:
        raise RuntimeError("The assessment environment must not reuse system site-packages.")
    return python


def offline_requirements(lock: Path, wheelhouse: Path, directory: Path) -> Path:
    """Resolve pinned direct wheel URLs locally without changing their hashes."""
    import re
    from urllib.parse import unquote

    lines = []
    for line in lock.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+) @ (https://\S+)(.*)$", line)
        if match:
            wheel = wheelhouse / unquote(Path(urlparse(match[2]).path).name)
            if not wheel.is_file():
                raise FileNotFoundError(f"Pinned direct-URL wheel is missing from wheelhouse: {wheel.name}")
            line = f"{match[1]} @ {wheel.resolve().as_uri()}{match[3]}"
        lines.append(line)
    result = directory / "offline-requirements.lock"
    result.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--venv", type=Path, default=Path(".venv-assessment"))
    parser.add_argument("--wheelhouse", type=Path, help="Install hash-matching wheels offline instead of using an index.")
    parser.add_argument("--index-url", default="https://pypi.org/simple", help="Optional explicit HTTPS mirror; hashes still required.")
    parser.add_argument("--frontend", action="store_true", help="Run npm ci and build in frontend; replaces its node_modules.")
    parser.add_argument("--npm-cache", type=Path, help="Optional dedicated npm cache, never the user's default cache.")
    parser.add_argument("--npm-offline", action="store_true", help="Require a prefilled dedicated cache for frontend installation.")
    parser.add_argument("--demo-books-dir", type=Path)
    parser.add_argument("--authorized-demo-use", action="store_true")
    args = parser.parse_args(argv)
    require_supported_python()
    validate_index(args.index_url)
    root = args.root.resolve()
    lock = root / LOCK
    if not (root / "pyproject.toml").is_file() or not lock.is_file():
        raise FileNotFoundError("The project manifest and pinned CPU dependency lock are required.")
    if args.authorized_demo_use != (args.demo_books_dir is not None):
        raise ValueError("--demo-books-dir and --authorized-demo-use must be supplied together.")
    if args.npm_offline and (not args.frontend or args.npm_cache is None):
        raise ValueError("--npm-offline requires --frontend and an explicit --npm-cache.")
    directory = args.venv.resolve() if args.venv.is_absolute() else (root / args.venv).resolve()
    if directory == root or root in directory.parents and directory == root / "src":
        raise ValueError("The environment directory must not replace the project or source directory.")
    validate_setup_paths(root, directory)
    environment = clean_environment()
    python = create_environment(root, directory, environment)
    install_lock = lock
    if args.wheelhouse is not None:
        if not args.wheelhouse.is_dir():
            raise FileNotFoundError("The explicit wheelhouse directory is missing.")
        install_lock = offline_requirements(lock, args.wheelhouse.resolve(), directory)
    command = [
        str(python), "-m", "pip", "install", "--require-hashes", "--only-binary=:all:",
        "--no-cache-dir", "--progress-bar", "off", "-r", str(install_lock),
    ]
    if args.wheelhouse is not None:
        command += ["--no-index", "--find-links", str(args.wheelhouse.resolve())]
    else:
        command += ["--index-url", args.index_url]
    run(command, root=root, environment=environment)
    run([
        str(python), "-m", "pip", "install", "--no-index", "--no-deps",
        "--no-build-isolation", "--editable", f"{root}[{EXTRAS}]",
    ], root=root, environment=environment)
    run([str(python), "-m", "pip", "check"], root=root, environment=environment)
    preparation = [str(python), str(root / "scripts" / "prepare_assessment_assets.py"),
                   "--root", str(root), "--smoke"]
    if args.demo_books_dir is not None:
        preparation += ["--demo-books-dir", str(args.demo_books_dir.resolve()), "--authorized-demo-use"]
    run(preparation, root=root, environment=environment)
    if args.frontend:
        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if npm is None:
            raise RuntimeError("Node.js/npm are required when --frontend is selected.")
        cache = args.npm_cache.resolve() if args.npm_cache is not None else directory / "npm-cache"
        environment.update({
            "NPM_CONFIG_REGISTRY": "https://registry.npmjs.org",
            "NPM_CONFIG_USERCONFIG": str(directory / "empty-user.npmrc"),
            "NPM_CONFIG_GLOBALCONFIG": str(directory / "empty-global.npmrc"),
            "NPM_CONFIG_CACHE": str(cache),
        })
        npm_command = [npm, "ci", "--registry=https://registry.npmjs.org", "--audit=false", "--fund=false"]
        if args.npm_offline:
            npm_command.append("--offline")
        run(npm_command, root=root / "frontend", environment=environment)
        run([npm, "run", "build"], root=root / "frontend", environment=environment)
    receipt = {
        "profile": "assessment-windows-py312-cpu", "state": "ready",
        "project_root": str(root),
        "python": sys.version.split()[0],
        "dependency_lock_sha256": hashlib.sha256(lock.read_text(encoding="utf-8").encode("utf-8")).hexdigest(),
        "uses_system_site_packages": False,
        "private_model_cache_required": False,
        "frontend_prepared": args.frontend,
        "paid_model_calls": 0,
    }
    (directory / OWNERSHIP_MARKER).write_text(json.dumps(receipt, indent=2) + "\n",
                                             encoding="utf-8", newline="\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
