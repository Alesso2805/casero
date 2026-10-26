import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import asyncpg

OWNER = "casero_owner"
BACKUP = "casero_backup"
APPLICATION_ROLES = ("casero_app", "casero_worker", "casero_admin")
ROLES_THAT_BYPASS_RLS = frozenset({OWNER, BACKUP})

TablePrivileges = dict[str, dict[str, set[str]]]
ColumnPrivileges = dict[str, dict[str, dict[str, set[str]]]]
ExpectedTablePrivileges = Mapping[str, Mapping[str, frozenset[str]]]
ExpectedColumnPrivileges = Mapping[str, Mapping[str, Mapping[str, frozenset[str]]]]

TABLE_PRIVILEGES = """
SELECT c.relname AS table_name, coalesce(r.rolname, 'PUBLIC') AS grantee, a.privilege_type
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
CROSS JOIN LATERAL aclexplode(c.relacl) a
LEFT JOIN pg_roles r ON r.oid = a.grantee
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.grantee <> c.relowner
"""

COLUMN_PRIVILEGES = """
SELECT c.relname AS table_name, at.attname AS column_name,
       coalesce(r.rolname, 'PUBLIC') AS grantee, a.privilege_type
FROM pg_attribute at
JOIN pg_class c ON c.oid = at.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
CROSS JOIN LATERAL aclexplode(at.attacl) a
LEFT JOIN pg_roles r ON r.oid = a.grantee
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND at.attnum > 0 AND NOT at.attisdropped
"""

TABLES = """
SELECT c.relname AS name, c.relrowsecurity AS rls, c.relforcerowsecurity AS forced,
       r.rolname AS owner
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_roles r ON r.oid = c.relowner
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
"""

CLOCK_DEFAULT = re.compile(
    r"\b(?:now|clock_timestamp|statement_timestamp|transaction_timestamp)\s*\(\s*\)"
    r"|\b(?:current_date|current_timestamp|current_time|localtimestamp|localtime)\b",
    re.IGNORECASE,
)

COLUMN_DEFAULTS = """
SELECT c.relname AS table_name, a.attname AS column_name,
       pg_get_expr(d.adbin, d.adrelid) AS expression
FROM pg_attrdef d
JOIN pg_class c ON c.oid = d.adrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum
WHERE n.nspname = 'public'
"""


ROLES = r"SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname LIKE 'casero\_%'"


@dataclass(frozen=True)
class Table:
    name: str
    rls: bool
    forced: bool
    owner: str


@dataclass(frozen=True)
class Role:
    name: str
    superuser: bool
    bypass_rls: bool


async def table_privileges(connection: asyncpg.Connection) -> TablePrivileges:
    privileges: TablePrivileges = defaultdict(lambda: defaultdict(set))
    for row in await connection.fetch(TABLE_PRIVILEGES):
        privileges[row["grantee"]][row["table_name"]].add(row["privilege_type"])
    return privileges


async def column_privileges(connection: asyncpg.Connection) -> ColumnPrivileges:
    privileges: ColumnPrivileges = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    for row in await connection.fetch(COLUMN_PRIVILEGES):
        grantee, table = row["grantee"], row["table_name"]
        privileges[grantee][table][row["privilege_type"]].add(row["column_name"])
    return privileges


async def tables(connection: asyncpg.Connection) -> list[Table]:
    return [Table(**row) for row in await connection.fetch(TABLES)]


async def roles(connection: asyncpg.Connection) -> list[Role]:
    return [
        Role(row["rolname"], row["rolsuper"], row["rolbypassrls"])
        for row in await connection.fetch(ROLES)
    ]


def tables_without_forced_rls(
    all_tables: Iterable[Table], closed_list: frozenset[str]
) -> list[str]:
    return sorted(
        table.name
        for table in all_tables
        if table.name not in closed_list and not (table.rls and table.forced)
    )


