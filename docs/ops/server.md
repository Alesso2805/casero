# Servidor y dominio (Google Cloud y un dominio .com)

Decisión (25 de octubre de 2026):

- Una VM de Compute Engine **e2-small** (2 vCPU compartidas, 2 GB de RAM) en **us-east1** (Carolina del Sur, EE. UU.), con disco pd-balanced de 20 GB.
- IP externa estática en el nivel de red **Standard**.
- Un dominio **.com** propio para la web y el correo (decisión del 26 de octubre de 2026, que reemplaza a DuckDNS).
- País que se declara ante la Autoridad: **EE. UU.**

Costo estimado: unos US$ 18 al mes (VM US$ 12.23, disco US$ 2.00, IP US$ 3.65). En el nivel Standard, los primeros 200 GiB de salida al mes son gratis. Si un día falta memoria, se pasa a e2-medium: se detiene la VM, se cambia el tipo y se vuelve a iniciar.

El dominio cuesta unos US$ 10 al año. La web va en el dominio raíz y el correo de SES sale de un subdominio propio (ver SPEC.md, Proveedores).

## 1. Crear la VM (una vez)

Desde Cloud Shell o con `gcloud` instalado y autenticado:

```sh
gcloud config set project <proyecto>
gcloud compute addresses create casero-ip --region=us-east1 --network-tier=STANDARD
gcloud compute instances create casero \
  --zone=us-east1-b --machine-type=e2-small \
  --image-family=debian-13 --image-project=debian-cloud \
  --boot-disk-size=20GB --boot-disk-type=pd-balanced \
  --network-tier=STANDARD --address=casero-ip --tags=casero-web
gcloud compute firewall-rules create casero-web \
  --allow=tcp:80,tcp:443,udp:443 --target-tags=casero-web
```

La red por defecto ya permite SSH (puerto 22). El acceso es solo con llave.

## 2. Preparar la VM

Conectarse con `gcloud compute ssh casero --zone=us-east1-b` y:

1. Crear 2 GB de swap, para que PostgreSQL y la API no se queden sin memoria en picos:
   ```sh
   sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
   sudo mkswap /swapfile && sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```
2. Instalar Docker Engine con el plugin de Compose desde el repositorio oficial de Docker para Debian.
3. Activar las actualizaciones de seguridad automáticas: `sudo apt install unattended-upgrades`.
4. Crear el usuario del despliegue y su carpeta:
   ```sh
   sudo adduser --disabled-password --gecos "" casero
   sudo usermod -aG docker casero
   sudo install -d -o casero -g casero /opt/casero
   ```
5. Comprobar en `/etc/ssh/sshd_config` que estén `PasswordAuthentication no` y `PermitRootLogin no`.
6. Crear `/opt/casero/.env`, con permisos 600 y dueño `casero`. Las contraseñas son alfanuméricas de 32 caracteres y se guardan en Bitwarden:
   ```
   POSTGRES_PASSWORD=...
   CASERO_OWNER_PASSWORD=...
   CASERO_BACKUP_PASSWORD=...
   CASERO_APP_PASSWORD=...
   CASERO_WORKER_PASSWORD=...
   CASERO_ADMIN_PASSWORD=...
   CASERO_RATE_LIMIT_KEY=...
   CASERO_EMAIL_HASH_KEY=...
   CASERO_UNSUBSCRIBE_KEY=...
   CASERO_ACCEPTANCE_IP_KEY=...
   CASERO_ENCRYPTION_KEYS=k1:<32 bytes en base64url>
   CASERO_ENCRYPTION_ACTIVE_KEY=k1
   CASERO_DOC_HMAC_KEY=<32 bytes en base64url>
   REGISTRATION_MODE=closed
   CASERO_SES_EVENTS_TOPIC_ARN=<ARN del tema SNS de rebotes y quejas>
   CASERO_SMTP_HOST=email-smtp.us-east-1.amazonaws.com
   CASERO_SMTP_USERNAME=<usuario SMTP de SES>
   CASERO_SMTP_PASSWORD=<contraseña SMTP de SES>
   CASERO_MAIL_FROM=Casero <no-reply@<dominio>.com>
   CASERO_BUSINESS_NAME=<nombre completo según el RUC>
   CASERO_BUSINESS_RUC=<RUC>
   CASERO_BUSINESS_ADDRESS=<domicilio fiscal>
   CASERO_COMPLAINTS_INBOX=<cuenta de Gmail exclusiva de Casero>
   CASERO_ALERTS_INBOX=<tu correo para las alertas del worker; vacío solo las deja en Sentry>
   CASERO_DOMAIN=<dominio>.com
   CASERO_TLS=<correo para los avisos de Let's Encrypt>
   SENTRY_DSN=<DSN del proyecto de Sentry; vacío lo apaga>
   ```
   `CASERO_EMAIL_HASH_KEY` no se cambia nunca: las supresiones de correo solo guardan su HMAC (ADR-0010). Tampoco `CASERO_DOC_HMAC_KEY`: agrupa las declaraciones y los pagos a SUNAT de solo inserción (ADR-0007). Las claves de 32 bytes se generan con `python -c "import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`; para rotar el cifrado se agrega otra clave a `CASERO_ENCRYPTION_KEYS` (`k1:...,k2:...`), se activa y, cuando un trabajo vuelve a cifrar las columnas, se retira la anterior. El usuario y la contraseña SMTP se crean en SES (credenciales SMTP de la región us-east-1) y también van a Bitwarden. Los datos del negocio aparecen en el Libro de Reclamaciones, en la copia de cada reclamo y en el aviso de la lista de espera; viven solo en el servidor, nunca en el repositorio. En el proyecto de Sentry se activan el «Data Scrubber» y «Use Default Scrubbers» como segunda capa (ADR-0011).

