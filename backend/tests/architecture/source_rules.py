import ast
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


WALL_CLOCK_CALLS = frozenset({"now", "utcnow", "today"})
SCHEDULING_CALLS = frozenset(
    {
        "create_task",
        "ensure_future",
        "run_coroutine_threadsafe",
        "call_later",
        "call_at",
        "Thread",
        "Timer",
        "on_event",
    }
)
ALLOWED_TAX_LITERALS = frozenset({0, 1})
WHATSAPP_HOSTS = re.compile(r"whatsapp\.(?:com|net)|graph\.facebook\.com|wa\.me", re.IGNORECASE)
WA_ME_LINK = "https://wa.me/"
SQL_WALL_CLOCK = re.compile(
    r"\b(?:current_date|current_timestamp|current_time|localtimestamp|localtime)\b"
    r"|\b(?:now|clock_timestamp|statement_timestamp|transaction_timestamp)\s*\(\s*\)",
    re.IGNORECASE,
)
SQL_WALL_CLOCK_FUNCS = frozenset(
    {"func.now", "func.current_date", "func.current_timestamp", "func.localtimestamp"}
)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _dotted(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    return ""


def _calls(tree: ast.AST) -> Iterator[tuple[ast.Call, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node, _dotted(node.func)


def _mentions_set_config(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "set_config" in node.value.lower()
    )


def unwired_ports(application_files: Iterable[Path], roots: Iterable[Path]) -> list[Violation]:
    wiring = "\n".join(root.read_text(encoding="utf-8") for root in roots if root.exists())
    violations = []
    for path in application_files:
        for node in ast.walk(_parse(path)):
            if not isinstance(node, ast.ClassDef):
                continue
            if not any(_dotted(base) in {"Protocol", "typing.Protocol"} for base in node.bases):
                continue
            if not re.search(rf":\s*{re.escape(node.name)}\b", wiring):
                violations.append(
                    Violation(
                        path, node.lineno, f"port {node.name} is not wired in a composition root"
                    )
                )
    return violations


def wall_clock_reads(files: Iterable[Path]) -> list[Violation]:
    violations = []
    for path in files:
        for call, name in _calls(_parse(path)):
            parts = name.split(".")
            if (
                len(parts) >= 2
                and parts[-1] in WALL_CLOCK_CALLS
                and parts[-2] in {"datetime", "date"}
            ):
                violations.append(Violation(path, call.lineno, f"{name}() outside the Clock"))
    return violations


def scheduled_work(files: Iterable[Path]) -> list[Violation]:
    violations = []
    for path in files:
        for call, name in _calls(_parse(path)):
            if name.split(".")[-1] in SCHEDULING_CALLS:
                violations.append(
                    Violation(path, call.lineno, f"{name}() schedules work in the API")
                )
    return violations


def float_usage(files: Iterable[Path]) -> list[Violation]:
    violations = []
    for path in files:
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.Name) and node.id == "float":
                violations.append(Violation(path, node.lineno, "float type"))
            elif isinstance(node, ast.Constant) and isinstance(node.value, float):
                violations.append(Violation(path, node.lineno, f"float literal {node.value}"))
    return violations


def tax_literals(files: Iterable[Path]) -> list[Violation]:
    violations = []
    for path in files:
        for node in ast.walk(_parse(path)):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, int | float)
                and not isinstance(node.value, bool)
                and node.value not in ALLOWED_TAX_LITERALS
            ):
                violations.append(Violation(path, node.lineno, f"numeric literal {node.value}"))
    return violations


def whatsapp_endpoints(files: Iterable[Path]) -> list[Violation]:
    violations = []
    for path in files:
        lines = path.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, start=1):
            if WHATSAPP_HOSTS.search(line.replace(WA_ME_LINK, "")):
                violations.append(
                    Violation(path, number, "WhatsApp endpoint other than wa.me links")
                )
    return violations


def sql_wall_clock(files: Iterable[Path]) -> list[Violation]:
    violations = []
    for path in files:
        if path.suffix != ".py":
            lines = path.read_text(encoding="utf-8").splitlines()
            for number, line in enumerate(lines, start=1):
                if SQL_WALL_CLOCK.search(line):
                    violations.append(Violation(path, number, "SQL reads the database clock"))
            continue
        tree = _parse(path)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and SQL_WALL_CLOCK.search(node.value)
            ):
                violations.append(Violation(path, node.lineno, "SQL reads the database clock"))
        for call, name in _calls(tree):
            if any(name.endswith(func) for func in SQL_WALL_CLOCK_FUNCS):
                violations.append(
                    Violation(path, call.lineno, f"{name}() reads the database clock")
                )
    return violations


def interpolated_set_config(files: Iterable[Path]) -> list[Violation]:
    violations = []
    for path in files:
        for node in ast.walk(_parse(path)):
            if not isinstance(node, ast.expr):
                continue
            interpolated = (
                (isinstance(node, ast.JoinedStr) and any(map(_mentions_set_config, node.values)))
                or (
                    isinstance(node, ast.BinOp)
                    and (_mentions_set_config(node.left) or _mentions_set_config(node.right))
                )
                or (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "format"
                    and _mentions_set_config(node.func.value)
                )
            )
            if interpolated:
                violations.append(
                    Violation(path, node.lineno, "set_config built with interpolated text")
                )
    return violations
