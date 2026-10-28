# Plan de respuesta a incidentes

> **Borrador para revisar con el abogado antes de la beta** (SPEC, "Incidentes"). Los canales oficiales de la Autoridad y del Centro Nacional de Seguridad Digital van entre corchetes hasta confirmarlos.

Un incidente es cualquier hecho que pone en riesgo la confidencialidad, la integridad o la disponibilidad de los datos que trata Casero. Algunos ejemplos:

- alguien entra sin permiso al servidor, a la base, a un bucket o a una cuenta de un proveedor;
- se publica una clave o una contraseña: en el repositorio, en un chat o en un registro;
- una cuenta ve datos de otra cuenta;
- se pierden datos o un respaldo no se puede restaurar;
- un error deja datos personales en registros, en Sentry o en un correo equivocado.

Tú eres el oficial de datos personales y quien responde. Todo se anota en el registro de abajo desde el primer minuto, sin copiar datos personales en él.

## 1. Contener (primeras 2 horas)

1. **Cortar el acceso.**
   - Si la API expone datos, detenerla: `docker compose stop api edge` en `/opt/casero`.
   - Si el problema está en el registro, dejar `REGISTRATION_MODE=closed`.
2. **Cerrar todas las sesiones:**
   `UPDATE sessions SET revoked_at = <ahora UTC> WHERE revoked_at IS NULL;` como `casero_owner`.
3. **Rotar lo comprometido.** Las claves viven en Bitwarden. Se reemplazan en `/opt/casero/.env` y se redespliega.
   - Contraseñas de los roles de la base: `ALTER ROLE ... PASSWORD ...`.
   - Claves de proveedores: B2 (`backup` y las de vouchers), SES (SMTP), Sentry, GitHub y la llave SSH del despliegue.
   - `CASERO_ENCRYPTION_KEYS`: agregar una clave nueva, activarla y volver a cifrar las columnas `*_enc` (ADR-0007). El trabajo de recifrado se escribe en ese momento si todavía no existe.
   - `CASERO_DOC_HMAC_KEY` y `CASERO_EMAIL_HASH_KEY` **no se rotan**: si se comprometen, hace falta una migración con su propio ADR (ADR-0007 y ADR-0010).
   - `CASERO_UNSUBSCRIBE_KEY` y `CASERO_RATE_LIMIT_KEY` se pueden cambiar en cualquier momento. Los enlaces de baja ya enviados dejan de funcionar.
4. **Preservar la evidencia:**
   - copias de los registros del servidor, la lista de accesos del proveedor y la hora de cada hallazgo;
   - antes de borrar o restaurar algo, guardar una copia del estado actual.

## 2. Evaluar (antes de las 24 horas)

- Qué datos se expusieron: ingresos (datos sensibles), documentos o celulares de inquilinos, correos, contraseñas (están con Argon2id).
- De cuántas cuentas y personas, y desde cuándo.
- Si sigue ocurriendo.
- Si afecta los derechos de las personas: por ejemplo, si permite suplantarlas o exponer sus ingresos.

## 3. Notificar

| A quién | Cuándo | Por dónde | Qué decir |
| --- | --- | --- | --- |
| Autoridad Nacional de Protección de Datos Personales | Dentro de las **48 horas** desde que se conoce el incidente (D.S. N.° 016-2024-JUS) | [canal oficial por confirmar con el abogado] | Qué pasó, qué datos, cuántos titulares, qué medidas se tomaron y quién es el contacto |
| Arrendadores afectados | Sin demora | Correo a la cuenta | Qué pasó con sus datos y los de sus inquilinos, qué hicimos y qué pueden hacer. Para los datos de inquilinos, Casero es encargado y el arrendador es el responsable (términos, anexo de encargo), así que el arrendador decide cómo avisar a sus inquilinos |
| Inquilinos afectados | Sin demora, cuando afecte sus derechos y en coordinación con el arrendador | [por confirmar con el abogado] | Lo mismo, en lenguaje simple |
| Centro Nacional de Seguridad Digital | Si es un incidente digital | [canal oficial por confirmar] | Reporte técnico sin datos personales |

Los textos de cada aviso se escriben en el momento con el abogado. Nunca se promete algo que no se sabe.

## 4. Recuperar

- Restaurar desde el respaldo si hace falta (`backups.md`), aceptando la pérdida de hasta 6 horas.
- Corregir la causa con un PR que tenga un test que reproduzca el problema.
- Revisar en Sentry y en Better Stack que todo vuelva a la normalidad.

## 5. Revisar (dentro de 2 semanas)

Escribir en el registro la causa, la línea de tiempo, qué funcionó, qué no y qué se cambia. Si el cambio es técnico, va como ADR.

## Registro

| Fecha y hora (Lima) | Qué pasó | Datos y personas afectadas | Avisos enviados | Cerrado |
| --- | --- | --- | --- | --- |
