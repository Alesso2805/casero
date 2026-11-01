# Libro de Reclamaciones: leer y responder

Los reclamos se leen con el rol `casero_admin` y se responden con `make complaint-respond`. El plazo es de 15 días hábiles, sin prórroga, y la fecha límite está en `due_at`. Cada reclamo nuevo llega como aviso a `CASERO_COMPLAINTS_INBOX`, solo con su número y su plazo, y si sigue sin respuesta a los 7 y a los 12 días hábiles llega una alerta a `CASERO_ALERTS_INBOX`.

## 1. Entrar a la base

```sh
gcloud compute ssh casero --zone=us-east1-b
cd /opt/casero
docker compose --env-file .env --env-file image.env exec postgres psql -U casero_admin -d casero
```

## 2. Ver los reclamos sin responder

```sql
SELECT number, kind, created_at AT TIME ZONE 'America/Lima' AS presentado, due_at,
       response_channel
FROM complaints
WHERE responded_at IS NULL
ORDER BY due_at;
```

Para ver uno completo: `SELECT * FROM complaints WHERE number = '000000001-2026' \gx`.

## 3. Responder

1. Escribir la respuesta en un archivo de texto en el servidor, por ejemplo `/tmp/respuesta.txt`.
2. Enviarla y registrarla, según el medio que eligió el consumidor (`response_channel`):
   - `email`: el comando la envía a su correo, con `Reply-To` al correo de reclamos, y registra la fecha. Si el correo falla, no se registra nada y se vuelve a intentar.
     ```sh
     docker compose --env-file .env --env-file image.env run --rm -T migrate python -m casero.worker complaint-respond <número> < /tmp/respuesta.txt
     ```
   - `letter`: enviar la carta a su `address`, guardar la constancia de envío, y registrar el texto con la fecha de envío:
     ```sh
     docker compose --env-file .env --env-file image.env run --rm -T migrate python -m casero.worker complaint-respond <número> <AAAA-MM-DD> < /tmp/respuesta.txt
     ```
3. Borrar el archivo. Cada respuesta queda en `staff_audit_log`.

En local es `make complaint-respond NUMBER=<número> FILE=<archivo>`, con `SENT_ON=<AAAA-MM-DD>` si es por carta.

Si un reclamo vino marcado como queja pero trata del servicio, se atiende como reclamo.

## 4. Si la copia al consumidor no salió

El aviso de cada reclamo dice el estado de la copia. Si dice que no se pudo enviar o que el envío no terminó:

1. Imprimir la copia exacta, la misma que habría enviado el worker:
   ```sh
   docker compose --env-file .env --env-file image.env exec worker python -m casero.worker complaint-copy <número>
   ```
2. Enviarla desde la cuenta de Gmail de reclamos al correo del consumidor, con el mismo asunto y el mismo texto.
3. Registrar el envío como `casero_admin`:
   ```sql
   INSERT INTO staff_audit_log (id, staff_user_id, actor, action, entity, entity_id, at)
   SELECT gen_random_uuid(), NULL, 'cli', 'complaint.copy_sent_by_hand', 'complaints', id,
          '<AAAA-MM-DD HH:MM>-05'
   FROM complaints WHERE number = '<número>';
   ```

El worker nunca reintenta un correo (CLAUDE.md, regla 12).

## 5. Revisión semanal

Las alertas avisan de una copia que falló (`complaint_email.failed`) o que lleva más de 10 minutos sin terminar (`complaint_email.stuck`). Como respaldo, una vez por semana, como `casero_admin`:

```sql
SELECT c.number, j.job, j.status, j.error_code
FROM job_runs j JOIN complaints c ON j.run_key = c.id::text
WHERE j.job IN ('complaint_copy', 'complaint_notice')
  AND (j.status = 'failed' OR (j.status = 'running' AND j.started_at < now() - interval '10 minutes'));

SELECT c.number FROM complaints c
WHERE NOT EXISTS (
    SELECT 1 FROM job_runs j WHERE j.job = 'complaint_notice' AND j.run_key = c.id::text
);
```

- **Primera consulta:** muestra los correos que fallaron o que quedaron a medias.
- **Segunda consulta:** muestra los reclamos sin aviso. Eso pasa si el worker no está corriendo, o si el correo falló antes de que llegara el aviso.

Cada uno se resuelve con el paso 4.

## 6. Si el libro virtual no funcionó

Si la página no pudo registrar un reclamo, le pide al consumidor que imprima la hoja y la envíe a la cuenta de Gmail de reclamos. Cuando llegue uno así:

1. Dentro del día siguiente a que el libro vuelva a funcionar (Reglamento, art. 4-A), registrarlo con la fecha y la hora en que llegó el correo. El número, el año y `due_at` salen de esa fecha, y el worker envía la copia al consumidor como siempre.
   Se escribe la hoja en un archivo JSON con los mismos campos que el formulario (`POST /api/public/complaints`), por ejemplo `/tmp/reclamo.json`:
   ```sh
   docker compose --env-file .env --env-file image.env run --rm -T migrate python -m casero.worker complaint-register <AAAA-MM-DDTHH:MM> < /tmp/reclamo.json
   ```
   Sin zona horaria, la fecha se toma como hora de Lima. En local es `make complaint-register FILED_AT=<fecha> FILE=<archivo>`.
2. Borrar el archivo, que tiene datos personales. El registro queda en `staff_audit_log`.

## Libro físico de respaldo

En el domicilio fiscal se guarda un libro físico, comprado o impreso con la herramienta gratuita de INDECOPI. Todo reclamo que se anote ahí se pasa al libro virtual igual que en el paso 6.

## Conservación

Los reclamos se conservan 2 años desde que se presentan (Reglamento, art. 12); después el worker los borra solo.

## Registro

| Fecha | Número | Acción | Quién |
| --- | --- | --- | --- |
| | | | |
