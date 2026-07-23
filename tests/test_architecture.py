"""Gate for the layer dependency rule (lightweight Clean Architecture).

Fails if: gi is imported outside ui/; domain/ imports any internal
layer; app/ imports infra/ or ui/; infra/ imports app/ or ui/.
See the "Plano — camadas físicas" section in the ROADMAP.
"""

import ast
from pathlib import Path

PACKAGE = Path(__file__).parent.parent / "src" / "tomenotas"

# layer -> internal layers it MAY import (besides its own)
ALLOWED = {
    "domain": set(),
    "app": {"domain"},
    "infra": {"domain"},
    "ui": {"domain", "app", "infra"},
}


def _files_per_layer():
    for layer in ALLOWED:
        for file in sorted((PACKAGE / layer).glob("*.py")):
            yield layer, file


def _absolute_imports(layer, file):
    """All imports in the file as absolute module names."""
    tree = ast.parse(file.read_text(encoding="utf-8"))
    current_package = ["tomenotas", layer]  # package containing the module
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                yield node.module or ""
            else:
                base = current_package[:len(current_package) - (node.level - 1)]
                module = node.module.split(".") if node.module else []
                yield ".".join(base + module)


def _layer_of(module):
    parts = module.split(".")
    if parts[0] != "tomenotas" or len(parts) < 2:
        return None  # external (stdlib etc.) or the package root
    return parts[1] if parts[1] in ALLOWED else None


def test_gi_may_only_be_imported_in_ui():
    violations = []
    for layer, file in _files_per_layer():
        if layer == "ui":
            continue
        for module in _absolute_imports(layer, file):
            if module == "gi" or module.startswith("gi."):
                violations.append(f"{layer}/{file.name} imports {module}")
    assert violations == []


def test_layer_dependency_rule():
    violations = []
    for layer, file in _files_per_layer():
        authorized = ALLOWED[layer] | {layer}
        for module in _absolute_imports(layer, file):
            target = _layer_of(module)
            if target is not None and target not in authorized:
                violations.append(
                    f"{layer}/{file.name} imports {module} "
                    f"(layer {target} is forbidden for {layer})"
                )
    assert violations == []


def test_all_layers_exist_and_have_modules():
    for layer in ALLOWED:
        modules = list((PACKAGE / layer).glob("*.py"))
        assert modules, f"layer {layer}/ empty or missing"
