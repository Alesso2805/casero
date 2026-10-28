# Respaldos y restauración

Cómo se respalda la base y cómo se restaura desde cero (CS-26). El bucket y sus claves están en `storage-buckets.md`.

## Qué hace el servicio `backup`

- Cada 6 horas corre `pg_dump` como `casero_backup`, que tiene `BYPASSRLS`. Por eso el respaldo incluye todas las cuentas aunque la RLS esté forzada.
- Deja fuera los datos de `rate_limit_buckets`: solo son hashes de IP que deben durar 24 horas (ADR-0004). La tabla vacía sí se respalda.
- Cifra el respaldo con `age` usando la clave pública `CASERO_BACKUP_AGE_RECIPIENT`. La clave privada vive solo en Bitwarden y nunca en el servidor: el servidor puede escribir respaldos, pero no leerlos.
- Sube el archivo `casero-<fecha UTC>.dump.age` al bucket de respaldos con `rclone`. El bloqueo de objetos de 30 días impide borrarlo antes, ni siquiera con una clave robada.
- Si el respaldo sale bien, avisa al heartbeat de respaldos de Better Stack. Si el aviso no llega a tiempo, Better Stack te alerta.
- Revisa el disco de la base: si está por debajo del 80 %, avisa al heartbeat de disco. Si el disco llega al 80 %, deja de avisar y Better Stack te alerta.

El servicio está apagado hasta que actives el perfil `backup` y completes las variables. CI prueba en cada cambio que el respaldo sale cifrado y que se restaura completo en una base vacía.

## Ponerlo en marcha (una sola vez)

1. Generar el par de claves de `age` en tu computadora, no en el servidor:
   ```
   docker run --rm --entrypoint age-keygen ghcr.io/alesso2805/casero-backup:<tag>
   ```
   Guardar la salida completa (incluida la clave privada `AGE-SECRET-KEY-...`) en Bitwarden como "Casero — clave de respaldos". La línea `# public key: age1...` es la clave pública.
2. En Better Stack (plan gratuito), crear:
   - un monitor de disponibilidad de `https://<dominio>/api/health` cada 3 minutos;
   - un heartbeat "Respaldos" con período de 6 horas y gracia de 1 hora;
   - un heartbeat "Disco" con el mismo período;
   - un heartbeat "Worker" con período de 5 minutos y gracia de 5 minutos: el worker lo envía cada minuto que todas sus tareas corren sin caerse, así que avisa si se detiene, se cuelga o pierde la base. Su URL va en `CASERO_WORKER_HEARTBEAT_URL` (`server.md`).
3. Agregar al `.env` del servidor (`/opt/casero/.env`):
   ```
   COMPOSE_PROFILES=backup
   CASERO_BACKUP_AGE_RECIPIENT=age1...
   CASERO_BACKUP_TARGET=b2:<prefijo>-backups
   CASERO_BACKUP_B2_KEY_ID=<keyID de la clave backup>
   CASERO_BACKUP_B2_APP_KEY=<applicationKey de la clave backup>
   CASERO_BACKUP_HEARTBEAT_URL=<URL del heartbeat de respaldos>
   CASERO_DISK_HEARTBEAT_URL=<URL del heartbeat de disco>
   ```
4. Desplegar. Dentro de unos minutos debe aparecer el primer `casero-*.dump.age` en el bucket y el heartbeat debe ponerse en verde.

## Prueba mensual de restauración desde cero

Se hace cada mes, partiendo solo de Bitwarden, y se anota en el registro de abajo. La meta es restaurar en menos de 4 horas (SPEC).

1. En una máquina limpia con Docker, sacar de Bitwarden la clave privada de `age` y la clave `restore` de B2.
2. Descargar el respaldo más reciente:
   ```
   export RCLONE_CONFIG_B2_TYPE=b2 RCLONE_CONFIG_B2_ACCOUNT=<keyID restore> RCLONE_CONFIG_B2_KEY=<applicationKey restore>
   rclone lsf b2:<prefijo>-backups | sort | tail -1
   rclone copyto b2:<prefijo>-backups/<archivo> ./respaldo.dump.age
   ```
3. Levantar un PostgreSQL 17 con los roles de `infra/postgres/init` y crear la base `casero`.
4. Descifrar y restaurar:
   ```
   age --decrypt --identity clave.txt respaldo.dump.age | pg_restore --username postgres --dbname casero
   ```
5. Comprobar:
   - el conteo de filas de `accounts`, `leases` y `payments`;
   - que `SELECT relforcerowsecurity FROM pg_class WHERE relname = 'leases'` devuelva `t`.
6. Borrar la máquina y la clave descargada.

## Volver a una versión anterior

`server.md` explica cómo volver a una imagen anterior. Si entre las dos versiones hubo una migración, cambiar `IMAGE_TAG` no basta: el migrador de la versión anterior no conoce la revisión nueva y la app no arranca. En ese caso hay dos caminos: corregir hacia adelante con una versión nueva, o restaurar el respaldo anterior a la migración con los pasos de arriba, aceptando que se pierde lo registrado desde entonces.

## Registro

| Fecha | Qué se hizo | Respaldo usado | Tiempo | Resultado |
| --- | --- | --- | --- | --- |
