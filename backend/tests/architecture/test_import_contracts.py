import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

BACKEND = Path(__file__).resolve().parents[2]
PACKAGE = BACKEND / "src" / "casero"
PYPROJECT = BACKEND / "pyproject.toml"
LAYERS = ["api", "infrastructure", "application", "domain"]


def contracts() -> dict[str, dict[str, Any]]:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return {contract["id"]: contract for contract in config["tool"]["importlinter"]["contracts"]}


def business_modules() -> list[str]:
    return sorted(
        path.name
        for path in PACKAGE.iterdir()
        if (path / "__init__.py").exists() and path.name != "shared"
    )


def lint_imports(project: Path) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("lint-imports", path=str(Path(sys.executable).parent))
    assert executable is not None
    env = {
        **os.environ,
        "PYTHONPATH": str(project / "src"),
        "PYTHONIOENCODING": "utf-8",
        "COLUMNS": "200",
    }
    return subprocess.run(
        [executable, "--no-cache", "--config", str(project / "pyproject.toml")],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def contract_status(output: str, name: str) -> str:
    for line in output.splitlines():
        if line.startswith(name):
            return line.removeprefix(name).strip()
    raise AssertionError(f"{name} is missing from the lint-imports output:\n{output}")


def fake_project(tmp_path: Path) -> Path:
    for init in PACKAGE.rglob("__init__.py"):
        target = tmp_path / "src" / "casero" / init.relative_to(PACKAGE)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
    (tmp_path / "src" / "casero" / "api.py").touch()
    shutil.copy(PYPROJECT, tmp_path / "pyproject.toml")
    return tmp_path


def test_import_contracts_hold() -> None:
    result = lint_imports(BACKEND)

    assert result.returncode == 0, result.stdout + result.stderr


def test_every_module_is_covered_by_the_contracts() -> None:
    configured = contracts()
    order = " ".join(configured["ar-01"]["layers"])
    composition_roots = ["casero.api"]
    if (PACKAGE / "worker.py").exists():
        composition_roots.append("casero.worker")

    for module in business_modules():
        assert f"casero.{module}" in order
        assert f"casero.{module}" in configured["ar-04"]["containers"]
        protected = configured[f"ar-02-{module}"]
        assert protected["protected_modules"] == [
            f"casero.{module}.{layer}" for layer in ("domain", "infrastructure", "api")
        ]
        assert protected["allowed_importers"] == [f"casero.{module}", *composition_roots]
        for layer in LAYERS:
            assert (PACKAGE / module / layer / "__init__.py").exists()


def test_meta_clean_skeleton_keeps_every_contract(tmp_path: Path) -> None:
    result = lint_imports(fake_project(tmp_path))

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("contract", "module", "source"),
    [
        (
            "AR-01 modules follow the dependency order",
            "identity/application/uses_ledger.py",
            "import casero.ledger.application\n",
        ),
        (
            "AR-02 leases internals stay private",
            "ledger/application/uses_leases_domain.py",
            "import casero.leases.domain\n",
        ),
        (
            "AR-04 each module keeps its internal layers",
            "leases/domain/uses_application.py",
            "import casero.leases.application\n",
        ),
        (
            "AR-05 domain, application and kernel stay framework-free",
            "leases/domain/uses_fastapi.py",
            "import fastapi\n",
        ),
        (
            "AR-05 domain, application and kernel stay framework-free",
            "tax/application/uses_shared_infrastructure.py",
            "import casero.shared.infrastructure\n",
        ),
    ],
)
def test_meta_contracts_detect_violations(
    tmp_path: Path, contract: str, module: str, source: str
) -> None:
    project = fake_project(tmp_path)
    (project / "src" / "casero" / module).write_text(source, encoding="utf-8")

    result = lint_imports(project)

    assert result.returncode != 0
    assert contract_status(result.stdout, contract) == "BROKEN"
