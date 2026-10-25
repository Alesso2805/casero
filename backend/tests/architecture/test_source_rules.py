from pathlib import Path

import pytest

from architecture import source_rules as rules

BACKEND = Path(__file__).resolve().parents[2]
PACKAGE = BACKEND / "src" / "casero"
CLOCK_MODULE = PACKAGE / "shared" / "kernel" / "clock.py"
COMPOSITION_ROOTS = [PACKAGE / "api.py", PACKAGE / "worker.py"]
MIGRATIONS = BACKEND / "migrations"
WEB_SOURCES = BACKEND.parent / "web" / "src"


def package_files() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


def application_files() -> list[Path]:
    return sorted(PACKAGE.glob("*/application/**/*.py"))


def api_process_files() -> list[Path]:
    return [PACKAGE / "api.py", *sorted(PACKAGE.glob("*/api/**/*.py"))]


def web_files() -> list[Path]:
    return (
        sorted(path for path in WEB_SOURCES.rglob("*") if path.suffix in {".ts", ".tsx"})
        if WEB_SOURCES.exists()
        else []
    )


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS.rglob("*.py")) if MIGRATIONS.exists() else []


def write(tmp_path: Path, name: str, source: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_ar03_every_port_is_wired_in_a_composition_root() -> None:
    assert rules.unwired_ports(application_files(), COMPOSITION_ROOTS) == []


def test_ar03_meta_detects_an_unwired_port(tmp_path: Path) -> None:
    port = write(tmp_path, "port.py", "from typing import Protocol\n\nclass Links(Protocol): ...\n")
    root = write(tmp_path, "api.py", "links = make_links()\n")
    wired_root = write(tmp_path, "wired.py", "links: Links = make_links()\n")

    assert len(rules.unwired_ports([port], [root])) == 1
    assert rules.unwired_ports([port], [wired_root]) == []


def test_ar06_wall_clock_is_read_only_in_the_clock() -> None:
    files = [path for path in package_files() if path != CLOCK_MODULE]

    assert rules.wall_clock_reads(files) == []


@pytest.mark.parametrize(
    "source",
    [
        "from datetime import datetime\nstamp = datetime.now()\n",
        "import datetime\ntoday = datetime.date.today()\n",
        "from datetime import datetime\nstamp = datetime.utcnow()\n",
    ],
)
def test_ar06_meta_detects_wall_clock_reads(tmp_path: Path, source: str) -> None:
    assert len(rules.wall_clock_reads([write(tmp_path, "module.py", source)])) == 1


def test_ar07_api_process_schedules_no_work() -> None:
    assert rules.scheduled_work(api_process_files()) == []


@pytest.mark.parametrize(
    "source",
    [
        "import asyncio\nasyncio.create_task(job())\n",
        "@app.on_event('startup')\nasync def start() -> None: ...\n",
        "import threading\nthreading.Thread(target=job).start()\n",
    ],
)
def test_ar07_meta_detects_scheduled_work(tmp_path: Path, source: str) -> None:
    assert len(rules.scheduled_work([write(tmp_path, "api.py", source)])) == 1


def test_ar08_money_never_uses_float() -> None:
    assert rules.float_usage(package_files()) == []


@pytest.mark.parametrize("source", ["price: float = 0\n", "ratio = 0.05\n", "total = float(x)\n"])
def test_ar08_meta_detects_float(tmp_path: Path, source: str) -> None:
    assert len(rules.float_usage([write(tmp_path, "money.py", source)])) == 1


def test_ar09_tax_domain_has_no_tax_literals() -> None:
    assert rules.tax_literals(sorted((PACKAGE / "tax" / "domain").rglob("*.py"))) == []


def test_ar09_meta_detects_tax_literals(tmp_path: Path) -> None:
    module = write(tmp_path, "rules.py", "RATE_BP = 625\nfirst = items[0]\nnext_one = index + 1\n")

    assert [violation.message for violation in rules.tax_literals([module])] == [
        "numeric literal 625"
    ]


def test_ar10_whatsapp_is_reached_only_through_wa_me_links() -> None:
    assert rules.whatsapp_endpoints([*package_files(), *web_files()]) == []


def test_ar10_meta_detects_whatsapp_api_endpoints(tmp_path: Path) -> None:
    api_call = write(tmp_path, "send.py", "URL = 'https://graph.facebook.com/v21.0/messages'\n")
    link = write(tmp_path, "link.ts", "const url = `https://wa.me/${phone}?text=${text}`;\n")

    assert len(rules.whatsapp_endpoints([api_call])) == 1
    assert rules.whatsapp_endpoints([link]) == []


def test_ar11_sql_never_reads_the_database_clock() -> None:
    assert rules.sql_wall_clock([*package_files(), *migration_files()]) == []


@pytest.mark.parametrize(
    "source",
    [
        "query = 'SELECT * FROM charges WHERE due_date < CURRENT_DATE'\n",
        "query = 'INSERT INTO payments (created_at) VALUES (now())'\n",
        "from sqlalchemy import func\ncolumn = func.now()\n",
    ],
)
def test_ar11_meta_detects_database_clock_reads(tmp_path: Path, source: str) -> None:
    assert len(rules.sql_wall_clock([write(tmp_path, "query.py", source)])) == 1


def test_ar12_set_config_is_always_bound() -> None:
    assert rules.interpolated_set_config(package_files()) == []


def test_ar12_meta_detects_interpolated_set_config(tmp_path: Path) -> None:
    interpolated = write(
        tmp_path, "bad.py", "sql = f\"SELECT set_config('app.account_id', '{account}', true)\"\n"
    )
    bound = write(tmp_path, "good.py", "sql = \"SELECT set_config('app.account_id', :id, true)\"\n")

    assert len(rules.interpolated_set_config([interpolated])) == 1
    assert rules.interpolated_set_config([bound]) == []