## 3. Dominio

1. Antes de comprarlo, revisar que el nombre esté libre como dominio y como marca (SPEC.md, "Antes de comprar el dominio").
2. Comprarlo con la **privacidad del WHOIS** activada, para que el registrador no publique tu domicilio. Guardar el acceso en Bitwarden.
3. Registros DNS:

   | Nombre | Tipo | Valor |
   | --- | --- | --- |
   | `@` | A | la IP estática (`gcloud compute addresses describe casero-ip --region=us-east1`) |
   | `www` | CNAME | `<dominio>.com` (Caddy redirige `www` al dominio raíz) |
   | `@` | TXT | `v=spf1 -all` (ningún correo sale con el dominio raíz como remitente del sobre) |
   | `_dmarc` | TXT | `v=DMARC1; p=none; rua=mailto:<cuenta de Gmail de Casero>`; se sube a `p=quarantine` cuando los informes salgan limpios |
   | 3 × `<token>._domainkey` | CNAME | los tres registros DKIM que da SES al verificar el dominio |
   | `mail` | MX | `10 feedback-smtp.us-east-1.amazonses.com` (MAIL FROM propio de SES) |
   | `mail` | TXT | `v=spf1 include:amazonses.com -all` |

   - Sin registro AAAA: la IP estática es solo IPv4.
   - Si se agrega un registro CAA, debe permitir `letsencrypt.org` y `sectigo.com`, porque Caddy recurre a ZeroSSL cuando Let's Encrypt falla.
   - HSTS va sin `includeSubDomains` ni `preload`.
4. Con la web ya en el dominio, pedir a SES el acceso de producción con la URL del dominio. AWS puede tardar hasta 96 horas en responder, así que se hace mientras el abogado revisa los textos.

## 4. Despliegue automático (GitHub)

1. Generar una llave solo para el despliegue: `ssh-keygen -t ed25519 -f casero-deploy -C github-actions`.
2. Agregar `casero-deploy.pub` a `/home/casero/.ssh/authorized_keys` en la VM y guardar la llave privada en Bitwarden.
3. Crear en el repositorio el entorno `production`:
   - Secreto `DEPLOY_SSH_KEY`: la llave privada.
   - Secreto `DEPLOY_KNOWN_HOSTS`: la línea de `ssh-keyscan <ip>`, comparada antes con la huella que muestra `gcloud compute ssh`.
   - Variables `DEPLOY_HOST` (la IP), `DEPLOY_USER` (`casero`) y `CASERO_DOMAIN`.
4. Crear la variable de repositorio `DEPLOY_ENABLED=true`.

Desde ese momento, cada fusión en `main` con el CI en verde:

1. construye las imágenes y las publica en GHCR;
2. copia `infra/deploy/docker-compose.yml` y los scripts de roles a `/opt/casero`;
3. levanta la versión nueva con la etiqueta del commit (guardada en `/opt/casero/image.env`);
4. comprueba `https://<dominio>/api/health`.

Para volver a una versión anterior, se ejecuta en `/opt/casero`:

```sh
printf 'IMAGE_TAG=<sha>\n' > image.env
docker compose --env-file .env --env-file image.env up --detach
```

## Registro

| Fecha | Acción | Quién |
| --- | --- | --- |
| | | |
