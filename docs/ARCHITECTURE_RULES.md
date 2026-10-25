# Reglas de arquitectura

Cada regla tiene un ID estable (AR-NN), el documento que la origina y el test que la verifica en CI. Un PR con un test de arquitectura en rojo no se fusiona.

Cada test tiene su meta-test: un ejemplo que viola la regla y que el chequeo debe detectar. Así una regla que deja de verificar nada falla en lugar de pasar en silencio.

Los tests viven en `backend/tests/architecture/`. Los contratos de import-linter están en `backend/pyproject.toml`. Las reglas que necesitan la base de datos (RLS forzada, permisos de cada rol, funciones `SECURITY DEFINER`, ausencia de `DEFAULT now()` en el libro) las agrega CS-03, cada una con su test de catálogo.

| ID | Regla | Origen | Test |
| --- | --- | --- | --- |
| AR-01 | Los módulos siguen el orden `shared.kernel` → `shared.infrastructure` → `identity` → `accounts` → `properties` → `leases` → `ledger` → `tax` → `reminders` → `tenant_portal` → `admin` → `casero.api` y `casero.worker`. Ningún módulo importa uno posterior, en ninguna capa | ADR-0001 | Contrato `ar-01` |
| AR-02 | Entre módulos solo se importa la capa `application`. El `domain`, la `infrastructure` y la `api` de un módulo solo los importan ese módulo y los puntos de arranque | ADR-0001 | Contratos `ar-02-<módulo>` y `test_every_module_is_covered_by_the_contracts` |
| AR-03 | Si un módulo necesita datos de uno posterior, declara un puerto (`Protocol`) en su `application` y el módulo posterior lo implementa. El cableado vive solo en `casero/api.py` y `casero/worker.py`, con una asignación anotada con el tipo del puerto, para que Mypy verifique que la implementación lo cumple | ADR-0001 | Contratos `ar-02-<módulo>` y `test_ar03_*` |
| AR-04 | Dentro de cada módulo, las capas van `api` → `infrastructure` → `application` → `domain`, y ninguna importa una capa superior | ADR-0001 | Contrato `ar-04` |
| AR-05 | `domain`, `application` y `shared.kernel` no importan FastAPI, Starlette, Uvicorn, SQLAlchemy, asyncpg ni `shared.infrastructure` | ADR-0001 | Contrato `ar-05` |
| AR-06 | `datetime.now()`, `datetime.utcnow()` y `date.today()` solo se usan dentro de `casero/shared/kernel/clock.py` | CLAUDE.md (regla 2), ADR-0001 | `test_ar06_*` |
| AR-07 | El proceso de la API no programa trabajo: ni `create_task`, `ensure_future`, hilos, timers ni `on_event` en `casero/api.py` ni en las capas `api` | CLAUDE.md, ADR-0001 | `test_ar07_*` |
| AR-08 | El backend no usa `float`: el dinero va en céntimos enteros | CLAUDE.md (regla 1), ADR-0003 | `test_ar08_*` |
| AR-09 | `casero.tax.domain` no tiene literales numéricos salvo 0 y 1. Las tasas, las fechas y los montos vienen de `tax_rule_sets` y `sunat_due_dates`, y las constantes de unidades viven en `shared.kernel` | CLAUDE.md (regla 6), ADR-0005 | `test_ar09_*` |
| AR-10 | WhatsApp solo se usa con enlaces `https://wa.me/`, en el backend y en el frontend | CLAUDE.md (regla 9), ADR-0006 | `test_ar10_*` |
| AR-11 | Ningún SQL ni migración lee el reloj de la base (`CURRENT_DATE`, `now()`, `func.now()` y similares) | CLAUDE.md (regla 2), ADR-0002 y ADR-0003 | `test_ar11_*` |
| AR-12 | `set_config` se llama solo con parámetros enlazados, nunca con texto interpolado | CLAUDE.md (regla 3), ADR-0002 | `test_ar12_*` |

## Patrón de puertos (AR-03)

1. El módulo inferior declara en su `application` un `Protocol` con el nombre de lo que necesita, por ejemplo `TenantLinkProvider` en `reminders`.
2. El módulo superior lo implementa. Puede importar el `application` del inferior, porque esa dependencia va hacia abajo.
3. `casero/api.py` y `casero/worker.py` construyen la implementación y la asignan con el tipo del puerto (`links: TenantLinkProvider = TenantLinks(...)`). Es el único lugar donde se conectan módulos de esta forma.
4. Las pruebas del módulo inferior usan una implementación falsa del puerto.

Casos conocidos:

- `reminders` obtiene de `tenant_portal` el enlace vigente para `{enlace}`.
- El resumen diario de `reminders` cuenta los vouchers pendientes de `tenant_portal`.
- La exportación de `accounts` reúne una sección de cada módulo.
