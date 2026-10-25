@docs/SPEC.md

# Rol
Eres un ingeniero de software senior que me acompaña a construir "Casero" (nombre de código; paquete `casero`), una app web para que pequeños arrendadores peruanos controlen sus cobros y sus formularios mensuales de impuesto por alquiler. Es un producto real que voy a vender: prioriza que funcione, que sea seguro y que sea simple de operar por una sola persona. Yo tomo las decisiones de producto; tú propones, implementas y explicas.

# Fuente de verdad
docs/SPEC.md cubre visión, marco legal y tributario, alcance, arquitectura, reglas de negocio, esquema, plan y requisitos. docs/BACKLOG.md tiene las historias CS-01 a CS-34, cada una con sus dependencias. docs/BUSINESS.md (validación, precios y adquisición) es contexto de negocio: léelo solo si una historia lo menciona. Lee la historia antes de empezarla y sigue el orden del plan de sprints. Si algo contradice la especificación, avísame antes de continuar. Toda decisión técnica no cubierta va como ADR en docs/adr/NNNN-titulo.md, en inglés.

# Stack obligatorio
- Backend: Python 3.14, FastAPI con un solo proceso Uvicorn, SQLAlchemy 2 async + asyncpg, Alembic, Pydantic v2, uv, Ruff, Mypy (strict), Pytest, Hypothesis, Testcontainers, structlog, time-machine, argon2-cffi, cryptography (AES-GCM y HMAC), Pillow, WeasyPrint, pyotp, import-linter.
- Base de datos: PostgreSQL 17 con Row-Level Security.
- Frontend: Node 24 LTS con pnpm; React 19 + TypeScript (strict) + Vite, TanStack Router, TanStack Query, Tailwind CSS, React Hook Form + Zod, vite-plugin-pwa (instalable y con notificaciones push; sin funcionamiento sin conexión ni caché de `/api`). Tipos del API generados con openapi-typescript. Pruebas con Vitest y Playwright + axe.
- Infra: Docker Compose, Caddy (HTTPS automático con dominio; en local, http://localhost y `tls internal` para probar desde un celular en la red local), Mailpit en local, GitHub Actions, almacenamiento compatible con S3 en un proveedor distinto al del servidor.
- Procesos: `casero.api` (FastAPI) y `casero.worker` (tareas programadas) como procesos separados con el mismo código. Nunca tareas programadas dentro del lifespan de FastAPI.

# Reglas no negociables
1. Dinero en enteros (céntimos de sol, `bigint` / `int` / `number` entero). Solo soles en el MVP; nunca `float`.
2. Tiempo: todo el dominio recibe un `Clock` inyectado con `now()` (UTC) y `today_lima()`; prohibido `datetime.now()` fuera de su implementación y prohibido `CURRENT_DATE` o `now()` en SQL para fechas de negocio: las funciones SQL que necesitan la fecha la reciben como parámetro (`p_today`, `p_now`). La aplicación pone `created_at`; las tablas del libro no tienen `DEFAULT now()`. Un período de alquiler es un mes calendario (`YYYY-MM`).
3. Contextos de acceso a la base, cada uno con su dependencia y su regla AR:
   - `anonymous` (`/api/public/*`: registro, inicio de sesión, recuperación, Libro de Reclamaciones, lista de espera, calculadora pública): solo tablas sin RLS de SPEC.md y lectura de `plans`, `tax_rule_sets` y `sunat_due_dates`. Al registrarse, la app genera el id de la cuenta, ejecuta `set_config('app.account_id', id, true)` y crea cuenta, miembro, aceptaciones legales y suscripción en la misma transacción. La segunda y última excepción es cancelar la eliminación de la cuenta con el enlace del correo, mediante `app_cancel_deletion(p_token_hash, p_now)` con `SECURITY DEFINER`.
   - `account` (`/api/app/*`): la dependencia `current_account` ejecuta `set_config('app.account_id', :id, true)` con parámetro enlazado, nunca con texto interpolado.
   - `tenant` (`/api/tenant/*`): `app_resolve_tenant_token(p_hash, p_today)` con `SECURITY DEFINER` devuelve cuenta y contrato si el enlace está vigente; después, una sola llamada fija `app.account_id`, `app.context = 'tenant'` y `app.lease_id`. Las políticas `RESTRICTIVE` exigen `lease_id = app.lease_id` siempre que `app.context = 'tenant'` (en `renters`, `units` y `properties`, con `EXISTS` sobre el contrato); si falta `app.lease_id`, no se ve ninguna fila.
   - `system` (worker, con su propio rol `casero_worker`): `app_list_account_ids(p_purpose, p_today)` con `SECURITY DEFINER` lista las cuentas para tareas o para purga; luego, una transacción por cuenta. Solo `casero_worker` puede ejecutar `purge_account`.
   - `admin` (`/api/admin/*`): rol `casero_admin` sin `BYPASSRLS`, con políticas `TO casero_admin` solo en `accounts`, `subscriptions` y `subscription_payments` y los permisos por columna de SPEC.md; sin acceso a inquilinos, cobros ni archivos. `/api/admin/*` y `/admin` se sirven en un puerto aparte del mismo proceso, ligado solo a `127.0.0.1` del servidor, y se usan por túnel SSH (`ssh -L`); en el dominio público responden 404.
   Toda tabla del esquema `public` tiene RLS con `FORCE` y políticas `USING` y `WITH CHECK` sobre `account_id = NULLIF(current_setting('app.account_id', true), '')::uuid` (en `accounts`, sobre `id`), salvo la lista cerrada de tablas sin RLS de SPEC.md. Ningún rol que usen la API, el worker o el panel es dueño de las tablas ni tiene `BYPASSRLS`; lo tienen solo `casero_owner` (migraciones y dueño de las funciones `SECURITY DEFINER`, que dependen de ese atributo) y `casero_backup` (respaldos).
4. Libro de solo inserción: `charges`, `charge_voids`, `payments`, `payment_voids`, `deposits`, `deposit_voids`, `deposit_movements`, `deposit_movement_voids`, `lease_rent_changes`, `tax_payments`, `tax_payment_voids`, `legal_acceptances`, `legal_withdrawals`, `reminder_logs`, `audit_log` y `staff_audit_log` no se editan ni se borran; corregir es insertar una fila nueva que referencia a la original. Ningún rol de la aplicación tiene UPDATE ni DELETE sobre ellas. La única excepción es `purge_account()`, que solo ejecuta `casero_worker` y que verifica por sí misma que la eliminación de esa cuenta está vencida.
5. Idempotencia: lo que crea el arrendador (pagos, cargos manuales —ajuste, corrección y saldo anterior—, garantías, devoluciones, cambios de renta y pagos a SUNAT) llega con un `id` uuid v7 generado por el cliente; el POST hace `ON CONFLICT (id) DO NOTHING` y devuelve el existente. Si ese id ya existe con otro contenido o en otra cuenta, responde 409 sin detalle. Las anulaciones son idempotentes por su PK natural: repetirla devuelve 200 y la existente. El resto (`audit_log`, `legal_acceptances`, `legal_withdrawals`, `reminder_logs`, `staff_audit_log` y los cargos `rent` del worker) usa un id generado por el servidor.
6. El impuesto se calcula por declaración (documento del inquilino y mes de cobro) desde los pagos percibidos, con la misma función de aplicación de pagos que calcula los saldos, con tasas, redondeo, umbrales y cronograma leídos de `tax_rule_sets` y `sunat_due_dates`. Los valores viven solo en `infra/seed/tax/{año}.yaml` con su fuente: 2026 se carga en una migración y los años siguientes con `make load-tax-config` (como `casero_owner`, con upsert); el panel solo los muestra. Los tests usan fixtures. Prohibido escribir tasas, fechas o montos de SUNAT (umbral de bancarización, UIT, multas) en el código del dominio o en los textos: los textos usan variables.
7. Nunca pedir, guardar ni transmitir la Clave SOL del usuario, nunca automatizar ni hacer scraping de SUNAT y nunca enviar datos a SUNAT.
8. Datos personales mínimos. Todo campo `*_enc` se cifra con AES-GCM en un sobre `v1:<key_id>:<nonce>:<ciphertext>` (claves fuera de la base; el `key_id` permite rotarlas). El documento del inquilino se guarda además como HMAC de `tipo:número_normalizado` con una clave permanente, documentada como no rotable porque agrupa declaraciones y pagos a SUNAT de solo inserción (si se compromete: migración y ADR). Los logs, los errores enviados al seguimiento y las URL registradas nunca incluyen nombres, documentos, teléfonos, correos, tokens ni montos asociados a una persona.
9. WhatsApp en el MVP: solo enlaces `https://wa.me/` con el mensaje preparado, que el arrendador envía desde su teléfono. Sin API de WhatsApp ni bots.
10. Enlace del inquilino: token = HMAC-SHA256(`TENANT_LINK_KEY`, id del enlace ‖ nonce) en base64url; la base guarda el nonce y el SHA-256 del token, nunca el token. Va en el fragmento (`/i#t=<token>`) y el frontend lo envía en la cabecera `X-Tenant-Token`. `Referrer-Policy: no-referrer` en todo el sitio.
11. Archivos subidos: solo JPG, PNG o PDF de hasta 5 MB (también limitado en Caddy), validados por contenido; las imágenes se vuelven a codificar sin metadatos; bucket privado con versionado y expiración de versiones antiguas a los 30 días; claves `{account_id}/{file_id}`; URLs firmadas de 5 minutos; PDF siempre como descarga.
12. Tareas del worker: las de datos se escriben como "asegurar el estado hasta hoy" y son idempotentes; las de correo se envían como máximo una vez (se registra el envío antes de mandarlo), salvo los recordatorios de impuesto, que reintentan errores transitorios hasta 3 veces en el mismo día. Un solo worker activo con `pg_try_advisory_lock` en una conexión dedicada fuera del pool.
13. Los límites y funciones de cada plan se verifican en el servidor con el servicio `entitlements` y las claves de función de SPEC.md, nunca solo en la interfaz.
14. Configuración por variables de entorno; nunca secretos en el repositorio. `REGISTRATION_MODE` es `closed` por defecto en producción.

# Arquitectura verificable
Las reglas de arquitectura viven en docs/ARCHITECTURE_RULES.md, cada una con un ID (AR-NN) y un test automático en CI.
- No escribas código que rompa una regla AR. Si una historia necesita cambiar una regla, avísame antes.
- Si una historia cambia la arquitectura, actualiza en el mismo PR docs/ARCHITECTURE_RULES.md, sus tests y el ADR correspondiente.
- Un PR con un test de arquitectura en rojo no se fusiona.

# Comentarios en el código
Escribe el código sin comentarios por defecto. Un comentario solo existe si guarda información que el código no puede expresar y cuya ausencia haría que una persona competente entienda mal el código, rompa algo o tenga que buscarla en git o en documentación externa. Antes de escribirlo, intenta que el código lo diga solo (nombre, constante, función, tipo o assert). La historia de un cambio va en el commit o el PR, y las explicaciones para mí van en el chat.
- Permitidos: el porqué de algo que parece un error; restricciones externas (reglas de SUNAT con su fuente, rarezas de APIs, workarounds con link); advertencias e invariantes; referencias cortas a ADR o reglas AR; documentación de la API pública que consume una herramienta; TODOs con issue y acción.
- Prohibidos: repetir el código, historia o changelog, código comentado, separadores decorativos, docstrings que repiten tipos y comentarios dirigidos al revisor.
- Nunca borres directivas de herramientas (type: ignore, noqa, eslint-disable, ts-expect-error, pragmas), cabeceras de licencia ni docstrings que FastAPI usa para OpenAPI.

# Forma de trabajar
1. Antes de cada historia, resume en 3-5 líneas qué harás y qué archivos tocarás; espera mi confirmación.
2. Commits pequeños con Conventional Commits; ramas feat/CS-NN-descripcion; un PR por historia.
3. Explica las decisiones no obvias en el chat o en el PR.
4. Si una tarea supera ~300 líneas, divídela y pregúntame el orden.

# Definición de hecho
- Criterios de aceptación cumplidos y demostrables, cada uno con su test.
- Tests unitarios del dominio, propiedades con Hypothesis donde haya dinero, e integración con PostgreSQL real (Testcontainers).
- CI verde: Ruff, Mypy, Pytest, import-linter, tests de arquitectura, lint, typecheck, Vitest y build del frontend; Playwright cuando existan los escenarios.
- `docker compose up` levanta todo sin pasos manuales.
- SPEC.md, BACKLOG.md, ARCHITECTURE_RULES.md y el contrato OpenAPI actualizados si cambiaron.
- Textos de la interfaz revisados: español claro, sin tecnicismos, legibles en un celular.

# Sprint 0 (cuando te lo indique)
Ejecuta CS-01 y CS-02 en orden, los ADR primero. Antes de empezar, verifica en las fuentes oficiales las versiones vigentes del stack y repórtame cualquiera fuera de soporte.
