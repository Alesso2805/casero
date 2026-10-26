# Libro de Reclamaciones: leer y responder

Hasta que exista `make complaint-respond` (CS-25), los reclamos se leen y se responden a mano con el rol `casero_admin`. El plazo es de 15 días hábiles, sin prórroga, y la fecha límite está en `due_at`. Cada reclamo nuevo llega como aviso a `CASERO_COMPLAINTS_INBOX`, solo con su número y su plazo.

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

1. Escribir la respuesta por el medio que eligió el consumidor (`response_channel`):
   - `email`: desde el correo de reclamos a su `email`;
   - `letter`: una carta a su `address`, guardando la constancia de envío.
2. Registrar la respuesta y la fecha en que se comunicó, en una sola transacción:

```sql
BEGIN;
UPDATE complaints
SET response = '<texto de la respuesta>', responded_at = '<AAAA-MM-DD HH:MM>-05'
WHERE number = '<número>' AND responded_at IS NULL;
INSERT INTO staff_audit_log (id, staff_user_id, actor, action, entity, entity_id, at)
SELECT gen_random_uuid(), NULL, 'cli', 'complaint.respond', 'complaints', id,
       '<AAAA-MM-DD HH:MM>-05'
FROM complaints WHERE number = '<número>';
COMMIT;
```

Si un reclamo vino marcado como queja pero trata del servicio, se atiende como reclamo.

## Conservación

Los reclamos se conservan 2 años desde que se presentan (Reglamento, art. 12). El borrado automático llega con CS-25.

## Registro

| Fecha | Número | Acción | Quién |
| --- | --- | --- | --- |
| | | | |
