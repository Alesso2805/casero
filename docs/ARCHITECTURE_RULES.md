# Reglas de arquitectura

Cada regla tiene un ID estable (AR-NN), el ADR que la origina y el test que la verifica en CI. Un PR con un test de arquitectura en rojo no se fusiona.

CS-02 completa esta lista con las demás reglas que piden los ADR y escribe sus tests. Cada test lleva su meta-test: un ejemplo que viola la regla y que el chequeo debe detectar. Las tres reglas de abajo se escribieron con CS-01 porque describen el patrón de módulos y puertos. Su test todavía no existe, y CS-02 no se cierra sin él.

| ID | Regla | Origen | Test | Estado |
| --- | --- | --- | --- | --- |
| AR-01 | Los módulos siguen el orden `shared.kernel` → `identity` → `accounts` → `properties` → `leases` → `ledger` → `tax` → `reminders` → `tenant_portal` → `admin`. Un módulo nunca importa uno posterior, en ninguna capa | ADR-0001 | Contrato `layers` de import-linter | Test en CS-02 |
| AR-02 | Entre módulos solo se importa la capa `application` de un módulo anterior; nunca su `domain`, `infrastructure` ni `api` | ADR-0001 | Contratos `forbidden` de import-linter | Test en CS-02 |
| AR-03 | Si un módulo necesita datos de uno posterior, declara un puerto (`Protocol`) en su `application` y el módulo posterior lo implementa. El cableado vive solo en `casero/api.py` y `casero/worker.py`: ningún otro archivo importa la `infrastructure` de otro módulo ni construye implementaciones de puertos de otro módulo | ADR-0001 | Contrato `forbidden` con `casero.api` y `casero.worker` como únicas excepciones, y un test de que cada puerto declarado tiene una implementación cableada en un punto de arranque | Test en CS-02 |

## Patrón de puertos (AR-03)

1. El módulo inferior declara en su `application` un `Protocol` con el nombre de lo que necesita, por ejemplo `TenantLinkProvider` en `reminders`.
2. El módulo superior lo implementa. Puede importar el `application` del inferior, porque esa dependencia va hacia abajo.
3. `casero/api.py` y `casero/worker.py` construyen la implementación y la inyectan. Es el único lugar donde se conectan módulos así.
4. Las pruebas del módulo inferior usan una implementación falsa del puerto.

Casos conocidos:

- `reminders` obtiene de `tenant_portal` el enlace vigente para `{enlace}`.
- El resumen diario de `reminders` cuenta los vouchers pendientes de `tenant_portal`.
- La exportación de `accounts` reúne una sección de cada módulo.