def ownership_and_role_problems(
    all_tables: Iterable[Table], all_roles: Iterable[Role]
) -> list[str]:
    problems = [
        f"{table.name} is owned by {table.owner}" for table in all_tables if table.owner != OWNER
    ]
    for role in all_roles:
        if role.superuser:
            problems.append(f"{role.name} is a superuser")
        if role.bypass_rls != (role.name in ROLES_THAT_BYPASS_RLS):
            problems.append(f"{role.name} has BYPASSRLS={role.bypass_rls}")
    return sorted(problems)


def privilege_differences(
    actual_tables: TablePrivileges,
    actual_columns: ColumnPrivileges,
    table_names: Iterable[str],
    expected_tables: ExpectedTablePrivileges,
    expected_columns: ExpectedColumnPrivileges,
) -> list[str]:
    differences = []
    names = sorted(table_names)
    for role in APPLICATION_ROLES:
        for table in names:
            actual = actual_tables.get(role, {}).get(table, set())
            expected = expected_tables.get(role, {}).get(table, frozenset())
            differences += [f"{role}: unexpected {p} on {table}" for p in sorted(actual - expected)]
            differences += [f"{role}: missing {p} on {table}" for p in sorted(expected - actual)]
            actual_by_privilege = actual_columns.get(role, {}).get(table, {})
            expected_by_privilege = expected_columns.get(role, {}).get(table, {})
            for privilege in sorted(set(actual_by_privilege) | set(expected_by_privilege)):
                got = actual_by_privilege.get(privilege, set())
                want = expected_by_privilege.get(privilege, frozenset())
                differences += [
                    f"{role}: unexpected {privilege}({c}) on {table}" for c in sorted(got - want)
                ]
                differences += [
                    f"{role}: missing {privilege}({c}) on {table}" for c in sorted(want - got)
                ]
    for table in names:
        backup = actual_tables.get(BACKUP, {}).get(table, set())
        if backup != {"SELECT"}:
            differences.append(f"{BACKUP}: has {sorted(backup)} on {table}, expected SELECT only")
        if table in actual_tables.get("PUBLIC", {}) or table in actual_columns.get("PUBLIC", {}):
            differences.append(f"PUBLIC: has privileges on {table}")
    return differences


async def clock_defaults(connection: asyncpg.Connection) -> list[str]:
    return sorted(
        f"{row['table_name']}.{row['column_name']} DEFAULT {row['expression']}"
        for row in await connection.fetch(COLUMN_DEFAULTS)
        if CLOCK_DEFAULT.search(row["expression"])
    )


SECURITY_DEFINER_FUNCTIONS = """
SELECT p.proname AS name, r.rolname AS owner, p.prosecdef AS security_definer,
       coalesce(array_to_string(p.proconfig, ','), '') AS config,
       coalesce(
           (SELECT array_agg(coalesce(g.rolname, 'PUBLIC') ORDER BY coalesce(g.rolname, 'PUBLIC'))
            FROM aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
            LEFT JOIN pg_roles g ON g.oid = a.grantee
            WHERE a.privilege_type = 'EXECUTE' AND a.grantee <> p.proowner),
           '{}'
       ) AS executors
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
JOIN pg_roles r ON r.oid = p.proowner
WHERE n.nspname = 'public'
"""


async def function_problems(
    connection: asyncpg.Connection, expected_executors: Mapping[str, frozenset[str]]
) -> list[str]:
    problems = []
    rows = {row["name"]: row for row in await connection.fetch(SECURITY_DEFINER_FUNCTIONS)}
    for name in sorted(set(rows) | set(expected_executors)):
        row = rows.get(name)
        if row is None:
            problems.append(f"{name} is missing")
            continue
        if name not in expected_executors:
            problems.append(f"{name} is not a listed function")
            continue
        if row["owner"] != OWNER:
            problems.append(f"{name} is owned by {row['owner']}")
        if row["security_definer"] and "search_path=" not in row["config"]:
            problems.append(f"{name} has no fixed search_path")
        executors = frozenset(row["executors"])
        if executors != expected_executors[name]:
            problems.append(f"{name} is executable by {sorted(executors)}")
    return problems
