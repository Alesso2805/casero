# Correo con Amazon SES

Se hace una sola vez, después de comprar el dominio (`docs/ops/server.md`, sección 3). Todo en la región **us-east-1**.

## 1. Cuenta y dominio

1. Crear la cuenta de AWS, activar el doble factor en el usuario raíz y guardar el acceso en Bitwarden. Para el día a día, crear un usuario IAM con acceso a SES y SNS.
2. En SES, crear la identidad del dominio con **Easy DKIM** (RSA de 2048 bits) y copiar los tres CNAME de DKIM al DNS.
3. En la misma identidad, configurar el **MAIL FROM** propio como `mail.<dominio>.com` y crear su MX y su TXT de SPF (tabla de `server.md`).
4. Crear el registro `_dmarc` con `p=none`.
5. Esperar a que SES muestre el dominio como verificado.

## 2. Rebotes y quejas

1. En SNS (us-east-1), crear el tema estándar `casero-ses-events`. En su configuración, poner **SignatureVersion = 2**: el webhook solo acepta firmas SHA-256.
2. Crear la suscripción **HTTPS** a `https://<dominio>.com/api/public/email-events`. La API la confirma sola si `CASERO_SES_EVENTS_TOPIC_ARN` tiene el ARN del tema.
3. En la identidad del dominio en SES, enviar las notificaciones **Bounce** y **Complaint** a ese tema y desactivar el reenvío de avisos por correo.
4. Guardar el ARN en `/opt/casero/.env` como `CASERO_SES_EVENTS_TOPIC_ARN`.

## 3. Credenciales SMTP

En SES, crear credenciales SMTP (crean un usuario IAM propio) y guardarlas en Bitwarden y en `.env` como `CASERO_SMTP_USERNAME` y `CASERO_SMTP_PASSWORD`. El host es `email-smtp.us-east-1.amazonaws.com`, en el puerto 587 con STARTTLS.

## 4. Acceso de producción

Mientras la cuenta está en el sandbox, SES solo entrega a direcciones verificadas. Por eso la landing no se publica hasta tener acceso de producción (SPEC.md, "Antes de publicar la landing").

1. Pedirlo con la web ya en el dominio. El formulario pide:
   - la URL;
   - el tipo de correo: transaccional;
   - cómo se consigue cada dirección: el consumidor la escribe en el Libro de Reclamaciones y el arrendador al registrarse;
   - cómo se manejan los rebotes y las quejas: la sección 2.
2. AWS puede tardar hasta 96 horas en responder.

## 5. Pruebas antes de publicar

1. **Copia de un reclamo:** presentar un reclamo de prueba con una dirección propia que no esté verificada en SES y comprobar que llegan la copia y el aviso.
2. **Rebote:** enviar un correo a `bounce@simulator.amazonses.com` desde SES y comprobar que aparece una fila `bounce` en `email_suppressions`.
3. **Queja:** igual que el rebote, con `complaint@simulator.amazonses.com`.
4. **Registro:** anotar el resultado abajo.

## Registro

| Fecha | Acción | Resultado |
| --- | --- | --- |
| | | |
