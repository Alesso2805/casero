# Buckets de almacenamiento (Backblaze B2)

Proveedor: Backblaze B2, región **US-East** (Reston, Virginia, EE. UU.). La región se elige al crear la cuenta de Backblaze y después no se puede cambiar. Los dos buckets quedan en esa región.

Los nombres de bucket son únicos en todo B2; `<prefijo>` se fija al crearlos y se anota en el registro del final.

## Resumen

| Bucket | Uso | Versionado | Ciclo de vida | Bloqueo de objetos |
| --- | --- | --- | --- | --- |
| `<prefijo>-vouchers` | Fotos y PDF de vouchers, con claves `{account_id}/{file_id}` | Sí | Las versiones antiguas se borran a los 30 días | No |
| `<prefijo>-backups` | Respaldos de `pg_dump`, ya cifrados antes de subir (CS-26) | Sí | Cada respaldo se oculta a los 30 días y se borra 1 día después | Sí, activado al crear el bucket, 30 días |

Los dos buckets son privados (`allPrivate`) y tienen activo el cifrado del lado del servidor (SSE-B2).

## Bucket de vouchers

- **Versionado:** B2 conserva todas las versiones de cada archivo.
- **Ciclo de vida:** una regla para todo el bucket.
  - `daysFromHidingToDeleting = 30`: las versiones antiguas y las ocultas se borran a los 30 días.
  - `daysFromUploadingToHiding` vacío: la versión vigente nunca se oculta sola.
  - Su equivalente en la API S3 es `NoncurrentVersionExpiration` con `NoncurrentDays = 30`.
- **Sin bloqueo de objetos:** la purga de una cuenta borra sus objetos con todas sus versiones en el momento (`ListObjectVersions` y `DeleteObject` con `versionId`), lo que el bloqueo impediría.
- **Acceso:**
  - Solo con URLs firmadas (SigV4) de 5 minutos, generadas por la API.
  - Los PDF se descargan con `Content-Disposition: attachment`.
- **Sin CORS:** la subida pasa por la API, que valida y recodifica cada archivo, y la descarga es una navegación a la URL firmada.

## Bucket de respaldos

- **Bloqueo de objetos:**
  - Se activa al crear el bucket. Después ya no se puede desactivar.
  - Retención por defecto: 30 días, en modo **compliance**. En ese modo nadie, ni siquiera la cuenta dueña, puede borrar un respaldo antes de que pasen los 30 días. Así un respaldo sobrevive aunque roben una clave.
- **Ciclo de vida:**
  - `daysFromUploadingToHiding = 30` y `daysFromHidingToDeleting = 1`.
  - Cada respaldo desaparece hacia el día 31, cuando su bloqueo ya venció. Así se cumple lo que promete la política de privacidad: los datos purgados desaparecen de los respaldos en 30 días.
- **Contenido:** los respaldos se cifran antes de subir (CS-26). El bucket nunca recibe datos en claro.

## Claves de aplicación

Cada clave tiene solo las capacidades que necesita y está limitada a un bucket.

| Clave | Bucket | Capacidades | Dónde vive |
| --- | --- | --- | --- |
| `api` | vouchers | `listFiles`, `readFiles`, `writeFiles` | Entorno de la API |
| `worker` | vouchers | `listFiles`, `readFiles`, `deleteFiles` | Entorno del worker (purgas) |
| `backup` | respaldos | `listFiles`, `writeFiles` (sin `deleteFiles`) | Entorno del proceso de respaldo |
| `restore` | respaldos | `listFiles`, `readFiles` | Solo en Bitwarden |

La clave maestra de la cuenta vive solo en Bitwarden y nunca en el servidor. Si el cliente S3 lo necesita, se agrega `listBuckets` a la clave correspondiente; se confirma en CS-04.

## Verificación

`make check-bucket-policy` (CS-04) compara la configuración real con este documento y falla si algo difiere. Revisa en cada bucket:

- que sea privado;
- que tenga versionado y SSE-B2;
- su regla de ciclo de vida;
- que el de respaldos tenga bloqueo de objetos con 30 días en compliance;
- que el de vouchers no tenga bloqueo de objetos;
- que no tenga CORS.

## Pasos de creación (una sola vez, en CS-04)

1. Crear la cuenta de Backblaze eligiendo la región US-East.
2. Activar el doble factor en la cuenta y guardar la clave maestra en Bitwarden.
3. Crear `<prefijo>-backups` con bloqueo de objetos activado y retención por defecto de 30 días en compliance.
4. Crear `<prefijo>-vouchers` sin bloqueo de objetos.
5. Configurar en ambos el cifrado SSE-B2 y las reglas de ciclo de vida.
6. Crear las cuatro claves de aplicación y guardarlas en Bitwarden.
7. Ejecutar `make check-bucket-policy`.
8. Anotar la ejecución en el registro de abajo.

## Registro

| Fecha | Acción | Quién |
| --- | --- | --- |
| | | |
