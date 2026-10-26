# Política de privacidad de Casero

> **Borrador para revisión del abogado. No publicar todavía.**
> Versión 0.1 · Fecha de publicación: [fecha de publicación]
> Esta es la política de la aplicación. Mientras Casero está en preparación, la landing usa la versión corta (`privacy-short.md`). Las dudas para el abogado están en `docs/legal/lawyer-questions.md`.

## 1. Quién es responsable de tus datos

[nombre completo según el RUC], persona natural con negocio, RUC [RUC], con domicilio en [domicilio], es responsable de los datos que tratamos para darte Casero.

- **Oficial de datos personales:** [nombre completo según el RUC], en [correo de privacidad].
- **Banco de datos:** "[nombre del banco de datos]", inscrito ante la Autoridad Nacional de Protección de Datos Personales con el código [código de inscripción].

Los datos de tus inquilinos que registras en Casero son tuyos: tú eres su responsable y nosotros los tratamos por tu encargo, como dice el Anexo de los términos y condiciones.

## 2. Qué datos tratamos, para qué y por cuánto tiempo

| Cuándo | Qué datos | Para qué | Por qué podemos | Cuánto tiempo |
| --- | --- | --- | --- | --- |
| Creas tu cuenta | Tu correo, el nombre que eliges mostrar y tu contraseña, que guardamos transformada (Argon2id) y nunca en texto legible | Darte acceso a tu cuenta | El contrato contigo | Mientras tengas la cuenta |
| Aceptas los documentos | La versión de cada documento, la fecha y una huella cifrada de tu dirección IP en ese momento (no la IP) | Probar qué aceptaste y cuándo | El contrato y nuestra obligación de probar tu consentimiento | Mientras tengas la cuenta [⚑ plazo después de eliminarla] |
| Usas la aplicación | Un identificador de sesión en una cookie (guardamos solo su huella), la fecha de tu último uso | Mantenerte conectado de forma segura | El contrato | Hasta que cierres sesión o pasen 30 días sin usarla |
| Registras tu perfil tributario | Tu RUC, el grupo de vencimientos y el tipo de declarante | Calcular la fecha límite de tus formularios | El contrato | Mientras tengas la cuenta |
| Registras tus alquileres | Tus inmuebles, contratos, cobros, deudas, garantías y pagos a SUNAT. **Tus ingresos por alquiler son datos sensibles** | Calcular saldos, preparar tus formularios 1683, enviarte recordatorios y darte la exportación | Tu consentimiento expreso, que das por separado | Mientras tengas la cuenta |
| Pagas tu suscripción | El monto, la fecha, el medio de pago y el número de boleta | Emitir tus comprobantes y cumplir nuestras obligaciones tributarias | La ley | [plazo que indique el contador; propuesta: 5 años] |
| Presentas un reclamo | Lo que pide la Hoja de Reclamación | Responder tu reclamo | La ley (Código de Protección y Defensa del Consumidor) | 2 años desde que lo presentas |
| Un correo nuestro rebota o lo marcas como spam | Una huella cifrada de tu dirección de correo, no la dirección | No volver a enviarte correos que no llegan o que no quieres | Nuestro interés en no enviar correo no deseado [⚑ base legal] | Mientras exista Casero, salvo que nos pidas borrarla |
| Usas la calculadora o el formulario de reclamos | No guardamos tu IP: para limitar abusos usamos una huella cifrada con una clave que cambia cada día | Evitar abusos | Nuestro interés en proteger el servicio | Menos de 24 horas |

Si eliminas tu cuenta, sus datos se borran a los 30 días y desaparecen de las copias de seguridad en otros 30 días. Solo conservamos los pagos de tu suscripción, con la cuenta anonimizada, porque la ley tributaria nos obliga.

**Qué datos son obligatorios:** el correo, la contraseña, el nombre, la aceptación de los documentos y el consentimiento para tus ingresos por alquiler. Sin ellos no podemos crear tu cuenta. El RUC es opcional hasta que uses los formularios de SUNAT.

**Decisiones automatizadas:** Casero calcula montos y fechas, pero no toma decisiones sobre ti ni hace perfiles.

## 3. Con quién compartimos tus datos

No vendemos tus datos ni los cedemos a nadie para su propio uso. Los guardan por encargo nuestro estos proveedores, que no pueden usarlos para otra cosa:

| Servicio | Proveedor y domicilio | País |
| --- | --- | --- |
| Servidor | Google LLC, 1600 Amphitheatre Parkway, Mountain View, CA 94043 | Estados Unidos |
| Almacenamiento y copias de seguridad | Backblaze, Inc., 201 Baldwin Ave., San Mateo, CA 94401 | Estados Unidos |
| Envío de correos | Amazon Web Services, Inc., 410 Terry Avenue North, Seattle, WA 98109 | Estados Unidos |
| Registro de errores técnicos, sin datos personales | Functional Software, Inc. (Sentry), 45 Fremont Street, 8th Floor, San Francisco, CA 94105 | Estados Unidos |
| Correo de atención y reclamos | Google LLC (Gmail), 1600 Amphitheatre Parkway, Mountain View, CA 94043 | Estados Unidos |

Como estos proveedores están en Estados Unidos, tus datos viajan fuera del Perú. Lo hacemos para cumplir el contrato contigo y con las garantías de los acuerdos de tratamiento de datos de cada proveedor [⚑ cláusulas modelo]. Este flujo transfronterizo está comunicado a la Autoridad.

Solo entregamos datos a una autoridad cuando la ley nos obliga.

## 4. Cookies

Usamos solo las cookies necesarias para que Casero funcione: la de tu sesión y la que protege tus formularios contra ataques (CSRF). No usamos cookies de publicidad ni de analítica.

## 5. Cómo protegemos tus datos

Cifrado en la conexión y en las copias de seguridad, cifrado del documento de identidad de tus inquilinos, separación estricta entre cuentas, sesiones que puedes cerrar desde cualquier dispositivo y registros técnicos sin datos personales. Si ocurre un incidente que afecte tus derechos, te avisamos sin demora y lo comunicamos a la Autoridad en un máximo de 48 horas.

## 6. Tus derechos

Puedes pedir, gratis, en cualquier momento:

- **Información y acceso:** saber qué datos tenemos y cómo los usamos.
- **Rectificación:** corregir los que estén mal; casi todos puedes corregirlos tú mismo en la aplicación.
- **Cancelación:** que borremos tus datos; puedes eliminar tu cuenta desde la aplicación.
- **Oposición:** que dejemos de usarlos para un fin concreto.
- **Portabilidad:** descargar tus datos en un formato que puedes abrir en otros programas, desde la aplicación.
- **Retirar tu consentimiento** para tus ingresos por alquiler: tu cuenta quedará bloqueada salvo para exportar o eliminar tus datos.

Escríbenos a [correo de privacidad]. Respondemos en 8 días hábiles si pides información, en 20 si pides acceso y en 10 en los demás casos; si necesitamos más tiempo, te lo decimos una sola vez. Si no estás de acuerdo con nuestra respuesta, puedes reclamar ante la Autoridad Nacional de Protección de Datos Personales del Ministerio de Justicia y Derechos Humanos.

## 7. Cambios a esta política

Si la cambiamos, te avisamos por correo y en la aplicación antes de que la nueva versión rija, y te pedimos que la aceptes para seguir usando Casero.
