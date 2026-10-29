# Casero — Especificación

Negocio y validación: en el repositorio privado `Alesso2805/casero-business`. Historias: docs/BACKLOG.md.

## Visión y problema

Casero (nombre provisional) es una app web para el pequeño arrendador peruano: le dice quién le debe, le ayuda a cobrar sin incomodarse y le deja listo, por cada inquilino, el formulario mensual que debe pagar a SUNAT y su fecha límite. En Perú al arrendador se le dice "casero" o "casera", y ese es el usuario.

**El problema.** Miles de familias complementan su ingreso alquilando un cuarto, un piso de su casa o un minidepartamento. Lo manejan en un cuaderno o en el chat de WhatsApp, y eso les cuesta en tres frentes:

- **Cobros:** no saben con certeza quién está atrasado ni cuánto, y cobrar cara a cara es incómodo.
- **Constancias:** el inquilino pide prueba de lo que pagó y no hay un registro ordenado.
- **Impuesto:** desde 2026 el impuesto por alquiler se paga sobre lo efectivamente cobrado, con un Formulario 1683 por cada inquilino y mes de cobro. Con 4 inquilinos son 4 formularios al mes, y cada uno que se omite puede costar una multa de hasta S/ 2,750.

**La propuesta en una frase.** "Registra tus alquileres una vez; Casero te avisa quién debe, te arma el mensaje de cobro para WhatsApp y te deja listo cada formulario de SUNAT con su fecha."

**Qué no es.** No cobra el alquiler por el arrendador, no presenta declaraciones ni paga en su nombre, nunca pide su Clave SOL y no envía datos a SUNAT. No reemplaza a un contador ni a un abogado.

**Usuarios.**

- **Arrendador** (cliente que paga): persona natural con 1 a 10 contratos de alquiler (cuartos, minidepartamentos, locales pequeños, cocheras), a menudo mayor de 45 años, que usa sobre todo el celular y WhatsApp. El segmento principal es el arrendador con RUC o que quiere formalizarse; el informal puede usar los cobros en el plan gratis.
- **Inquilino** (usuario invitado, gratis): ve su saldo y su historial con un enlace, y puede subir la foto de su voucher de Yape o transferencia.

**Por qué este proyecto para empezar a emprender.** Decide una sola persona, el valor se ve en el primer mes (deudas visibles y formularios listos), el costo de operación es bajo y el stack es el que ya dominas: Python, FastAPI, PostgreSQL y React. No encontramos una app peruana que combine cobros y formularios 1683 por inquilino; los sustitutos reales son el cuaderno, las plantillas de Excel, las calculadoras gratuitas y el contador.

## Marco legal y tributario

Casero calcula e informa; la decisión y el pago ante SUNAT son siempre del arrendador. Esta sección resume las reglas en las que se basa el producto y debe revisarla un contador antes de la beta.

**Impuesto a la renta de primera categoría (alquiler de inmuebles por personas naturales domiciliadas), reglas vigentes desde el 1 de enero de 2026**

| Regla | Qué dice | Cómo la usa Casero |
| --- | --- | --- |
| Base: lo percibido | El pago a cuenta se genera en el mes en que el arrendador cobra, no cuando vence el alquiler (Ley N.° 32430, Ley N.° 32541 y D.S. N.° 012-2026-EF) | El impuesto sale de los pagos registrados con fecha de cobro en ese mes |
| Una declaración por inquilino | Se presenta un Formulario Virtual N.° 1683 por cada inquilino y por cada tipo de bien; varios meses cobrados juntos van en una sola declaración del mes de cobro | Casero arma una declaración por documento del inquilino y mes de cobro, sumando todos sus contratos (en el MVP todo es tipo de bien "predio") |
| Tasa y redondeo | 6.25 % sobre la renta neta (80 % de la bruta): en la práctica, 5 % de lo cobrado. En los ejemplos de SUNAT la base y el tributo se redondean a soles enteros, mitad hacia arriba | Base = redondeo de lo cobrado; tributo = redondeo de la base × 5 %, por declaración. La R.S. N.° 025-2000/SUNAT solo exige enteros en el tributo; el contador confirma antes de la beta si la base también se redondea (`docs/ops/tax-config.md`) |
| Datos del formulario | RUC del arrendador, período (mes de cobro), tipo y número de documento del inquilino, tipo de bien y monto | La guía muestra esos datos listos para copiar en cada declaración |
| Forma de pago | En SUNAT Operaciones en Línea con RUC y Clave SOL (cuenta, tarjeta o Yape), o en bancos y agentes | Casero guía el paso a paso; nunca pide la Clave SOL |
| Vencimiento | Según el cronograma mensual de SUNAT por último dígito del RUC (grupos 0, 1, 2-3, 4-5, 6-7, 8-9 y buenos contribuyentes) | Tabla del cronograma por año; recordatorio 5 días y 1 día antes |
| Multa por no declarar | Hasta 50 % de la UIT por cada declaración omitida (S/ 2,750 con la UIT 2026 de S/ 5,500); con gradualidad, la rebaja puede llegar al 90–100 % si se subsana antes de que SUNAT notifique | Se usa en la ayuda y la comunicación como "hasta {multa_maxima}" (50 % de la UIT del año, de `tax_rule_sets.uit_cents`); Casero no calcula multas ni intereses |
| Declaración anual | Solo es obligatoria con saldo por pagar, pagos en exceso, mejoras no reembolsables, alquiler menor al 6 % del autovalúo o cesión gratuita | Fuera del MVP; la ayuda explica cuándo aplica |
| Renta mínima | El alquiler anual no puede ser menor al 6 % del autovalúo del predio, proporcional a la parte alquilada y a los meses alquilados; si lo es, se tributa sobre ese mínimo en la declaración anual | Si el arrendador registró el autovalúo y la parte que alquila, y el alquiler anualizado queda por debajo, Casero muestra un aviso; no calcula el monto |
| Inquilino empresa | No hay retención: el arrendador paga el mismo 1683 con el RUC del inquilino, y la empresa lo necesita pagado para deducir el gasto | Soportado, con un aviso para pagarlo a tiempo |
| Bancarización | Las obligaciones desde S/ 2,000 o US$ 500 deben pagarse por medios bancarios; el umbral se mide por el monto de la obligación, no de cada pago | Aviso al registrar un pago en efectivo en un contrato con renta igual o mayor que el umbral del año (S/ 2,000 en 2026) |
| Deudas de 2025 o antes | Las rentas hasta diciembre de 2025 se imputaron por lo devengado; cobrarlas después no genera un nuevo pago a cuenta | El saldo anterior se registra en dos importes (hasta 2025 y desde 2026); la parte de un pago aplicada al de 2025 o antes no entra a la base y se marca para revisar con el contador |
| Cambios después de declarar | Si el monto de un mes ya declarado sube, se presenta una rectificatoria del mismo período con el monto total y se paga la diferencia con intereses; una rectificatoria que reduce la deuda queda sujeta a verificación de SUNAT | Casero muestra el texto exacto de qué hacer en cada caso; si el monto baja o hubo una devolución, deriva al contador |
| Titularidad | Cualquier copropietario puede hacer el pago a cuenta del total; en la sociedad conyugal, un cónyuge declara todo si ejerce la opción con el pago de enero, y si no, cada cónyuge declara la mitad; la sucesión indivisa tiene su propio RUC | Soportados: único dueño, copropiedad, sociedad conyugal con opción y sucesión (en una cuenta propia con el RUC de la sucesión). No soportado: sociedad conyugal por mitades. Una cuenta es un declarante con un RUC |

