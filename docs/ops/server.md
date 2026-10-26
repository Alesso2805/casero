# Servidor (Google Cloud y DuckDNS)

Decisión (25 de octubre de 2026):

- Una VM de Compute Engine **e2-small** (2 vCPU compartidas, 2 GB de RAM) en **us-east1** (Carolina del Sur, EE. UU.), con disco pd-balanced de 20 GB.
- IP externa estática en el nivel de red **Standard**.
- Un subdominio de **DuckDNS** para la web.
- País que se declara ante la Autoridad: **EE. UU.**

Costo estimado: unos US$ 18 al mes (VM US$ 12.23, disco US$ 2.00, IP US$ 3.65). En el nivel Standard, los primeros 200 GiB de salida al mes son gratis. Si un día falta memoria, se pasa a e2-medium: se detiene la VM, se cambia el tipo y se vuelve a iniciar.

El correo no sale desde DuckDNS, porque no permite los registros que pide Amazon SES. Usa un dominio propio comprado solo para el correo (ver SPEC.md, Proveedores).

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
   CASERO_SMTP_HOST=email-smtp.us-east-1.amazonaws.com
   CASERO_SMTP_USERNAME=<usuario SMTP de SES>
   CASERO_SMTP_PASSWORD=<contraseña SMTP de SES>
   CASERO_MAIL_FROM=Casero <no-reply@<dominio del correo>>
   CASERO_BUSINESS_NAME=<nombre completo según el RUC>
   CASERO_BUSINESS_RUC=<RUC>
   CASERO_BUSINESS_ADDRESS=<domicilio fiscal>
   CASERO_COMPLAINTS_INBOX=<correo donde llegan los avisos de reclamos>
   CASERO_DOMAIN=<subdominio>.duckdns.org
   CASERO_TLS=<correo para los avisos de Let's Encrypt>
   ```
   El usuario y la contraseña SMTP se crean en SES (credenciales SMTP de la región us-east-1) y también van a Bitwarden. Los datos del negocio aparecen en la copia de cada reclamo.

## 3. DuckDNS

1. Entrar a duckdns.org, crear el subdominio y apuntarlo a la IP estática (`gcloud compute addresses describe casero-ip --region=us-east1`).
2. Guardar el token de DuckDNS en Bitwarden. El servidor no lo necesita, porque la IP es fija.
3. Antes del primer despliegue, comprobar que la consulta CAA del subdominio no devuelve SERVFAIL (`dig CAA <subdominio>.duckdns.org`). Si lo devuelve, Let's Encrypt no emite el certificado. Caddy intenta además con ZeroSSL, y los registros de Caddy lo muestran en el primer arranque.

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
