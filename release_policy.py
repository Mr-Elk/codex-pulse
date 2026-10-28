"""Explicit Windows payload selection and checks shared by builds and preflight.

No file discovery adds content to a package. New local files are ignored unless
reviewed into the specification; dependencies omitted from it fail validation.
"""
import ast
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

from product_version import windows_version


SPEC_PATH = "distribution/windows-package.json"
REQUIRED = {"plugin.json", "LICENSE", "README.md", "BETA_GUIDE.md", "RELEASE_NOTES.md", SPEC_PATH}


def checked_name(name):
    if not isinstance(name, str) or not name:
        raise ValueError("Package paths must be nonempty strings")
    path = PurePosixPath(name)
    if (not path.parts or path.is_absolute() or path.as_posix() != name or ".." in path.parts
            or any(part.rstrip(" .") != part
                   or re.search(r'[<>:"\\|?*\x00-\x1f]', part)
                   or re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', part)
                   for part in path.parts)):
        raise ValueError(f"Invalid package path: {name}")
    lower = name.lower()
    if (path.parts[0].lower() in {".git", "qa", "dist", "data", "releases", "macos", "cli_dist"}
            or any(part.startswith(("._", ".env")) or part == "__pycache__" for part in path.parts)
            or lower.endswith((".log", ".sqlite", ".sqlite3", ".jsonl", ".pyc"))
            or path.name.lower().startswith(("settings", "runtime.")) and path.suffix.lower() == ".json"
            or lower.startswith(("cli_", "macos_")) or lower == "pulse_cli.py"
            or lower == ".codex-pulse-local.json"):
        raise ValueError(f"Not a Windows distribution input: {name}")
    return name


def read_input(root, name):
    checked_name(name)
    path = root
    for part in PurePosixPath(name).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"Symlink cannot be packaged: {name}")
    if not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError(f"Required package file is missing: {name}")
    return path.read_bytes()


def load_spec(root):
    spec = json.loads(read_input(root, SPEC_PATH))
    fields = {"schema", "platform", "version_source", "runtime", "development",
              "optional_runtime", "templates", "version_documents"}
    if (not isinstance(spec, dict) or set(spec) != fields or type(spec["schema"]) is not int
            or spec["schema"] != 1 or spec["platform"] != "windows"
            or spec["version_source"] != "plugin.json"):
        raise ValueError("Unsupported Windows package specification")
    names = []
    for group in ("runtime", "development", "optional_runtime"):
        if not isinstance(spec[group], list):
            raise ValueError(f"Package {group} must be an explicit list")
        names.extend(checked_name(name) for name in spec[group])
    if not isinstance(spec["templates"], dict) or not isinstance(spec["version_documents"], dict):
        raise ValueError("Package documentation contracts must be objects")
    for name, source in spec["templates"].items():
        names.append(checked_name(name))
        checked_name(source)
        if not name.endswith(".md") or not source.endswith(".md.in"):
            raise ValueError("Only Markdown documentation templates can be rendered")
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError("Duplicate or ambiguous Windows package paths")
    runtime = set(spec["runtime"]) | set(spec["templates"])
    if not REQUIRED <= runtime:
        raise ValueError("Windows package must include metadata, license and candidate guides")
    for name, pattern in spec["version_documents"].items():
        if name not in runtime or not isinstance(pattern, str):
            raise ValueError("Invalid versioned document contract")
        try:
            groups = re.compile(pattern).groups
        except re.error as error:
            raise ValueError("Invalid versioned document pattern") from error
        if groups != 1:
            raise ValueError("Versioned document patterns need exactly one version capture")
    if not {"BETA_GUIDE.md", "RELEASE_NOTES.md"} <= set(spec["version_documents"]):
        raise ValueError("Candidate guide and release notes require version checks")
    return spec


def check_dependencies(files):
    """Validate literal imports without executing application or test code."""
    for name, data in files.items():
        if not name.endswith(".py"):
            continue
        tree = ast.parse(data, filename=name)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.level:
                    parent = PurePosixPath(name).parent.parts
                    prefix = parent[:len(parent) - node.level + 1]
                    imports.add(".".join((*prefix, node.module)))
                else:
                    imports.add(node.module)
            elif isinstance(node, ast.Call) and node.args:
                dynamic = (isinstance(node.func, ast.Name) and node.func.id == "__import__"
                           or isinstance(node.func, ast.Attribute) and node.func.attr == "import_module")
                if dynamic and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    imports.add(node.args[0].value)
        for module in imports:
            if module.split(".")[0] in sys.stdlib_module_names:
                continue
            target = module.replace(".", "/")
            if target + ".py" not in files and target + "/__init__.py" not in files:
                raise ValueError(f"{name} requires an unlisted Python module: {module}")


def selected_files(root, include_tests=True):
    root = Path(root).resolve()
    version = windows_version(root)
    spec = load_spec(root)
    selected = spec["runtime"] + (spec["development"] if include_tests else [])
    files = {name: read_input(root, name) for name in selected}
    for name in spec["optional_runtime"]:
        if (root / name).exists() or (root / name).is_symlink():
            files[name] = read_input(root, name)
    for name, source in spec["templates"].items():
        template = read_input(root, source).decode("utf-8")
        rendered = template.replace("{{version}}", version)
        if "{{" in rendered or "}}" in rendered:
            raise ValueError(f"Unresolved documentation template: {source}")
        files[name] = rendered.encode("utf-8")
    for name, pattern in spec["version_documents"].items():
        matches = re.findall(pattern, files[name].decode("utf-8-sig"), re.MULTILINE)
        if matches != [version]:
            raise ValueError(f"{name} version differs from plugin.json ({version})")
    if not files["LICENSE"].strip():
        raise ValueError("Package license is empty")
    check_dependencies(files)
    return files


def clean_revision(root):
    """A dirty tree or a non-Git fixture has no attested source revision."""
    root = Path(root).resolve()
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=root,
                             capture_output=True, text=True, check=True, timeout=10).stdout.strip()
        if Path(top).resolve() != root:
            return None
        status = subprocess.run(["git", "status", "--porcelain=v1", "--untracked-files=all"],
                                cwd=root, capture_output=True, check=True, timeout=10)
        if status.stdout:
            return None
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
                              text=True, check=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