Fuentes: [preguntas y respuestas de SUNAT 2026](https://personas.sunat.gob.pe/sites/default/files/inline-files/RENTAS%20PRIMERA%20CATEG-PREGUNTAS%20Y%20RESPUESTAS-GOS.docx_.pdf), [cartilla de SUNAT](https://cultura.sunat.gob.pe/sites/default/files/2026-01/2025_Cartilla5_IR_PrimeraCategoria_Arrendamientos.pdf), [SUNAT: declaración y pago](https://personas.sunat.gob.pe/alquilo-mi-casa-o-auto/declaracion-pago-0), [SUNAT: preguntas frecuentes](https://personas.sunat.gob.pe/alquilo-mi-casa-o-auto/preguntas-frecuentes), [cronograma 2026](https://www.sunat.gob.pe/orientacion/cronogramas/2026/cObligacionMensual2026.html), [D.S. N.° 012-2026-EF](https://busquedas.elperuano.pe/dispositivo/NL/2484490-2), [UIT 2026](https://elperuano.pe/noticia/285208-mef-establece-en-s-5-500-la-unidad-impositiva-tributaria-para-2026), [R.S. N.° 025-2000/SUNAT (redondeo)](https://www.sunat.gob.pe/legislacion/superin/2000/025.htm), [R.S. N.° 000281-2022/SUNAT (cronograma desde 2023)](https://busquedas.elperuano.pe/dispositivo/NL/2136866-1) (la charla de SUNAT de 2024 con ejemplos de redondeo y multa ya no está publicada), [cartilla de instrucciones para personas (sociedad conyugal)](https://renta.sunat.gob.pe/sites/default/files/inline-files/Cartilla_Instrucciones_Personas.pdf), [BYB Consultores](https://bybconsultores.pe/impuesto-a-la-renta/arrendamiento-justo-pagos-cuenta-ir-2026/) y [bancarización](https://lacamara.pe/operaciones-desde-s-2000-deberan-usar-medio-de-pago/).

**Casos que el MVP no calcula** (la app los marca y muestra el total cobrado, pero no arma la declaración): alquiler en dólares, subarrendamiento, alquiler de bienes muebles, arrendador no domiciliado y sociedad conyugal que declara por mitades (cada cónyuge con su RUC).

**Desalojo y contratos.** La Ley N.° 30933 permite un desalojo con intervención notarial solo si el contrato consta en el Formulario Único de Arrendamiento (FUA) o en escritura pública, e incluye una cláusula de allanamiento a futuro, una de sometimiento expreso a esa ley y una cuenta bancaria para el pago de la renta. Procede por vencimiento del plazo o por falta de pago según lo pactado (si no se pactó, dos meses y quince días), y el notario solo considera los pagos depositados en esa cuenta ([El Peruano](https://busquedas.elperuano.pe/normaslegales/ley-que-regula-el-procedimiento-especial-de-desalojo-con-int-ley-n-30933-1762977-1/)). Casero no genera contratos en el MVP: registra los datos del contrato y muestra una guía informativa con enlaces oficiales.

**Datos personales.** Casero trata los ingresos por alquiler del arrendador, que la Ley N.° 29733 considera datos sensibles, y datos de terceros (nombre, celular y documento del inquilino). Aplican la ley y su reglamento (D.S. N.° 016-2024-JUS, vigente desde el 30 de marzo de 2025). Lo que implica para el producto:

- Solicitud de inscripción del banco de datos ante la Autoridad Nacional de Protección de Datos Personales antes de empezar a tratar datos (semana 1 de la validación), declarando cada proveedor (servidor, respaldos, correo y seguimiento de errores) y su país.
- Al registrarse: aceptación de términos y política de privacidad, y un consentimiento separado y expreso para tratar los ingresos por alquiler; ambos versionados y guardados con fecha. Sin ese consentimiento no se puede crear la cuenta, porque todo Casero trata ingresos por alquiler. Si después se retira, la cuenta queda bloqueada salvo para exportar o eliminar sus datos.
- Términos con cláusula de encargo: el arrendador es responsable de los datos de sus inquilinos y Casero es encargado, con la lista de subencargados (servidor, respaldos, correo y seguimiento de errores) y su país. La política de privacidad menciona que el panel interno no accede a datos de inquilinos ni a cobros.
- Aviso visible en el portal del inquilino: quién registró sus datos, para qué y cómo ejercer sus derechos.
- El documento del inquilino solo es obligatorio para contratos que entran al módulo de impuesto, porque lo exige el Formulario 1683.
- Tú te designas como oficial de datos personales y lo registras en `docs/legal/`.
- Incidentes: aviso a la Autoridad en 48 horas, a los afectados sin demora cuando afecte sus derechos y al Centro Nacional de Seguridad Digital si es un incidente digital ([Pérez-Llorca](https://www.perezllorca.com/es-pe/actualidad/articulos/se-aprueba-nuevo-reglamento-de-la-ley-de-proteccion-de-datos-personales/), [La Cámara](https://lacamara.pe/nuevo-reglamento-refuerza-la-proteccion-de-datos-personales/)).
- Exportación de los datos en formato estructurado y eliminación de la cuenta.
- Si un arrendador persona natural debe inscribir su propio banco de datos de inquilinos es una consulta pendiente para el abogado.
- Los borradores de términos (con el anexo de encargo de tratamiento), la política de privacidad de la aplicación y el consentimiento de datos sensibles están en `docs/legal/`, y las preguntas abiertas para el abogado en `docs/legal/lawyer-questions.md`.

**Tu formalización como emprendedor**

- RUC como persona natural con negocio y régimen tributario elegido con un contador antes de la preventa. Para el primer año conviene evaluar el Nuevo RUS (cuota fija con IGV incluido, solo boletas, tope de S/ 96,000 al año), con paso a RER o Régimen MYPE si te acercas al tope o un cliente necesita factura; el contador confirma que la actividad no está excluida ([comparativo de regímenes](https://tramitesperu.com/comparadores/regimenes-tributarios/)).
- Boletas electrónicas desde el sistema gratuito de SUNAT mientras el volumen sea bajo.
- Libro de Reclamaciones virtual enlazado desde la página de inicio, con la Hoja de Reclamación del Anexo I, copia automática al correo del consumidor, opción de imprimirla y respuesta en un máximo de 15 días hábiles improrrogables por el medio que eligió el consumidor (correo o carta). Solo son obligatorios el nombre, el documento, el correo o el domicilio y el detalle; el teléfono y las casillas de aceptación no se pueden exigir. Se conserva al menos 2 años ([D.S. N.° 011-2011-PCM](https://www.inei.gob.pe/media/libro_reclamaciones/DS011_2011_PCM.pdf), modificado por el [D.S. N.° 006-2014-PCM](https://busquedas.elperuano.pe/dispositivo/NL/1041477-1) y el [D.S. N.° 101-2022-PCM](https://busquedas.elperuano.pe/dispositivo/NL/2095978-1); [Anexo I vigente](https://cdn.www.gob.pe/uploads/document/file/3510113/Anexo%20I%20DS%20N%20101-2022-PCM_.pdf.pdf)). No hay que reportar al SIREC: solo lo exige a proveedores con ingresos desde 3,000 UIT. Se guarda además un libro físico de respaldo en el domicilio fiscal: las preguntas frecuentes de INDECOPI lo piden aunque el art. 4-A lo liga a los establecimientos, y cuesta poco. Si el libro virtual falla, la página pide imprimir la hoja y enviarla al correo de reclamos; ese reclamo se registra dentro del día siguiente a que el libro vuelva a funcionar y su plazo cuenta desde que llegó el correo (`docs/ops/complaints.md`). Se publica el domicilio fiscal; las páginas que lo muestran (`/privacidad`, `/legal` y `/libro-de-reclamaciones`) llevan `X-Robots-Tag: noindex`. Consulta para el abogado: si, al ser la web el establecimiento (art. 3.2), basta con su dirección web en la hoja. Hay un proyecto de reglamento nuevo en consulta desde julio de 2026; se revisa cuando se publique.
- Términos y condiciones que digan claramente que Casero es una herramienta de registro y cálculo, no asesoría tributaria ni legal, y que Casero no entrega información a terceros salvo ante un requerimiento legal obligatorio.

> Nota: esta especificación no es asesoría legal ni tributaria. Las reglas vienen de fuentes públicas consultadas en octubre de 2026 y deben confirmarse con un contador y un abogado antes de cobrar.

## Alcance del MVP y funcionalidades

El MVP cubre el ciclo mensual completo de un arrendador: registrar sus alquileres, saber quién debe, cobrar por WhatsApp, registrar pagos y tener listos sus formularios de SUNAT. Se entrega en dos hitos: la beta privada con los fundadores y el lanzamiento público.

| Módulo | Funcionalidad | Detalle | Hito |
| --- | --- | --- | --- |
| Cuenta | Registro e inicio de sesión | Por invitación durante la beta y abierto desde el lanzamiento; correo y contraseña; se puede usar la app sin verificar el correo hasta 7 días, pero solo se envían correos de verificación hasta hacerlo; recuperación de contraseña; aceptación de términos y privacidad y consentimiento obligatorio de datos sensibles | Beta |
| Cuenta | Perfil tributario | RUC con dígito verificador, grupo del cronograma (último dígito o buen contribuyente); opcional hasta usar el impuesto | Beta |
| Inmuebles | Inmuebles y unidades | Un inmueble tiene unidades (cuarto, minidepartamento, departamento, local, cochera u otro); titularidad, autovalúo y porcentaje alquilado opcionales | Beta |
| Contratos | Alquiler de una unidad | Inquilino, monto mensual, día de pago, inicio, fin previsto, mes desde el que se lleva el control, saldo anterior (de 2025 o antes y de 2026 en adelante) y tratamiento tributario | Beta |
| Contratos | Corregir, renovar y terminar | Anular o corregir un cargo con motivo; cambiar la renta desde el próximo mes; extender o editar el fin previsto (renovación); terminar con fecha y crédito opcional | Beta |
| Cobros | Cargos mensuales | Se generan solos para cada contrato activo; estados atrasado, vence hoy, por vencer, pendiente y pagado | Beta |
| Cobros | Registrar pagos | Monto, fecha de cobro, medio y nota; pagos parciales y adelantados; saldo a favor; anulación con motivo; aviso de bancarización | Beta |
| Cobros | Panel | Atrasados primero con días y monto, luego vence hoy y por vencer; total por cobrar hasta fin de mes (lo pendiente de los cargos que vencen hasta el último día del mes, incluido lo atrasado, que se muestra aparte); también los contratos terminados que aún deben | Beta |
| Recordatorios | Mensajes de cobro | Botón "Enviar por WhatsApp" con el mensaje listo (amable, vence hoy, atraso), editable; registro de cada envío | Beta |
| Portal del inquilino | Enlace personal | Saldo e historial en pantalla, aviso de privacidad; el arrendador lo revoca y regenera | Beta |
| Impuesto | Formularios del mes | Una tarjeta por declaración (documento del inquilino y mes de cobro, sumando sus contratos) con los datos del 1683 listos para copiar, el tributo y el vencimiento; registro del pago con número de orden; qué hacer si el monto cambia después; recordatorio por correo y aviso en la app | Beta |
| Adquisición | Calculadora pública | "¿Cuánto pago a SUNAT por mi alquiler?" sin registro, con una línea por inquilino, conectada a la lista de espera | Beta (desde enero) |
| Legal | Páginas obligatorias | Términos, privacidad, Libro de Reclamaciones virtual, exportación y eliminación de la cuenta | Beta |
| Operación | Respaldos y monitoreo | Respaldos cada 6 horas fuera del servidor, alertas y seguimiento de errores | Beta |
| Suscripción | Planes | Gratis y Casero, prueba de 30 días, límites y funciones por plan; pago por Yape activado desde el panel interno | Lanzamiento |
| Operación | Panel interno | Para ti: cuentas, suscripciones, cronograma de SUNAT, reclamos con su plazo | Lanzamiento |
| Cuenta | Bienvenida guiada | Primer inmueble, unidad, inquilino y saldo anterior en 3 pasos | Lanzamiento |
| Cobros | Constancias y garantías | Constancia en PDF del pago; garantía recibida, aplicada y devuelta | Lanzamiento |
| Portal del inquilino | Vouchers | El inquilino sube la foto; el arrendador la confirma con el monto y la fecha reales o la rechaza | Lanzamiento |
| Recordatorios | Resumen diario y notificaciones | Correo de las 8:00 opcional y notificación push si la app está instalada | Lanzamiento |

**El ciclo de un mes para el arrendador**

1. Cada contrato activo tiene su cargo del mes desde el día 1.
2. Tres días antes del día de pago, el panel marca "por vencer" y sugiere el recordatorio amable; el día de pago marca "vence hoy".
3. El inquilino paga por Yape o en efectivo; el arrendador registra el pago (o, tras el lanzamiento, confirma el voucher que subió el inquilino).
4. Si pasa el día de pago sin pago completo, el cargo pasa a "atrasado" y se sugiere el aviso de atraso.
5. Al cerrar el mes, Casero muestra una declaración por cada inquilino que pagó en ese mes (sumando sus contratos), con su tributo y su vencimiento, y la recuerda 5 días y 1 día antes. La ayuda recomienda presentar el formulario después de cerrar el mes, no apenas se cobra.
6. El arrendador paga cada formulario en SUNAT con la guía y registra su número de orden.

**Fuera del MVP** (en orden de prioridad para después del lanzamiento):

- Recordatorio de vencimiento de SUNAT al arrendador por la API de WhatsApp (plantilla de utilidad aprobada, con consentimiento).
- Prorrateo de servicios (luz y agua) entre cuartos con un solo medidor.
- Cobro de la suscripción con tarjeta y renovación automática.
- Resumen anual para la declaración anual, cuando haya un año completo de datos.
- Alquileres en dólares y sociedad conyugal que declara por mitades.
- Contratos generados con plantilla revisada por un abogado.
- Varios usuarios por cuenta y acceso del contador (base para un plan Plus).
- App móvil nativa y funcionamiento sin conexión.

## Arquitectura y stack

Un monolito modular en Python con dos procesos (API y worker), una PWA en React y un PostgreSQL, en un solo servidor detrás de Caddy. Es lo más simple que una persona puede operar y alcanza para miles de cuentas.

| Componente | Tecnología | Responsabilidad |
| --- | --- | --- |
| `casero.api` | FastAPI, un proceso Uvicorn | API REST bajo `/api`, sesiones, validación, límites por plan, OpenAPI como contrato único; con `ADMIN_ENABLED=true`, un segundo listener solo en `127.0.0.1` para el panel |
| `casero.worker` | Proceso Python con el mismo código y rol `casero_worker` | Asegurar cargos y cierres de contrato hasta hoy, enviar correos programados y las copias de los reclamos, purgar cuentas y archivos vencidos, alertar si falta el cronograma y si un reclamo se acerca a su plazo |
| `web` | React 19, Vite, PWA instalable | `/app` para el arrendador, `/i` para el inquilino, `/admin` para ti (solo por el puerto de administración); landing y calculadora pública en `/` |
| PostgreSQL 17 | RLS por cuenta | Datos, libro de cobros de solo inserción, configuración tributaria por año, auditoría |
| Almacenamiento S3 | Backblaze B2 (US-East), buckets privados | Vouchers con versionado y expiración de versiones antiguas a los 30 días; respaldos cifrados con bloqueo de objetos de 30 días desde la creación del bucket (`docs/ops/storage-buckets.md`) |
| Correo | Amazon SES (us-east-1) detrás de una interfaz `Mailer` | Verificación, recuperación, recordatorios de impuesto y resúmenes; rebotes y quejas por SNS hacia un webhook; Mailpit en local |
| Seguimiento de errores | Sentry (plan gratuito, región EE. UU.) | Excepciones de API, worker y frontend, con filtro que elimina datos personales; el navegador no carga el SDK y envía solo el tipo, la ruta y el lugar del código a `/api/public/client-errors` (ADR-0011) |
| Caddy | Proxy | HTTPS, cabeceras de seguridad, límite de 5 MB por petición, 404 para `/admin` y `/api/admin/*` en el dominio público, `X-Robots-Tag: noindex` en las páginas que muestran el domicilio del negocio, en `/baja` y en `/api/*`, los datos del negocio desde variables de entorno, redirección de `www`, sin registrar `/i` ni consultas |

**Contextos de acceso a la base**

| Contexto | Quién lo usa | Cómo accede |
| --- | --- | --- |
| `anonymous` | Rutas `/api/public/*`: registro, inicio de sesión, recuperación, cancelación de la eliminación, Libro de Reclamaciones, lista de espera, calculadora pública | Solo tablas sin RLS y lectura de la configuración tributaria, con dos excepciones: al registrarse crea cuenta, miembro, aceptaciones y suscripción en una transacción fijando antes `app.account_id` con el id generado, y el enlace de cancelación de la eliminación llama a `app_cancel_deletion(p_token_hash, p_now)` (`SECURITY DEFINER`) |
| `account` | Rutas `/api/app/*` | `current_account` fija `app.account_id` con `set_config(..., true)` dentro de la transacción |
| `tenant` | Rutas `/api/tenant/*` | `app_resolve_tenant_token(p_hash, p_today)` (`SECURITY DEFINER`, propiedad de `casero_owner`, `search_path` fijo) devuelve cuenta y contrato; luego una sola llamada fija `app.account_id`, `app.context = 'tenant'` y `app.lease_id`, y las políticas `RESTRICTIVE` limitan las filas a ese contrato |
| `system` | Worker con el rol `casero_worker` | `app_list_account_ids(p_purpose, p_today)` (`SECURITY DEFINER`, p\_purpose ∈ jobs, purge) y una transacción por cuenta; tablas de sistema sin RLS (`job_runs`, `pending_object_deletions`) |
| `admin` | Rutas `/api/admin/*` | Puerto aparte del mismo proceso, ligado solo a `127.0.0.1` del servidor y usado por túnel SSH, con un pool aparte como `casero_admin` (sin `BYPASSRLS`); ambos se crean solo si `ADMIN_ENABLED=true`; ve filas de cuenta solo por sus políticas en `accounts`, `subscriptions` y `subscription_payments`; sesiones en `staff_sessions`; cada acción queda en `staff_audit_log`; permisos por columna en la tabla de roles |

**Políticas RLS.** Cada tabla de cuenta tiene la política por cuenta (`account_id = NULLIF(current_setting('app.account_id', true), '')::uuid`, en `accounts` sobre `id`). Además:

- Contexto `tenant`: políticas `AS RESTRICTIVE` con `current_setting('app.context', true) IS DISTINCT FROM 'tenant' OR lease_id = NULLIF(current_setting('app.lease_id', true), '')::uuid` (en `leases`, sobre `id`). Las tablas sin `lease_id` usan `EXISTS` sobre su padre (anulaciones, devoluciones de garantía y archivos) o sobre el contrato (`renters`, `units` y `properties`). `accounts` y `subscriptions` siguen visibles mientras el contexto tenga `app.lease_id`, porque el portal necesita el nombre del arrendador y las funciones del plan, pero los endpoints de `/api/tenant/*` solo leen `display_name` y las funciones del plan, mediante un DTO explícito; el resto de tablas de cuenta no se ve en este contexto. Si falta `app.lease_id`, la comparación es nula y no se ve ninguna fila (falla cerrada). Además, políticas `AS RESTRICTIVE` por comando impiden INSERT, UPDATE y DELETE en el contexto `tenant` en todas las tablas de cuenta, salvo el UPDATE de `tenant_links` para `last_used_at`; los vouchers y sus archivos se habilitan con CS-19.
- `casero_admin`: políticas `TO casero_admin` solo en `accounts`, `subscriptions` y `subscription_payments`; en el resto de tablas de cuenta no ve filas aunque se le otorgue un permiso por error.

**Módulos del backend.** Cada uno con capas `domain`, `application`, `infrastructure` y `api`; el dominio no importa FastAPI ni SQLAlchemy. Los módulos siguen un orden acíclico, de abajo hacia arriba: `shared.kernel` → `identity` → `accounts` → `properties` → `leases` → `ledger` → `tax` → `reminders` → `tenant_portal` → `admin`. Un módulo solo importa la capa `application` de los módulos anteriores (contrato `layers` de import-linter) y nunca su `domain`, `infrastructure` ni `api` (contratos `forbidden`). `shared.kernel` (Clock, Money, ids) es puro y lo puede usar cualquier capa; `shared.infrastructure` (contextos de base, Mailer, Storage, crypto) solo se usa desde `infrastructure`, `api` y los puntos de arranque (`casero.api` y `casero.worker`). Un caso de uso que cruza módulos vive en el más alto de ellos: crear un contrato con saldo anterior vive en `ledger.application` y llama a `leases.application`, y `leases` lee las funciones del plan desde `accounts.application`. Si un módulo necesita datos de uno posterior (por ejemplo, `reminders` necesita el enlace vigente de `tenant_portal` para `{enlace}`), declara un puerto en su `application` y los puntos de arranque inyectan la implementación; ese cableado vive solo en `casero/api.py` y `casero/worker.py` (ADR-0001).

| Módulo | Contenido |
| --- | --- |
| `identity` | Usuarios, sesiones, verificación, recuperación, aceptaciones legales |
| `accounts` | Cuenta, registro, perfil tributario, plan, suscripción, `entitlements` (funciones del plan y estado de la suscripción), exportación y eliminación |
| `properties` | Inmuebles y unidades |
| `leases` | Inquilinos y contratos, ciclo de vida |
| `ledger` | Cargos, pagos, garantías, aplicación de pagos, estados, constancias |
| `reminders` | Plantillas, enlaces de WhatsApp, correos y notificaciones push |
| `tax` | Configuración por año, declaraciones mensuales, pagos a SUNAT, calculadora pública |
| `tenant_portal` | Enlaces del inquilino y vouchers |
| `admin` | Personal interno con doble factor, panel, Libro de Reclamaciones |

**Sesiones.** Cookie `__Host-casero_session` httpOnly, Secure, SameSite=Lax, con identificador opaco guardado como hash; se rota al iniciar sesión y dura 30 días deslizantes. Protección CSRF con doble token, también en el formulario de inicio de sesión. El personal interno usa otra cookie (`__Host-casero_staff`, SameSite=Strict, sesión en `staff_sessions` que vence a las 8 horas o tras 30 minutos sin uso) y doble factor TOTP. Sin JWT. Los límites de intentos viven en una tabla `UNLOGGED` de PostgreSQL: bloqueo por IP y retraso progresivo por correo, para que nadie pueda bloquear la cuenta de otra persona.

**Tareas programadas.** El worker revisa cada minuto qué tareas tocan según la hora de Lima. Las tareas de datos (cargos, cierre de contratos vencidos) aseguran el estado hasta hoy: crean lo que falta desde el mes de control de cada contrato, así que se recuperan solas tras una caída. Corren una vez por día de Lima: cada cuenta en su propia transacción, con hasta 3 intentos al día si falla, y una marca del día cuando terminan todas. Las de correo se registran en `job_runs` antes de enviarse y no se reintentan el mismo día, salvo los recordatorios de impuesto, que reintentan hasta 3 veces los errores transitorios; las que tienen hora (resumen de las 8:00) se descartan si a las 12:00 no se pudieron enviar. La purga de una cuenta tiene dos fases: primero se borran sus objetos de S3 (con sus versiones) a través de `pending_object_deletions`, y cuando esa cola está vacía se llama a `purge_account()`.

**Correo.** Amazon SES en us-east-1, con DKIM, un subdominio MAIL FROM propio (SPF) y DMARC. Se envía por SMTP detrás de un puerto `Mailer` en cada módulo (Mailpit en local): los correos programados y las copias de los reclamos, desde el worker; los de la cuenta (verificación y recuperación), durante la petición que crea su token, porque solo la API puede leer `email_tokens` y el token en claro solo existe ahí (ADR-0009). La copia de cada reclamo al consumidor y el aviso al correo de reclamos (`CASERO_COMPLAINTS_INBOX`, sin datos personales, con el estado de la copia) salen en el minuto siguiente a su presentación, como máximo una vez. Los correos programados (resumen diario y recordatorios de impuesto) llevan `List-Unsubscribe` y `List-Unsubscribe-Post` de un clic, que dan de baja solo ese tipo de correo: el enlace lleva a `/baja` (pide confirmar) y el encabezado a `POST /api/public/unsubscribe`, ambos con un token HMAC de `CASERO_UNSUBSCRIBE_KEY` sobre el usuario y el tipo de correo. Los rebotes y las quejas llegan por SNS a `POST /api/public/email-events`, que solo acepta el tema configurado y firmas SHA-256 verificadas con el certificado de SNS, y alimentan `email_suppressions` (ADR-0010; pasos en `docs/ops/email.md`): una dirección que rebota o se queja deja de recibir todo correo. Una baja nunca suprime los correos transaccionales, y se deshace desde Mis datos con la casilla "Recibir los recordatorios de SUNAT por correo", que borra solo la baja de ese usuario y ese tipo de correo.

**Despliegue y respaldos.** Un servidor virtual de Google Cloud con Docker Compose (Caddy con la web compilada, API, worker, PostgreSQL; `infra/deploy/`), imágenes construidas en GitHub Actions, publicadas en GHCR y desplegadas por SSH al fusionar en `main`. Respaldo con `pg_dump` cada 6 horas, cifrado y enviado a otro proveedor; prueba de restauración mensual partiendo solo de Bitwarden, donde viven las claves. Monitor externo (Better Stack) de `/api/health`, con heartbeats que avisan si un respaldo no llegó o si el disco supera el 80 % (`docs/ops/backups.md`). Ni Caddy ni Uvicorn (`--no-access-log`) registran las peticiones, así que las IP y los tokens de las URL no quedan en ningún registro.

**Proveedores.** Precios y capacidades verificados el 25 de octubre de 2026. Todos guardan datos fuera del Perú, así que cada uno se declara ante la Autoridad como flujo transfronterizo.

| Servicio | Proveedor y plan | País de los datos |
| --- | --- | --- |
| Servidor | Google Cloud Compute Engine e2-small (2 GB) en us-east1, con IP estática en el nivel Standard (`docs/ops/server.md`) | EE. UU. |
| Dominio | Un dominio .com propio para la web y el correo de SES (DKIM, MAIL FROM y DMARC), con privacidad del WHOIS; el registrador solo resuelve el nombre y no trata datos personales (`docs/ops/server.md`) | — |
| Correo de reclamos y de privacidad | Una cuenta de Gmail exclusiva de Casero: `CASERO_COMPLAINTS_INBOX` recibe los avisos de reclamos, es el Reply-To de cada copia y el respaldo si el libro virtual falla; `CASERO_PRIVACY_INBOX` es el canal para ejercer los derechos sobre los datos personales y puede ser la misma cuenta | EE. UU. |
| Vouchers y respaldos | Backblaze B2, región US-East, con un bucket para cada uso (`docs/ops/storage-buckets.md`) | EE. UU. |
| Correo | Amazon SES, región us-east-1; rebotes y quejas por SNS | EE. UU. |
| Seguimiento de errores | Sentry, plan gratuito, región EE. UU. | EE. UU. |
| Monitor externo | Better Stack, plan gratuito: disponibilidad de `/api/health` y heartbeats de respaldos y disco; no recibe datos personales (`docs/ops/backups.md`) | — |

La web y el correo comparten el dominio desde antes de publicar la landing: los enlaces del inquilino, la PWA instalada, las suscripciones push y la solicitud de producción de SES quedan atados al dominio, y un subdominio de DNS dinámico tiene peor reputación y no permite los registros que pide SES. DuckDNS se descartó por eso el 26 de octubre de 2026, antes de publicar nada en él.

## Reglas de negocio

El saldo de un contrato es siempre Σ cargos válidos (los ajustes llevan signo) − Σ pagos válidos, y el tributo de cada declaración es siempre la regla del año aplicada a lo cobrado a un mismo inquilino (por su documento) en ese mes, sumando todos sus contratos. Todo lo demás se deriva de esas dos reglas y se calcula al leer.

**Contratos**

| Regla | Detalle |
| --- | --- |
| Activo | Un contrato está activo mientras `ended_at` es nulo. `end_date` es la fecha prevista: el panel avisa 15 días antes, el arrendador puede extenderla o quitarla mientras el contrato esté activo (renovación), y si pasa sin renovación el worker cierra el contrato con `ended_at = end_date` |
| Un contrato activo por unidad | Índice único parcial sobre la unidad donde `ended_at` es nulo |
| Mes de control | Si el inicio está en el pasado, el arrendador elige desde qué mes lleva el control (por defecto el actual), entre el mes de inicio y el actual y nunca antes de enero de 2026; si el inicio es futuro, el control empieza en el mes de inicio. No se generan cargos anteriores; la deuda previa va como saldo anterior |
| Saldo anterior | Hasta dos cargos `opening_balance` válidos por contrato, uno por era (`pre_2026`), verificado bajo el bloqueo del contrato; uno equivocado se anula y se registra de nuevo: uno con la deuda de 2025 o antes y otro con la de 2026 anterior al mes de control (solo si el control empieza después de enero de 2026). El de 2025 o antes se aplica primero. Ya están vencidos: el de 2025 o antes vence el 31 de diciembre de 2025 y el de 2026, el día anterior al mes de control |
| Cambio de renta | Se registra en `lease_rent_changes` con el monto nuevo y el período desde el que aplica (el siguiente que no se haya generado); los cargos ya generados no cambian y se corrigen con `rent_correction` si hace falta |
| Último mes | Se cobra completo todo período cuyo primer día sea anterior o igual al fin del contrato. Un crédito proporcional se registra a mano como ajuste, o al terminarlo. Terminar un contrato se hace con una fecha entre el mes de control y hoy; los cargos de los períodos que empiezan después se anulan con el motivo "Contrato terminado". Un contrato registrado por adelantado que todavía no empieza se termina con la fecha de hoy: se anulan todas sus rentas y lo cobrado queda "a devolver". Para terminarlo en el futuro se cambia la fecha prevista |
| Tratamiento tributario | `standard` (persona natural), `company_tenant` (inquilino empresa) o `unsupported` (casos fuera del MVP). Solo los dos primeros entran a las declaraciones |
| Titularidad | En el inmueble: `sole` (único dueño), `co_owned` (un copropietario declara y paga el total), `conjugal_option` (un cónyuge declara todo por la sociedad conyugal, opción ejercida con el pago de enero), `conjugal_split` (cada cónyuge declara su mitad) o `estate` (sucesión indivisa). `conjugal_split` fuerza `unsupported` en sus contratos y la app explica por qué; la titularidad no cambia hacia o desde `conjugal_split` mientras el inmueble tenga un contrato activo |
| Un declarante por cuenta | Las declaraciones salen con el RUC de la cuenta, así que una cuenta es un solo declarante (`accounts.taxpayer_kind` ∈ person, estate). En una cuenta `estate` todos los inmuebles son `estate`; en una cuenta `person`, `estate` no se puede elegir y la app explica que la sucesión necesita su propia cuenta con su RUC. El tipo de declarante solo cambia mientras la cuenta no tiene inmuebles, archivados incluidos. Al elegir `conjugal_option`, la app pide confirmar que el RUC de la cuenta es el del cónyuge que ejerció la opción |

**Cargos**

| Regla | Detalle |
| --- | --- |
| Tipos | `rent` (mensual), `rent_correction` (reemplaza un `rent` anulado del mismo período), `opening_balance` y `adjustment` (débito si es positivo, crédito si es negativo; nunca cero) |
| Ajustes negativos | Un crédito tiene como fecha efectiva la fecha en Lima en que se registra y se aplica junto con los pagos, en orden de fecha y después de los pagos de su misma fecha (ver Aplicación). No es dinero cobrado: nunca entra a la base del impuesto |
| Generación | Un `rent` por contrato y período, único por `(lease_id, period)`. El worker asegura cada día que existan todos los períodos desde el mes de control hasta el actual (o hasta el del fin del contrato); al crear un contrato se generan en el acto sus cargos hasta hoy, con la misma función; un período con un `rent` anulado no se vuelve a generar |
| Corrección | Anular el cargo con motivo e insertar un `rent_correction` del mismo período |
| Vencimiento | El día de pago del contrato; si el mes no tiene ese día, el último día del mes; en el primer período, nunca antes de la fecha de inicio |
| Estado | Con este orden de precedencia: pagado (saldo del cargo ≤ 0), atrasado (hoy > vencimiento), vence hoy, por vencer (faltan 3 días o menos) y pendiente. "Parcial" es un atributo aparte cuando hay algo pagado. Un contrato está "al día" si no tiene cargos atrasados |

**Pagos**

| Regla | Detalle |
| --- | --- |
| Aplicación | Los movimientos (pagos y créditos) se aplican juntos, ordenados por fecha efectiva: la de un pago es `received_on` y la de un crédito, la fecha en Lima de su `created_at`. En una misma fecha van primero todos los pagos y después todos los créditos, y dentro de cada grupo se ordena por `(created_at, id)`. Cada movimiento cubre lo que dejaron pendiente los anteriores en los cargos válidos con monto positivo, ordenados con el saldo anterior de 2025 o antes primero, luego el de 2026, luego por vencimiento, fecha de creación e id; así, un movimiento solo afecta la asignación de los posteriores. Lo que sobra queda como saldo a favor y se aplica a los cargos siguientes. El cálculo es determinista: el mismo conjunto de movimientos da siempre la misma asignación, y el saldo de cada cargo y el tributo no dependen del orden de inserción |
| Fecha de cobro | La fecha en que el arrendador recibió el dinero; no puede ser posterior a hoy en Lima ni anterior al 1 de enero de 2026. Si es anterior al primer día del mes de control (por ejemplo, el primer mes pagado al firmar un contrato que empieza después), se acepta con un aviso, porque el pago cuenta para el impuesto del mes en que se cobró. Es la que usa el impuesto |
| Idempotencia | El cliente genera el id (uuid v7) al abrir el formulario de lo que crea el arrendador: contratos (que se crean con su primera renta y sus saldos anteriores), pagos, cargos manuales (ajuste, corrección y saldo anterior), garantías, devoluciones, cambios de renta y pagos a SUNAT. Reenviar devuelve el existente; un id que ya existe con otro contenido o en otra cuenta responde 409 sin detalle. Las anulaciones son idempotentes por su PK natural (repetirla devuelve 200 y la existente) |
| Pagos adelantados | Cuentan para el impuesto del mes en que se cobraron, aunque cubran meses siguientes |
| Anulación | Se registra con motivo. Si anular un pago o un cargo cambia lo gravado de un mes que ya tiene un pago a SUNAT registrado del mismo inquilino (el mes del pago, o uno posterior cuando cambia cuánto toma la deuda de 2025 o antes), Casero avisa: "Ya registraste un pago a SUNAT de {periodo}. Con esta anulación, lo que declaraste ya no coincide: revisa la tarjeta de ese mes en Formularios de SUNAT." (con varios meses: "Ya registraste pagos a SUNAT de {periodos}. Con esta anulación, lo que declaraste ya no coincide: revisa las tarjetas de esos meses en Formularios de SUNAT.") |
| Bancarización | Si la renta vigente en el período de la fecha de cobro es igual o mayor que el umbral del año (`cash_threshold_cents`; S/ 2,000 en 2026), registrar un pago en efectivo muestra: "Para alquileres desde {umbral} la ley exige pagar por banco, transferencia o billetera. Sin eso tu inquilino no puede deducir el gasto y te será más difícil probar cuándo cobraste" |
| Saldo a favor al terminar | Se muestra como "a devolver al inquilino"; la devolución se registra como un ajuste |

**Garantías**

| Regla | Detalle |
| --- | --- |
| Registro | Garantía recibida por contrato; no es renta |
| Aplicar a alquiler | Crea un pago con medio "garantía" y `deposit_id`, en la fecha en que se aplica; desde ahí cuenta para el impuesto. Lo aplicado es la suma de esos pagos válidos |
| Devolver | Se registra en `deposit_movements` (solo devoluciones) |
| Anulación | Una garantía se anula en `deposit_voids` solo si no tiene pagos ni devoluciones válidos; una devolución, en `deposit_movement_voids`; un pago desde la garantía, como cualquier pago |
| Disponible | Recibido − aplicado − devuelto, calculado al leer y verificado bajo bloqueo de la fila del contrato; no se puede aplicar ni devolver más que lo disponible |

**Vouchers del inquilino.** Quedan "por confirmar" y no cuentan como pago. El arrendador los confirma indicando el monto y la fecha que realmente recibió (eso crea el pago una sola vez) o los rechaza con motivo. Máximo 3 pendientes por contrato y 10 subidas por enlace al día.

**Declaraciones del impuesto**

```latex
\text{base}(d, m) = \text{redondeo}\left(\sum \text{pagos válidos gravados de los contratos del inquilino con documento } d \text{ cobrados en el mes } m\right)
```

```latex
\text{tributo}(d, m) = \text{redondeo}\left(0.80 \times 0.0625 \times \text{base}(d, m)\right)
```

- Hay una declaración por cada documento de inquilino (`renter_doc_hmac`; si el inquilino no tiene documento, por `renter_id`, y la tarjeta queda "incompleta" sin permitir registrar el pago a SUNAT hasta completarlo) con pagos cobrados en el mes en contratos `standard` o `company_tenant`; si un mismo inquilino tiene dos contratos, se suman. El total del mes es la suma de sus tributos. Ejemplo de prueba: 450.50 + 100.50 en dos contratos del mismo inquilino dan base 551 y tributo 28.
- El redondeo es al sol entero, mitad hacia arriba, primero en la base y luego en el tributo. Tasa, deducción, redondeo, umbral de bancarización y UIT se leen de `tax_rule_sets` del año del mes de cobro.
- De la base se excluye la parte de un pago que la aplicación asigna al saldo anterior de 2025 o antes (ya gravado por devengado); esa parte se muestra aparte para revisar con el contador. Pruebas de propiedades con Hypothesis verifican que el tributo no depende del orden en que se insertaron los movimientos (permutando el `created_at` dentro de cada día) y que un crédito no cambia la base de ningún mes anterior a su fecha.
- Caso para validar con el contador: un crédito registrado después de pagos que cubrieron deuda de 2025 o antes no cambia la asignación de esos pagos ni la base de sus meses; solo afecta a los movimientos posteriores a su fecha.
- Cada tarjeta muestra los datos del 1683: RUC del arrendador, período, tipo y número de documento del inquilino (descifrado solo en esa vista y en la exportación para el contador), tipo de bien "predio", base y tributo, con botones para copiar. Sin documento del inquilino, la tarjeta pide completarlo.
- El vencimiento sale de `sunat_due_dates` según el año, el mes y el grupo del RUC. Si el cronograma del año no está cargado, se muestra "fecha por confirmar" y el worker te alerta por correo.
- Sin RUC registrado, Casero muestra el tributo pero no el vencimiento, y explica cómo obtener el RUC.
- La exportación para el contador (función `accountant_export`) entrega dos CSV del año: los cobros válidos (con la parte de deuda de 2025 o antes, el monto gravado y si entra al 1683) y las declaraciones de cada mes hasta el actual (base, tributo, pagado, pendiente, vencimiento y números de orden). Llevan el número de documento completo, porque el contador lo necesita para el 1683; son UTF-8 con BOM, separados por comas y con punto decimal, y una celda que una hoja de cálculo tomaría como fórmula empieza con un apóstrofo.
- El pago a SUNAT se registra por declaración (documento del inquilino y período), con fecha, monto, número de orden y el monto declarado (la base), que el formulario trae con la base de la tarjeta y el arrendador confirma o corrige: un cobro registrado entre la presentación y el registro del pago debe verse como cobrado después de declarar. Lo pendiente de una declaración es su tributo menos los pagos registrados.
- Si la declaración cambia después de registrar el pago, Casero lo señala sin bloquear, con estos textos. Compara la base actual con la del último pago registrado de esa declaración (`base_cents`, porque una rectificatoria declara el mes completo): si es mayor, sube, con {diferencia} = base actual − base declarada y {tributo_diferencia} = tributo actual − lo pagado; si es menor, baja. Si se anulan todos los cobros del mes, la tarjeta sigue con base cero para mostrar que bajó. El documento cambiado se detecta cuando un pago válido de ese inquilino y mes tiene otro `renter_doc_hmac`:
  - Sube con un cobro registrado después del último pago a SUNAT: "Cobraste S/ {diferencia} más en {periodo} después de declarar. Presenta una declaración rectificatoria del 1683 con la nueva base y paga la diferencia de S/ {tributo_diferencia} con intereses. Consúltalo con tu contador."
  - Sube sin un cobro registrado después del último pago a SUNAT (por ejemplo, porque se anuló una deuda de 2025 o antes o un descuento): "La base de {periodo} subió después de declarar. Presenta una rectificatoria del 1683 con la nueva base y paga la diferencia de S/ {tributo_diferencia} con intereses. Consúltalo con tu contador."
  - Baja (pago anulado): "La base de {periodo} bajó después de declarar. Una rectificatoria que reduce el tributo la revisa SUNAT antes de surtir efecto; consulta con tu contador si conviene presentarla o pedir la devolución."
  - Documento del inquilino cambiado después de pagar: "Esta declaración se pagó con otro documento del inquilino. Ese dato no se corrige con una rectificatoria sino con el Formulario 1693 (solicitud de modificación de datos del pago). Revísalo con tu contador." Lo pagado con el documento anterior cuenta como pagado en la tarjeta (salvo que ese documento sea ahora el de otro inquilino con declaración en el mes), así que la declaración no queda pendiente ni sale en el recordatorio por correo: no se paga dos veces.
  - Vencida sin pago registrado (por ejemplo, un cobro registrado con fecha pasada): "Esta declaración venció el {vencimiento}. Si la presentas y pagas antes de que SUNAT te notifique, la multa tiene una rebaja importante por gradualidad, y se pagan intereses. Consúltalo con tu contador."
- Si el arrendador registró el autovalúo y el porcentaje alquilado (`rented_share_pct`, 100 por defecto) de un inmueble, y el alquiler de sus unidades en los meses alquilados queda por debajo del 6 % del autovalúo × porcentaje alquilado × meses alquilados / 12, se muestra el aviso de renta mínima. El alquiler es la renta pactada, no lo cobrado: los cargos de renta válidos (o la corrección que reemplazó a uno) de los contratos `standard` y `company_tenant` de sus unidades, desde enero hasta el mes que se muestra; los meses alquilados son los que tienen alguno de esos cargos, así que los meses anteriores al mes de control no cuentan. El aviso solo nombra el inmueble; Casero no calcula la diferencia.

**Mensajes de cobro.** Tres plantillas editables por cuenta, con variables `{inquilino}`, `{monto}`, `{periodo}`, `{fecha}` y `{enlace}`:

- Recordatorio amable: "Hola {inquilino}, te recuerdo que el {fecha} vence el alquiler de {periodo} por {monto}. Puedes ver tu detalle aquí: {enlace}. ¡Gracias!"
- Vence hoy: "Hola {inquilino}, hoy vence el alquiler de {periodo} por {monto}. Tu detalle está aquí: {enlace}."
- Atraso: "Hola {inquilino}, el alquiler de {periodo} por {monto} está pendiente desde el {fecha}. ¿Me confirmas cuándo podrías pagarlo? Tu detalle: {enlace}."

`{enlace}` siempre es el mismo enlace vigente del contrato, así que los mensajes ya enviados siguen funcionando; si el contrato aún no tiene enlace, Casero lo crea al preparar el mensaje (solo si la plantilla usa `{enlace}`). El mensaje es del alquiler impago más antiguo del contrato (renta o su corrección; los saldos anteriores no se recuerdan por WhatsApp), con lo que falta pagar de ese mes, y la plantilla sale de su estado: atraso si está atrasado, vence hoy si vence hoy y recordatorio amable en otro caso. Sin celular del inquilino, WhatsApp pide elegir el chat. La ayuda recomienda enviar entre las 8:00 y las 20:00. Cada envío queda registrado para mostrar "recordado hace N días".

**Recordatorios de impuesto.** Por correo 5 días y 1 día antes del vencimiento, con aviso fijo en la app los últimos 5 días; tras el lanzamiento, también por notificación push si la app está instalada. Estos recordatorios no dependen del resumen diario y salen desde las 8:00 de Lima; si el envío falla, se intenta hasta 3 veces en el día, con una hora entre intentos. Si el worker no pudo enviar el primero 5 días antes, lo envía el primer día que pueda, hasta 2 días antes del vencimiento. Si la declaración no tiene documento del inquilino, el correo pide completarlo. Es un correo por cuenta y día al dueño de la cuenta, solo con su correo confirmado, que lista las declaraciones del mes con algo pendiente (nombre del inquilino y monto, nunca su documento); cada declaración incluida queda en `reminder_logs`. El worker agrupa por `doc_hmac` sin descifrar documentos, así que no recibe las claves de cifrado.

**Planes, funciones y límites**

| Clave de función | Gratis | Casero |
| --- | --- | --- |
| Contratos activos | 1 | 10 |
| `whatsapp_links` | Sí | Sí |
| `tenant_portal` | Sí | Sí |
| `tax_module` (declaraciones y registro de pagos a SUNAT) | No | Sí |
| `tax_reminders` | No | Sí |
| `receipts_pdf` | No | Sí |
| `accountant_export` (CSV de pagos y declaraciones) | No | Sí |
| `data_export` (portabilidad legal) | Sí | Sí |

| Regla | Detalle |
| --- | --- |
| Estado de la suscripción | Se calcula desde fechas: en prueba, activa, en gracia (7 días tras vencer) o gratis |
| Al superar el límite | No se pueden crear contratos nuevos. El límite se verifica bloqueando la fila de la cuenta para evitar altas simultáneas |
| Al bajar de plan | El arrendador elige qué contratos conservan WhatsApp y portal hasta el límite (por defecto, los más antiguos). Los demás siguen generando cargos y aceptando pagos, pero sin esas funciones hasta que se termine otro contrato o se vuelva a pagar |
| Meses pagados | Los meses de la prueba gratis no cuentan como pagados; al terminar la prueba se envía un único correo y un aviso en la app con los vencimientos de SUNAT pendientes. Las declaraciones de meses de cobro dentro de un período pagado conservan su tarjeta y sus recordatorios aunque la suscripción venza después |
| Datos | Nunca se borran por bajar de plan; la exportación legal siempre está disponible |

## Esquema de base de datos

PostgreSQL 17 con cuatro grupos de tablas: identidad y personal interno, configuración global, sistema, y datos de cada arrendador con RLS por `account_id`. Las claves primarias son `uuid` v7 generados en la aplicación, o en el cliente para lo que crea el arrendador (ver Idempotencia en Pagos). Cada tabla de cuenta con `id` tiene `UNIQUE (account_id, id)` y las foráneas entre ellas son compuestas `(account_id, x_id)`, para que ninguna fila apunte a otra cuenta; las tablas de anulación usan como PK la clave del registro anulado y una FK compuesta `(account_id, x_id)` hacia él. La aplicación pone `created_at`; las tablas del libro no tienen `DEFAULT now()`. Los planes se cargan en una migración de datos (CS-03). La configuración tributaria, el cronograma de SUNAT y los feriados tienen una sola fuente, los YAML de `infra/seed/tax/`: el año 2026 se carga en una migración (CS-20) y los siguientes con `make load-tax-config`, que corre como `casero_owner`, hace upsert y también lo ejecuta el migrador al arrancar. Es idempotente y falla si a un YAML le falta `source_url`. El panel interno solo los muestra.

**Tablas sin RLS (lista cerrada; el test de CS-03 falla si aparece otra):** `users`, `sessions`, `email_tokens`, `registration_invites`, `account_members`, `legal_documents`, `staff_users`, `staff_sessions`, `staff_audit_log`, `plans`, `tax_rule_sets`, `sunat_due_dates`, `holidays`, `complaints`, `complaint_counters`, `waitlist_entries`, `email_suppressions`, `rate_limit_buckets`, `job_runs`, `pending_object_deletions` y la tabla de versiones de Alembic. Todas las demás del esquema `public` tienen RLS con `FORCE`.

**Roles.** Esta tabla es exhaustiva: un permiso que no aparece aquí no existe, y un test de catálogo lo compara con `information_schema`.

| Rol | Uso | Permisos |
| --- | --- | --- |
| `casero_owner` | Migraciones, `make create-staff`, `make load-tax-config` y dueño de los objetos y de las funciones `SECURITY DEFINER` | Todo, con `BYPASSRLS` (necesario porque `FORCE` también somete al dueño a las políticas). Las funciones `SECURITY DEFINER` fijan `search_path`, validan sus argumentos y reciben la fecha como parámetro; `purge_account` además fija `app.account_id` al inicio |
| `casero_backup` | Solo `pg_dump` | `LOGIN`, `BYPASSRLS`, SELECT en todo; sin escritura |
| `casero_app` | API (contextos `anonymous`, `account` y `tenant`) | Sin `BYPASSRLS`. Tablas de cuenta: SELECT e INSERT; UPDATE solo en las tablas con estado editable (`accounts`, `properties`, `units`, `renters`, `leases(end_date, ended_at, due_day, tools_enabled, tax_treatment)`, `voucher_submissions(status, reject_reason, payment_id, reviewed_by, reviewed_at)`, `tenant_links(revoked_at, last_used_at)`, `message_templates`, `push_subscriptions(revoked_at)`, `subscriptions(ends_at, ended_at)`); nada de UPDATE ni DELETE en las de solo inserción, por eso los bloqueos se hacen sobre la fila del contrato (`SELECT ... FROM leases ... FOR UPDATE`) o de la cuenta, nunca sobre una tabla de solo inserción. Sin RLS: CRUD en `users`, `sessions`, `email_tokens`, `account_members`, `rate_limit_buckets`; SELECT y UPDATE(`used_at`) en `registration_invites`; SELECT en `plans`, `tax_rule_sets`, `sunat_due_dates`, `holidays`, `legal_documents`; INSERT en `complaints`; INSERT, SELECT(`email`) y DELETE en `waitlist_entries` (DELETE al registrarse); SELECT, INSERT y UPDATE en `complaint_counters`; SELECT, INSERT y DELETE en `email_suppressions` (webhook de rebotes, baja de un clic y volver a recibir los recordatorios desde Mis datos; el DELETE solo borra la baja del propio usuario para ese tipo de correo, nunca un rebote ni una queja). EXECUTE en `app_resolve_tenant_token` y `app_cancel_deletion`. No tiene EXECUTE en `app_list_account_ids` ni en `purge_account`: un test verifica que recibe "permission denied" |
| `casero_worker` | Worker (contexto `system`) | Sin `BYPASSRLS`. Lo mismo que `casero_app` sobre tablas de cuenta (actúa una cuenta a la vez con `app.account_id`), más UPDATE(`purged_at`) en `files`; SELECT en `users(id, email, email_verified_at, deleted_at)`, `account_members`, `plans`, `tax_rule_sets`, `sunat_due_dates`, `complaints`, `holidays`, `waitlist_entries`; DELETE en `waitlist_entries` (vencidas) y en `rate_limit_buckets` (filas de más de 24 horas), con SELECT(`window_start`) en `rate_limit_buckets` para filtrarlas; CRUD en `job_runs`, `pending_object_deletions`, `email_suppressions`; EXECUTE en `app_list_account_ids` y `purge_account` |
| `casero_admin` | Panel interno y comandos `make` de personal | Sin `BYPASSRLS`; políticas RLS `TO casero_admin` solo en `accounts`, `subscriptions` y `subscription_payments`. SELECT en `accounts(id, display_name, created_at, deletion_requested_at, purged_at)`, `subscriptions`, `subscription_payments`, `account_members`, `users(id, email, created_at, email_verified_at)`, `complaints`, `job_runs`, `waitlist_entries`, `registration_invites`, `plans`, `tax_rule_sets`, `sunat_due_dates`, `holidays`; INSERT en `subscriptions`, `subscription_payments`, `registration_invites`, `staff_sessions`, `staff_audit_log`; UPDATE en `complaints(response, responded_at)`, `subscriptions(ends_at, ended_at, founder)`, `staff_sessions(revoked_at, last_seen_at)`, `staff_users(recovery_codes_hash)`; SELECT en `staff_users` y `staff_sessions`. Nada sobre inquilinos, contratos, cobros, garantías ni archivos, y solo lectura de la configuración tributaria |

### Identidad, legal y personal interno (sin RLS)

| Tabla | Columnas principales | Restricciones clave |
| --- | --- | --- |
| `users` | id, email, password\_hash, email\_verified\_at, created\_at, deleted\_at | `email` único sin distinguir mayúsculas; al pedir la eliminación se anonimiza como `deleted+<id>@invalid`; hash Argon2id |
| `sessions` | id, user\_id, token\_hash, created\_at, last\_seen\_at, expires\_at, revoked\_at | `token_hash` único |
| `email_tokens` | id, user\_id, purpose, token\_hash, expires\_at, used\_at | purpose ∈ verify\_email, reset\_password, cancel\_deletion; un solo uso. Los enlaces de baja no usan esta tabla: son tokens firmados con HMAC (usuario, tipo de correo), reutilizables y sin guardar, para que los filtros de correo que abren enlaces no los consuman |
| `registration_invites` | id, email, token\_hash, created\_by\_staff\_id, expires\_at, used\_at | Se crean con `make invite` (con `created_by_staff_id` nulo si se crean antes de que exista personal); un solo uso; solo se exigen si `REGISTRATION_MODE=invite` (con `closed` el registro devuelve 403, con `open` no se piden) |
| `account_members` | account\_id, user\_id, role | PK `(account_id, user_id)`; un usuario por cuenta y una cuenta por usuario en el MVP (`account_id` y `user_id` únicos), role = owner |
| `legal_documents` | id, kind, version, published\_at, url | kind ∈ terms, privacy, sensitive\_consent |
| `staff_users` | id, email, password\_hash, totp\_secret\_enc, recovery\_codes\_hash `text[]`, created\_at, disabled\_at | Se crean solo con `make create-staff` (corre como `casero_owner`), nunca por HTTP; cada código de recuperación se usa una sola vez (se quita del arreglo) |
| `staff_sessions` | id, staff\_user\_id, token\_hash, created\_at, last\_seen\_at, expires\_at, revoked\_at | Cookie `__Host-casero_staff`; vence a las 8 horas o 30 minutos sin uso |
| `staff_audit_log` | id, staff\_user\_id, actor, action, entity, entity\_id, at | Solo inserción; actor ∈ panel, cli; `staff_user_id` nulo solo con `actor = 'cli'`, para comandos ejecutados antes de que exista personal; registra cada acción del panel y de los comandos `make` de personal |

### Configuración y sistema (sin RLS)

| Tabla | Columnas principales | Restricciones clave |
| --- | --- | --- |
| `plans` | code, name, price\_month\_cents, price\_year\_cents, max\_active\_leases, features `jsonb` | code ∈ free, casero; features con las claves de la tabla de funciones; se cargan en migración |
| `tax_rule_sets` | year, rate\_bp, deduction\_bp, rounding, cash\_threshold\_cents, min\_rent\_bp, uit\_cents, source\_url | PK `year`; 2026: rate\_bp = 625, deduction\_bp = 2000, rounding = half\_up\_sol, cash\_threshold\_cents = 200000, min\_rent\_bp = 600, uit\_cents = 550000; solo se escribe desde los YAML de `infra/seed/tax/` |
| `sunat_due_dates` | year, period, ruc\_group, due\_date, source\_url | PK `(year, period, ruc_group)`; `year` es el año del período declarado (diciembre de 2026 está en 2026 aunque venza en enero de 2027); ruc\_group ∈ 0, 1, 2-3, 4-5, 6-7, 8-9, bc |
| `holidays` | date, name | Feriados nacionales; se usan para los 15 días hábiles del Libro de Reclamaciones |
| `complaints` | id, number, created\_at, full\_name, document\_type, document\_number, address, email, phone, guardian\_name, guardian\_address, guardian\_phone, guardian\_email, item\_kind, claimed\_amount\_cents, item\_description, kind, detail, request, response\_channel, response, responded\_at, due\_at | Libro de Reclamaciones con los campos de la Hoja del Anexo I; kind ∈ claim (reclamo), complaint (queja); document\_type ∈ dni, ce, passport; item\_kind ∈ product, service; response\_channel ∈ email (exige email), letter (exige address); los datos del padre, madre o representante solo con guardian\_name (consumidor menor de edad); number = `NNNNNNNNN-AAAA` como en el Anexo I, con el año de la fecha en Lima, tomado de `complaint_counters` en la misma transacción; due\_at = 15 días hábiles contados desde el día hábil siguiente, sin sábados, domingos ni `holidays`; responded\_at es la fecha de comunicación de la respuesta; se responde con `make complaint-respond` |
| `complaint_counters` | year, last\_number | PK `year`; se incrementa con `INSERT ... ON CONFLICT (year) DO UPDATE ... RETURNING`, que bloquea la fila del año hasta el fin de la transacción |
| `waitlist_entries` | id, email, source, consented\_at, created\_at | Se borra al registrarse o a los 12 meses |
| `email_suppressions` | email\_hash, email\_kind, reason, created\_at | email\_hash = HMAC-SHA256 del correo normalizado con `CASERO_EMAIL_HASH_KEY`, una clave permanente (ADR-0010); reason ∈ bounce, complaint, unsubscribe; solo suprimen los rebotes permanentes y las quejas; email\_kind nulo en un rebote o una queja (bloquea todo correo) o ∈ daily\_digest, tax\_reminders en una baja (bloquea solo ese tipo); único `(email_hash, email_kind)` con `NULLS NOT DISTINCT`; los correos transaccionales (verificación, recuperación, cancelación de la eliminación y copia del reclamo) nunca se suprimen por una baja |
| `rate_limit_buckets` | key\_hash, window\_start, count | Tabla `UNLOGGED`; la IP nunca se guarda, solo un hash con una sal que rota cada 24 horas; las ventanas son de una hora y el worker borra en cada minuto las que empezaron hace más de 23 horas, así ningún hash llega a 24 horas |
| `job_runs` | job, run\_key, account\_id, status, attempts, started\_at, finished\_at, error\_code | Único `(job, run_key, account_id)` con `NULLS NOT DISTINCT`; status ∈ running, done, failed |
| `pending_object_deletions` | storage\_key, account\_id, requested\_at, attempts, done\_at | Cola para borrar objetos de S3 (con todas sus versiones) antes de purgar filas |

### Datos de cada arrendador (RLS)

| Tabla | Columnas principales | Restricciones clave |
| --- | --- | --- |
| `accounts` | id, display\_name, taxpayer\_kind, ruc, ruc\_group, daily\_digest, deletion\_requested\_at, deletion\_scheduled\_for, deletion\_contact\_enc, purged\_at, created\_at | Política RLS sobre `id`; taxpayer\_kind ∈ person, estate (person por defecto); RUC de 11 dígitos con dígito verificador; `deletion_contact_enc` guarda cifrado el correo original solo para avisar o cancelar la eliminación y se borra en la purga; tras la purga solo quedan id, fechas y `purged_at` (fecha), así que `display_name` solo puede ser nulo en una cuenta purgada |
| `legal_acceptances` | id, account\_id, user\_id, document\_id, accepted\_at, ip\_hash | Solo inserción; la app exige aceptar la versión vigente de términos, privacidad y consentimiento de datos sensibles antes de usar `/app` |
| `legal_withdrawals` | id, account\_id, user\_id, document\_id, withdrawn\_at | Solo inserción; retirar el consentimiento de datos sensibles bloquea la cuenta (solo exportar o eliminar) |
| `subscriptions` | id, account\_id, plan\_code, starts\_at, trial\_ends\_at, ends\_at, ended\_at, founder | Único `(account_id)` donde `ended_at` es nulo; el estado se calcula desde las fechas; `founder` lo marca `make grant-founder` |
| `subscription_payments` | id, account\_id, amount\_cents, paid\_on, method, boleta\_number, months | method ∈ yape, transfer; se conservan con la cuenta anonimizada aunque la cuenta se elimine |
| `push_subscriptions` | id, account\_id, user\_id, endpoint, keys `jsonb`, created\_at, revoked\_at | Notificaciones de la PWA |
| `properties` | id, account\_id, name, address\_line, district, ownership, autovaluo\_cents, rented\_share\_pct, archived\_at | ownership ∈ sole, co\_owned, conjugal\_option, conjugal\_split, estate; estate si y solo si la cuenta es estate (validado en la aplicación); rented\_share\_pct entre 1 y 100, 100 por defecto |
| `units` | id, account\_id, property\_id, name, kind, archived\_at | kind ∈ room, mini\_apartment, apartment, shop, parking, other; no se archiva con contrato activo, y un inmueble tampoco si alguna de sus unidades lo tiene; archivar un inmueble archiva sus unidades |
| `renters` | id, account\_id, full\_name, phone\_e164, email, doc\_type, doc\_enc, doc\_hmac, doc\_last4 | doc\_type ∈ dni, ce, passport, ruc; `doc_enc` en el sobre `v1:<key_id>:<nonce>:<ciphertext>`; `doc_hmac` = HMAC-SHA256 de `tipo:número_normalizado` con una clave permanente (no rotable), para duplicados y para agrupar declaraciones; único `(account_id, doc_hmac)` cuando hay documento; validación al registrar: DNI de 8 dígitos, RUC de 11 con dígito verificador, carné de extranjería y pasaporte de 5 a 12 letras o números; el celular se guarda en E.164, y 9 dígitos que empiezan con 9 se toman como celular peruano (+51) |
| `leases` | id, account\_id, unit\_id, renter\_id, due\_day, start\_date, control\_from\_period, end\_date, ended\_at, tax\_treatment, tools\_enabled, created\_at | due\_day 1 a 31; `end_date` opcional (contrato sin fin previsto), con CHECK `end_date >= start_date`; único parcial por `unit_id` donde `ended_at` es nulo; tax\_treatment ∈ standard, company\_tenant, unsupported (forzado si la propiedad es conjugal\_split); `tools_enabled` (WhatsApp y portal) lo decide el arrendador al exceder el plan |
| `lease_rent_changes` | id, account\_id, lease\_id, monthly\_rent\_cents, effective\_period, created\_by, created\_at | Solo inserción, sin unicidad por período; la renta de un período es la del cambio con mayor `(effective_period, created_at)` tal que `effective_period` ≤ período, así que corregir un error es insertar otra fila del mismo período; al crear el contrato se inserta el primero |
| `charges` | id, account\_id, lease\_id, kind, period, amount\_cents, due\_date, corrects\_charge\_id, pre\_2026, created\_by, created\_at | kind ∈ rent, rent\_correction, opening\_balance, adjustment; único `(lease_id, period)` si kind = rent; un opening\_balance válido por `(lease_id, pre_2026)`, verificado en la aplicación bajo el bloqueo del contrato (un índice único contaría también los anulados); único `corrects_charge_id`; amount > 0 salvo adjustment (≠ 0); period obligatorio en rent y rent\_correction y nulo en opening\_balance; `pre_2026` solo en opening\_balance; `corrects_charge_id` solo en rent\_correction; solo inserción |
| `charge_voids` | charge\_id, account\_id, reason, voided\_by, voided\_at | PK `charge_id`; solo inserción |
| `payments` | id, account\_id, lease\_id, amount\_cents, received\_on, method, deposit\_id, note, source, created\_by, created\_at | id generado por el cliente; amount > 0; method ∈ cash, yape, plin, transfer, bank\_deposit, guarantee; `deposit_id` obligatorio si y solo si method = guarantee; source ∈ landlord, tenant\_voucher; índice `(account_id, received_on)`; solo inserción |
| `payment_voids` | payment\_id, account\_id, reason, voided\_by, voided\_at | PK `payment_id`; solo inserción |
| `deposits` | id, account\_id, lease\_id, amount\_cents, received\_on, note, created\_at | Solo inserción |
| `deposit_voids` | deposit\_id, account\_id, reason, voided\_by, voided\_at | PK `deposit_id`; solo inserción; solo sin pagos ni devoluciones válidos |
| `deposit_movements` | id, account\_id, deposit\_id, amount\_cents, on\_date, created\_by, created\_at | Solo devoluciones al inquilino; amount > 0; solo inserción |
| `deposit_movement_voids` | deposit\_movement\_id, account\_id, reason, voided\_by, voided\_at | PK `deposit_movement_id`; solo inserción |
| `voucher_submissions` | id, account\_id, lease\_id, file\_id, declared\_cents, declared\_on, status, reject\_reason, payment\_id, reviewed\_by, reviewed\_at, created\_at | status ∈ pending, confirmed, rejected; `created_at` permite contar las 10 subidas por enlace al día; único `payment_id`; se confirma con `UPDATE ... WHERE status = 'pending'` |
| `tenant_links` | id, account\_id, lease\_id, nonce, key\_id, token\_hash, created\_at, revoked\_at, last\_used\_at | `token_hash` único; uno vigente por contrato; `key_id` identifica la clave HMAC para rotarla; vence 90 días después de `leases.ended_at`, calculado al resolver el token (no se guarda); tampoco resuelve si la cuenta pidió su eliminación |
| `files` | id, account\_id, purpose, storage\_key, mime, size\_bytes, sha256, created\_at, purged\_at | purpose = voucher; único `(account_id, sha256)` donde `purged_at` es nulo: si el mismo archivo se sube otra vez se reutiliza la fila vigente; la purga de vouchers rechazados a los 90 días borra el objeto (vía `pending_object_deletions`) solo si ninguna otra solicitud no rechazada usa ese archivo, conserva las filas y marca `purged_at`, y una nueva subida del mismo archivo crea otra fila; storage\_key = `{account_id}/{file_id}` |
| `message_templates` | account\_id, kind, body | PK `(account_id, kind)`; kind ∈ friendly, due\_today, overdue |
| `reminder_logs` | id, account\_id, kind, charge\_id, period, renter\_id, renter\_doc\_hmac, channel, created\_at | kind ∈ rent, tax\_due; `charge_id` obligatorio si kind = rent y nulo si kind = tax\_due, que lleva period, renter\_id y renter\_doc\_hmac (nulo si la declaración no tiene documento); channel ∈ whatsapp\_link, email, push; solo inserción |
| `tax_payments` | id, account\_id, period, renter\_doc\_hmac, renter\_id, amount\_cents, paid\_on, order\_number, base\_cents, created\_by, created\_at | `renter_doc_hmac` NOT NULL; la declaración se identifica por `(renter_doc_hmac, period)`; `renter_id` es el inquilino que se mostró al registrar; `base_cents` es el monto declarado que el arrendador confirmó al registrarlo, para decir cuánto más se cobró después de declarar; se permiten varios por declaración; solo inserción |
| `tax_payment_voids` | tax\_payment\_id, account\_id, reason, voided\_by, voided\_at | PK `tax_payment_id`; solo inserción |
| `audit_log` | id, account\_id, actor\_user\_id, action, entity, entity\_id, changed\_fields `text[]`, at | Solo inserción; nombres de campos, nunca valores personales |

**Cómo se relacionan.** Una cuenta tiene inmuebles; un inmueble tiene unidades; una unidad tiene a lo más un contrato activo con un inquilino. Cada contrato acumula cambios de renta, cargos, pagos y garantías. La aplicación de créditos y pagos a cargos, los estados de los cargos y de la suscripción, lo disponible de cada garantía y las declaraciones del impuesto (agrupadas por documento de inquilino y mes) se calculan al leer, no se guardan, así que anular algo nunca deja datos inconsistentes.

**Eliminación de una cuenta.** Al pedirla se guarda cifrado el correo en `deletion_contact_enc`, se anonimiza el correo del usuario, se bloquea el acceso y se programa la purga a 30 días. Se puede cancelar con el enlace enviado a ese correo: `app_cancel_deletion(p_token_hash, p_now)` valida el token de un solo uso, anula la programación, borra `deletion_contact_enc` y lo devuelve, y en la misma transacción la aplicación lo descifra y restaura el correo del usuario. Antes, la app ofrece descargar la exportación y advierte que SUNAT puede revisar hasta 4 años. La purga tiene dos fases en el worker: primero encola en `pending_object_deletions` todos los objetos de la cuenta y los borra con todas sus versiones; cuando no queda ninguno pendiente, descifra `deletion_contact_enc` y llama a `purge_account(p_account_id, p_today, p_email)` (`SECURITY DEFINER`), que verifica que la fecha programada ya pasó y elimina las filas en orden de dependencias, incluidas las de `job_runs` y `pending_object_deletions` de la cuenta y las `registration_invites` de ese correo. `p_email` solo se usa para borrar esas invitaciones y no se escribe en ningún log. Solo quedan la fila de `accounts` anonimizada (sin nombre, RUC ni contacto, marcada como purgada) y sus `subscription_payments`, que Casero debe conservar como contribuyente; los reclamos viven aparte en `complaints`. `purge_account` borra también al usuario de la cuenta con sus `sessions` y `email_tokens`. Un test verifica que no queda ninguna otra fila con ese `account_id`, ni el usuario, ni una invitación con su correo. Los respaldos con esos datos se borran solos a los 30 días, y la política de privacidad lo dice.

## Plan de sprints y lanzamiento

Tres semanas de validación sin código y quince sprints de dos semanas planificados a 7 puntos (carga entre 5 y 8): beta privada con los fundadores el 26 de abril de 2027 y lanzamiento público el 21 de junio de 2027, antes del pico de mudanzas de julio y agosto. Casero se construye a tiempo parcial, así que se planifica con una velocidad conservadora y se ajusta con la velocidad medida. Los sprints de fin de año y de Semana Santa llevan menos carga.

| Fase | Fechas | Objetivo | Historias, en orden | Pts |
| --- | --- | --- | --- | --- |
| Validación | 2 nov – 22 nov 2026 | Formalización, privacidad y validación del negocio (`casero-business`) | — | — |
| Sprint 0 | 23 nov – 6 dic | ADR y monorepo con CI y arquitectura verificable | CS-01, 02 | 5 |
| Sprint 1 | 7 dic – 20 dic | Base segura y publicada con correo y buckets configurados | CS-03, 04 | 8 |
| Sprint 2 | 21 dic – 3 ene 2027 | Cuentas seguras por invitación (sprint corto por las fiestas) | CS-05 | 5 |
| Sprint 3 | 4 ene – 17 ene | Aislamiento probado, funciones del plan, perfil tributario, inmuebles y reglas tributarias como datos | CS-07, 06, 08, 20 | 8 |
| Sprint 4 | 18 ene – 31 ene | Calculadora pública (captación desde fines de enero) e inquilinos y contratos | CS-32, 09 | 7 |
| Sprint 5 | 1 feb – 14 feb | Cargos automáticos y operación segura | CS-11, 26 | 8 |
| Sprint 6 | 15 feb – 28 feb | Pagos con saldos correctos y panel de cobros | CS-12, 13 | 8 |
| Sprint 7 | 1 mar – 14 mar | Correcciones de cargos, renovación y portal del inquilino | CS-31, 18 | 7 |
| Sprint 8 | 15 mar – 28 mar | Formularios de SUNAT (Semana Santa: 25 y 26 de marzo) | CS-21 | 5 |
| Sprint 9 | 29 mar – 11 abr | Cobro por WhatsApp, registro y recordatorio de pagos a SUNAT y exportación para el contador | CS-16, 34 | 7 |
| Sprint 10 | 12 abr – 25 abr | Cumplimiento legal: listo para datos reales | CS-25 | 5 |
| Beta privada | desde 26 abr | Fundadores con sus alquileres reales (registro por invitación, `make grant-founder`); el año de fundador cuenta desde aquí; 15 minutos a la semana con cada uno | — | — |
| Sprint 11 | 26 abr – 9 may | Planes y panel interno | CS-23, 24 | 6 |
| Sprint 12 | 10 may – 23 may | Bienvenida, constancias y garantías | CS-10, 14, 15 | 6 |
| Sprint 13 | 24 may – 6 jun | Vouchers, resumen diario y notificaciones push | CS-19, 17, 33 | 7 |
| Sprint 14 | 7 jun – 20 jun | Pruebas de punta a punta y `REGISTRATION_MODE=open` | CS-27 | 2 |
| Lanzamiento | 21 jun 2027 | Apertura pública con "cobra tus alquileres sin incomodarte y ten claro cuánto pagar a SUNAT cada mes" | — | — |

CS-01 y CS-02 empezaron antes de lo previsto, el 25 de octubre de 2026. Las fechas del plan y la puerta del 22 de noviembre no cambian; el adelanto se refleja en la velocidad medida del Sprint 0.

**Seguimiento de velocidad**

| Sprint | Puntos planificados | Puntos reales | Cierre | Velocidad media |
| --- | --- | --- | --- | --- |
| Sprint 0 | 5 (CS-01, CS-02) | 5 | 25 oct 2026 (el plan lo cerraba el 6 dic) | 5 puntos por sprint |
| Sprint 1 | 8 (CS-03, CS-04) | 8; de CS-04 queda la operación que espera tus cuentas: servidor, dominio, SES y buckets | 26 oct 2026 (el plan lo cerraba el 20 dic) | 6.5 puntos por sprint |
| Sprint 2 | 5 (CS-05) | 5 | 26 oct 2026 (el plan lo cerraba el 3 ene) | 6 puntos por sprint |
| Sprint 3 | 8 (CS-07, CS-06, CS-08, CS-20) | 10, con CS-32 adelantada del Sprint 4 | 27 oct 2026 (el plan lo cerraba el 17 ene) | 7 puntos por sprint |
| Sprint 4 | 7 (CS-32, CS-09) | 5: CS-09 (CS-32 ya se contó en el Sprint 3) | 27 oct 2026 (el plan lo cerraba el 31 ene) | 6.6 puntos por sprint |
| Sprint 5 | 8 (CS-11, CS-26) | 8; de CS-26 queda activar respaldos, Sentry y Better Stack cuando tengas las cuentas | 28 oct 2026 (el plan lo cerraba el 14 feb) | 6.8 puntos por sprint |
| Sprint 6 | 8 (CS-12, CS-13) | 8 | 28 oct 2026 (el plan lo cerraba el 28 feb) | 7 puntos por sprint |
| Sprint 7 | 7 (CS-31, CS-18) | 7 | 28 oct 2026 (el plan lo cerraba el 14 mar) | 7 puntos por sprint |
| Sprint 8 | 5 (CS-21) | 5; de CS-21 queda que un contador valide los casos de prueba (puerta del fin del Sprint 10) | 29 oct 2026 (el plan lo cerraba el 28 mar) | 6.8 puntos por sprint |
| Sprint 9 | 7 (CS-16, CS-34) | 7 | 29 oct 2026 (el plan lo cerraba el 11 abr) | 6.8 puntos por sprint |

Los sprints 1 a 3 se cerraron por contenido, antes de sus fechas. Las fechas del plan y las puertas no cambian: la de fin del Sprint 1 (20 dic) decide si se comprime el plan con esta velocidad. El Sprint 4 cerró con CS-09, el Sprint 5 con CS-11 y CS-26, el Sprint 6 con CS-12 y CS-13, el Sprint 7 con CS-31 y CS-18, el Sprint 8 con CS-21 y el Sprint 9 con CS-16 y CS-34.

**Puertas de decisión**

- **Fin de la validación (22 nov):** se sigue solo si se cumple la puerta de validación del negocio (`casero-business`), con RUC activo y la solicitud de inscripción del banco de datos presentada ante la Autoridad (la inscripción debe estar resuelta antes de la beta), y si ya decidiste qué otro proyecto pausas.
- **Fin del sprint 1 (20 dic):** con la velocidad medida de S0 y S1. Si es de 10 puntos o más, el plan se comprime (beta a fines de marzo, lanzamiento a mediados de mayo). Si es menor de 5, se recorta el alcance de la beta antes de seguir.
- **Fin del sprint 10 (25 abr):** la beta empieza solo si el aislamiento entre cuentas, las páginas legales, la inscripción del banco de datos, los respaldos con restauración probada y la prueba de punta a punta de CS-21 están en verde, y si un contador validó los casos del impuesto. Si no, aplican los términos de la preventa (`casero-business`).
- **Antes de publicar la landing:** el domicilio fiscal revisado en Consulta RUC; el dominio .com con la web y el correo; SES en producción y un correo de prueba recibido en una dirección no verificada en SES; la política de privacidad completa y revisada por el abogado; la solicitud ante la Autoridad presentada; y el libro físico de respaldo en el domicilio fiscal.
- **Antes del lanzamiento (sprint 14):** se revisa la cuota de envío de SES (correos al día y por segundo) frente al volumen de la beta y su proyección a 200 cuentas. Si no alcanza, se pide el aumento a AWS con tiempo.
- **Un mes después del lanzamiento (21 jul):** la puerta de activación de `casero-business` decide si se prioriza la bienvenida y el panel antes que funciones nuevas.

**Si el ritmo es menor.** Antes de mover la beta, se recorta CS-31: se reduce a anular y corregir cargos (sin crédito proporcional). Antes de mover el lanzamiento: CS-17 (resumen diario), CS-33 (push), CS-19 (vouchers; el inquilino envía la foto por WhatsApp), CS-15 (la garantía se anota como nota del contrato) y CS-10 (la bienvenida se reemplaza por los formularios normales). Nunca se recortan el aislamiento entre cuentas, las páginas legales, los respaldos ni la exactitud del impuesto.

## Requisitos no funcionales, seguridad y privacidad

Casero guarda ingresos, deudas y documentos de personas reales: una fuga o un saldo mal calculado destruye la confianza de un negocio pequeño. Por eso la corrección del dinero, el aislamiento entre cuentas y la privacidad pesan más que cualquier función.

| Categoría | Requisito | Cómo se verifica |
| --- | --- | --- |
| Corrección del dinero | Saldo = Σ cargos válidos (los ajustes llevan signo) − Σ pagos válidos para cualquier secuencia; el saldo de cada cargo y el tributo por documento de inquilino y mes, según la regla del año, no dependen del orden de inserción; un crédito no cambia la base de ningún mes anterior a su fecha | Propiedades con Hypothesis y casos validados por un contador |
| Idempotencia | Reenviar un pago, una confirmación de voucher o una tarea del worker no duplica nada | Tests de reenvío y de reejecución |
| Aislamiento | Ningún dato cruza cuentas por la API ni por SQL directo; ninguna tabla nueva queda sin RLS por olvido; ningún rol tiene permisos fuera de la tabla de roles | Tests con dos cuentas por endpoint y test del catálogo de tablas y permisos |
| Autenticación | Argon2id; sesiones revocables y rotadas; CSRF; bloqueo por IP y retraso por correo; doble factor obligatorio en `/admin` con sesiones propias y auditoría; registro cerrado salvo invitación hasta el lanzamiento | Tests de sesión, CSRF, 429, TOTP y `REGISTRATION_MODE` |
| Datos personales | Documento cifrado con AES-GCM y clave rotable; consentimiento obligatorio de datos sensibles y retiro que bloquea la cuenta; logs y errores sin datos personales; exportación y eliminación en dos fases | Test de que el documento no aparece en claro en la base, los logs ni el seguimiento de errores |
| Archivos | Bucket privado con versionado y expiración de versiones antiguas a 30 días, claves `{account_id}/{file_id}`, validación por contenido, imágenes sin metadatos, 5 MB, cupos por enlace, URLs de 5 minutos, PDF como descarga | Tests con archivos falsos, sobredimensionados y con EXIF; `make check-bucket-policy` |
| Seguridad web | CSP estricta, HSTS, `Referrer-Policy: no-referrer`, cookies `__Host-`, validación con Pydantic, escaneo de dependencias en CI | Test de cabeceras |
| Disponibilidad | 99 % mensual; worker que se recupera solo | Monitor externo |
| Pérdida de datos aceptable | Hasta 6 horas de registros en el peor caso; restauración en menos de 4 horas | Prueba mensual de restauración desde cero |
| Rendimiento | Panel de cobros en menos de 1 s (p95) con 10 contratos, medido en el servidor (sin la latencia Lima–EE. UU.); primera carga móvil en menos de 3 s en 4G, con los assets estáticos con hash servidos con caché larga | Prueba de carga simple en el servidor y Lighthouse |
| Accesibilidad y uso | WCAG 2.1 AA; letra mínima de 16 px; botones de 44 px; usable con una mano en 360 px | axe y revisión con 3 usuarios mayores de 45 años |
| Tiempo | `Clock` inyectado con `now()` y `today_lima()`; fin de mes, febrero y año bisiesto probados | Tests con reloj falso |
| Costo | Infraestructura bajo US$ 30 al mes hasta 200 cuentas | Revisión mensual |
| Incidentes | Plan escrito para notificar a la Autoridad en 48 horas, a los afectados y al Centro Nacional de Seguridad Digital | `docs/ops/incident-response.md` revisado antes de la beta |

**Retención de datos**

| Dato | Se conserva | Al eliminar la cuenta |
| --- | --- | --- |
| Inmuebles, contratos, inquilinos, cobros y declaraciones | Mientras la cuenta exista | Se purgan a los 30 días |
| Vouchers rechazados | 90 días | Se purgan con la cuenta |
| Versiones antiguas de archivos en S3 | 30 días | Se borran con todas sus versiones antes de purgar las filas |
| Correo de contacto para la eliminación (`deletion_contact_enc`) | Solo durante los 30 días de espera | Se borra en la purga |
| Pagos de la suscripción y boletas | El plazo que indique el contador | Se conservan con la cuenta anonimizada |
| Reclamos | 2 años desde que se presentan, el mínimo del Reglamento (art. 12); luego el worker los borra (CS-25) | Se conservan en `complaints` |
| Lista de espera | Hasta registrarse o 12 meses | — |
| Límite de peticiones (hash de la IP) | 24 horas | — |
| Respaldos | 30 días | Los datos purgados desaparecen de los respaldos a los 30 días |

**Límites declarados** (van en los términos y en la ayuda):

- Casero no presenta declaraciones ni paga impuestos por el arrendador, y su cálculo no reemplaza la revisión de un contador.
- La constancia de Casero no es un comprobante de pago SUNAT; el recibo oficial es el Formulario 1683.
- Casero no verifica que un voucher sea real; el arrendador confirma el dinero que recibió.
- Si el arrendador registra mal un pago, el tributo calculado también estará mal.
- Casero no entrega información a terceros salvo ante un requerimiento legal obligatorio.

## Repositorio, convenciones y operación

Un monorepo público desde el inicio de la implementación, con todos los derechos reservados (sin licencia abierta). Nunca contiene secretos, datos personales reales ni información de negocio. Los datos del negocio que la web debe mostrar (nombre, RUC y domicilio del responsable) viven en variables de entorno (`CASERO_BUSINESS_*`); el worker los usa en la copia de cada reclamo, y Caddy los sirve en `GET /api/public/business` (con `CASERO_COMPLAINTS_INBOX` y `CASERO_PRIVACY_INBOX`), así el Libro de Reclamaciones, la política de privacidad y el aviso de la lista de espera los muestran aunque la API esté caída. El plan de negocio vive en el repositorio privado `Alesso2805/casero-business`, y GitHub tiene activados el escaneo de secretos y la protección de push.

```text
casero/
├── backend/
│   ├── src/casero/
│   │   ├── identity/          # domain, application, infrastructure, api
│   │   ├── accounts/
│   │   ├── properties/
│   │   ├── leases/
│   │   ├── ledger/
│   │   ├── reminders/
│   │   ├── tax/
│   │   ├── tenant_portal/
│   │   ├── admin/
│   │   ├── shared/
│   │   │   ├── kernel/        # Clock, Money, ids (puro)
│   │   │   └── infrastructure/ # contextos de base, Mailer, Storage, crypto
│   │   ├── api.py             # app FastAPI
│   │   └── worker.py          # tareas programadas
│   ├── migrations/            # Alembic
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/       # Testcontainers
│   │   ├── architecture/      # reglas AR y test del catálogo
│   │   ├── deployment/        # pruebas del borde con el Caddyfile de producción
│   │   └── smoke/             # pruebas de humo por flujo
│   ├── scripts/               # exportación del contrato OpenAPI
│   └── pyproject.toml
├── web/
│   ├── src/account/           # registro, sesión y datos del arrendador
│   ├── src/properties/        # inmuebles y unidades; cada módulo del arrendador en su carpeta
│   ├── src/tenant/            # portal del inquilino (CS-18)
│   ├── src/admin/             # panel interno (CS-24)
│   ├── src/test/              # ayudas de Vitest
│   ├── src/landing/           # landing y calculadora pública
│   ├── src/api/               # tipos generados con openapi-typescript
│   └── e2e/                   # Playwright
├── infra/
│   ├── postgres/init/         # roles casero_owner, casero_backup, casero_app, casero_worker, casero_admin
│   ├── seed/tax/              # 2026.yaml, 2027.yaml con su fuente
│   ├── caddy/                 # Caddyfile (local) y Caddyfile.prod
│   ├── edge/                  # imagen de Caddy con la web compilada
│   ├── backup/                # respaldos cifrados: pg_dump, age y rclone (ADR-0013)
│   └── deploy/                # despliegue en el servidor
├── docs/
│   ├── SPEC.md
│   ├── BACKLOG.md
│   ├── ARCHITECTURE_RULES.md
│   ├── adr/                   # en inglés
│   ├── legal/                 # términos, privacidad, consentimiento, oficial de datos
│   ├── ops/                   # respaldos, claves, incidentes, carga anual del cronograma
│   └── reviews/               # revisiones críticas cada 3 sprints, en PDF
├── docker-compose.yml
├── Makefile                   # up, down, test, lint, migrate, load-tax-config, invite, check-bucket-policy; luego create-staff, grant-founder y complaint-respond
├── CLAUDE.md
└── README.md
```

| Artefacto | Propósito | Cuándo se actualiza |
| --- | --- | --- |
| `docs/SPEC.md` | Producto, marco legal, reglas, esquema, plan y requisitos | Al cambiar alcance o reglas |
| `docs/BACKLOG.md` | Historias con criterios y dependencias | Al cerrar o cambiar una historia |
| `casero-business` (repositorio privado) | Validación, precios, costos, métricas y adquisición | Tras cada aprendizaje con clientes |
| `docs/ARCHITECTURE_RULES.md` | Reglas AR con su test | Cuando cambia la arquitectura |
| `docs/adr/` | Decisiones técnicas en inglés | Cada decisión no trivial |
| `docs/legal/` | Términos, privacidad y consentimiento con versión y fecha | Antes de cualquier cambio que afecte datos o precios |
| `docs/ops/` | Respaldos, restauración, claves, incidentes y carga del cronograma | Cada vez que se ejecuta uno |
| `infra/seed/tax/` | Única fuente de las reglas, la UIT, el cronograma de SUNAT y los feriados por año, con su fuente | Cada diciembre, validado con el contador |
| Contrato OpenAPI | Generado por la API; CI falla si los tipos del frontend no están al día | Cada cambio de endpoint |

**Idioma.** Interfaz, especificación y textos legales en español de Perú. Código, nombres de tablas, ADR y README en inglés.

**Convenciones.** Ramas `feat/CS-NN-descripcion`; Conventional Commits; un PR por historia con la checklist de la definición de hecho; tablas y columnas en `snake_case`.

**Operación recurrente**

| Cada | Tarea |
| --- | --- |
| Día | Revisar alertas del monitor, respaldos, tareas fallidas y errores; responder soporte por el WhatsApp Business del negocio |
| Semana | Revisar reclamos (respuesta en máximo 15 días hábiles), métricas de activación y conversión, y conversar con 2 clientes |
| Mes | Probar una restauración desde cero; revisar costos; registrar ingresos para tus propios impuestos |
| Año (diciembre) | Agregar al YAML del año siguiente el cronograma de SUNAT, las reglas (con la UIT) y los feriados, validados con el contador, y desplegarlos (el migrador los carga al arrancar; en local, `make load-tax-config`); revisar términos y privacidad |

**Antes de comprar el dominio.** Verificar que "Casero" esté disponible como dominio y marca; si no, elegir otro nombre antes de comprar el dominio y antes de registrar la marca en Indecopi.

## Registro del debate y decisiones abiertas

Esta especificación pasó por cuatro rondas de revisión con dos agentes independientes: A (negocio, marco legal y tributario peruano, producto) y B (arquitectura, esquema, seguridad, backlog y plan). Cada ronda terminó cuando el autor aplicó todos los hallazgos aceptados; el debate se cerró cuando ambos revisores declararon que no quedaban bloqueantes ni importantes.

| Ronda | Versión revisada | Hallazgos de A | Hallazgos de B | Resultado |
| --- | --- | --- | --- | --- |
| 1 | v1 | A1–A13 | B1–B21 | Todos aceptados; v2 con decisiones por defecto |
| 2 | v2 | A14–A20 | B22–B35 | Todos aceptados; v3 con declaración por documento de inquilino, nuevo rol de worker y 34 historias |
| 3 | v3 | A21 (importante), A22–A24 | B36–B37 (importantes), B38–B44 | Todos aceptados; v4 con un declarante por cuenta, rol de respaldos y tabla de roles completa |
| 4 | v4 | A25 (menor) | B45–B46 (menores) | Aplicados; ambos revisores: sin bloqueantes ni importantes |

**Revisión previa al Sprint 0 (octubre de 2026).** Una revisión de v4 contra el plan de los sprints 0 y 1 encontró 24 puntos (10 que afectaban a esos sprints y 14 posteriores). Alessandro los decidió todos y v5 los aplica: orden acíclico de módulos, contexto tenant que falla cerrado, `casero_admin` sin `BYPASSRLS`, fechas como parámetro en las funciones SQL, créditos ordenados junto con los pagos, sobre de cifrado con id de clave, configuración tributaria con una sola fuente y `entitlements` adelantado a CS-07.

**Correcciones de mayor impacto**

- El Formulario 1683 es uno por documento de inquilino y mes de cobro, sumando sus contratos, con base y tributo redondeados al sol (ejemplo de prueba: 450.50 + 100.50 → base 551, tributo 28).
- Una cuenta es un solo declarante con un RUC; las sucesiones van en su propia cuenta.
- Los saldos de 2025 o antes no entran a la base (se gravaron por devengado); los créditos nunca entran a la base; el cálculo no depende del orden de registro.
- Con `FORCE` RLS el dueño también queda sujeto a las políticas: `casero_owner` y un rol `casero_backup` tienen `BYPASSRLS`; la API y el worker nunca.
- La tabla de roles es exhaustiva y se verifica con un test de catálogo y pruebas de humo por flujo.
- El plan pasó de 30 a 34 historias, con la beta el 26 de abril y el lanzamiento el 21 de junio de 2027.

**Decisiones tomadas por defecto (Alessandro puede cambiarlas)**

| Tema | Decisión |
| --- | --- |
| Segmento | Arrendador con RUC o que quiere formalizarse; el reposicionamiento según la validación vive en `casero-business` |
| Planes | Gratis (1 contrato) y Casero (S/ 19 al mes o S/ 190 al año, 10 contratos); sin Plus en el MVP |
| Historial 2026 y resumen anual | No se importa historial; el resumen anual (CS-22) es posterior al lanzamiento |
| Recordatorio por WhatsApp | Primera historia después del lanzamiento (CS-30); se adelanta si en la beta se abren menos de la mitad de los correos |
| Exceso de plan | El arrendador elige qué contratos conservan WhatsApp y portal |
| Panel interno | Mismo proceso, puerto aparte solo en `127.0.0.1` del servidor con túnel SSH, y TOTP |
| Velocidad | 7 puntos por sprint, con puerta al final del sprint 1 para comprimir o recortar |
| Respaldo | Cada 6 horas a otro proveedor; restauración en menos de 4 horas |

**Preguntas que solo Alessandro puede cerrar**

- Régimen tributario propio con el contador (evaluar Nuevo RUS).
- Disponibilidad del nombre "Casero" como dominio y marca antes de CS-04.