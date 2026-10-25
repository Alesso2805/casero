# Servidor

El servidor se contrata antes de presentar la solicitud ante la Autoridad (semana del 2 al 8 de noviembre de 2026), porque esa solicitud declara el país donde quedan los datos. Se declara el país del servidor que de verdad se contrate.

## Regla para elegirlo

Se toma la primera opción disponible, en este orden:

1. Hetzner Cloud CX33 (4 vCPU x86, 8 GB, 80 GB) en Nuremberg (Alemania) o Helsinki (Finlandia).
2. Cualquier plan cloud de Hetzner en Alemania o Finlandia con 4 GB de RAM o más y menos de € 15 al mes, primero x86 (CX) y después ARM (CAX).
3. Si no hay nada en Hetzner, un VPS x86 de OVHcloud, solo en un datacenter de Francia. En ese caso se declara Francia.

x86 va antes que ARM porque con un servidor ARM CI tendría que construir las imágenes para arm64.

## Opciones al 25 de octubre de 2026

Precios sin IVA. En Hetzner incluyen la IPv4.

| Opción | Plan | vCPU, RAM y disco | Precio al mes | Ubicaciones | Estado |
| --- | --- | --- | --- | --- | --- |
| 1 | Hetzner CX33 | 4 x86, 8 GB, 80 GB | € 8.99 | Nuremberg, Helsinki | No disponible |
| 2 | Hetzner CX23 | 2 x86, 4 GB, 40 GB | € 5.99 | Nuremberg, Helsinki | No disponible |
| 2 | Hetzner CAX11 | 2 ARM, 4 GB, 40 GB | € 6.49 | Nuremberg, Helsinki | No disponible |
| 2 | Hetzner CAX21 | 4 ARM, 8 GB, 80 GB | € 10.99 | Nuremberg, Helsinki | No disponible |
| 3 | OVHcloud VPS-1 | 2 vCores, 4 GB, 40 GB | desde € 3.81 | Francia, por confirmar en el configurador | Por revisar al contratar |
| 3 | OVHcloud VPS-2 | 4 vCores, 8 GB, 75 GB | desde € 7.21 | Francia, por confirmar en el configurador | Por revisar al contratar |

- Hetzner tiene abierto desde el 26 de junio de 2026 un aviso de disponibilidad limitada de servidores cloud.
- Hetzner no ofrece el CX33 en Falkenstein.
- Su CX43 (€ 16.49) y su CPX22 (€ 19.99) superan el tope de la opción 2.
- Los precios "desde" de OVHcloud parecen suponer un pago adelantado de 12 meses; se confirma al contratar.

## Al contratar

1. Elegir el servidor según la regla y anotarlo en el registro de abajo.
2. Activar el doble factor en la cuenta del proveedor y guardar las credenciales en Bitwarden.
3. Configurar el acceso SSH solo con llave (la llave vive en Bitwarden), sin contraseñas y sin acceso de root por SSH.
4. Abrir en el firewall solo los puertos 22, 80 y 443. El puerto del panel interno queda ligado a `127.0.0.1` (ADR-0008).
5. No contratar las copias de seguridad del proveedor: la restauración parte de los respaldos en B2.
6. Declarar el país ante la Autoridad. Actualizar la tabla de proveedores de SPEC, la política de privacidad y la tabla de costos de BUSINESS.md con el plan real.

CS-04 instala sobre este servidor la configuración definitiva.

## Registro

| Fecha | Proveedor y plan | Ubicación | País declarado | Quién |
| --- | --- | --- | --- | --- |
| | | | | |
