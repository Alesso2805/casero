# Preguntas para el abogado

Reunidas al redactar los borradores de octubre de 2026. Cada una indica el documento afectado y su fuente. Se responden antes de publicar la landing o, como máximo, antes de la beta.

## Términos y condiciones (`terms.md`)

1. **Consumidor.** ¿El arrendador que usa Casero es consumidor según el art. IV del Código (Ley N.° 29571)? Los borradores asumen que sí y se redactan como contrato de consumo.
2. **Devoluciones.** ¿Qué política de devoluciones conviene, incluida la promesa de la preventa (devolución si no hay beta antes del 31 de mayo de 2027)?
3. **Suspensión.** ¿Las causas de la sección 7 bastan frente al art. 50.b–c del Código y el art. 1430 del Código Civil?
4. **Responsabilidad.** ¿Es válido algún límite de responsabilidad frente a usuarios que no sean consumidores?
5. **Jurisdicción.** ¿Conviene una cláusula de jurisdicción o arbitraje sin limitar los derechos del art. 50.f–g?
6. **Comprobante.** ¿Cómo se redacta el comprobante y el IGV en el Nuevo RUS? (también para el contador)
7. **Encargo.** ¿Basta con que el encargo de tratamiento de los datos de los inquilinos sea un anexo de los términos aceptado con un clic, o debe ser un documento aparte (Reglamento, art. 32.2)?

## Datos personales (`privacy.md`, `sensitive-consent.md`)

8. **Forma del consentimiento.** ¿Un clic en una casilla sin marcar, registrado con fecha y una huella de la IP, cumple el "por escrito" del art. 13.6 de la Ley N.° 29733 para datos sensibles, o hace falta un código por correo o escribir el nombre?
9. **Base del consentimiento.** Como los ingresos son indispensables para el servicio, ¿aplica la excepción de ejecución del contrato (art. 14.5)? El borrador pide el consentimiento igual.
10. **Bloqueo tras retirar el consentimiento.** ¿Cuánto tiempo puede quedar bloqueada la cuenta antes de borrar sus datos (Reglamento, art. 10)?
11. **Trazabilidad.** El Reglamento (art. 46.3) pide conservar registros de trazabilidad al menos 2 años, y el SPEC purga el `audit_log` de una cuenta 30 días después de eliminarla. ¿Aplica a Casero y qué debe conservarse?
12. **Constancia de aceptación.** ¿Cuánto tiempo conservar la huella de IP y la fecha de las aceptaciones después de eliminar la cuenta?
13. **Supresiones de correo.** ¿Qué base legal tiene guardar la huella de un correo que rebotó o se quejó, y por cuánto tiempo?
14. **Transferencias internacionales.** ¿Bastan los acuerdos de tratamiento de datos estándar de Google, Backblaze, AWS y Sentry, o hacen falta las cláusulas modelo aprobadas por la Autoridad (R.D. N.° 74-2022)?
15. **Comunicación del flujo transfronterizo.** ¿Quién comunica a la Autoridad el flujo de los datos de los inquilinos: Casero o cada arrendador (art. 21.2)?
16. **Aviso a los inquilinos.** Cuando los datos vienen del arrendador, ¿quién da al inquilino la información del art. 6.2: el arrendador o Casero en el portal?
17. **Banco de datos del arrendador.** ¿Un arrendador persona natural debe inscribir su propio banco de datos de inquilinos (art. 42)?
18. **Oficial de datos personales.** Para una microempresa es obligatorio desde el 30 de noviembre de 2028. ¿Conviene designarlo ya y comunicarlo a la Autoridad?

## Libro de Reclamaciones

19. **Libro físico de respaldo.** ¿Un negocio solo en línea necesita además un libro físico? Las preguntas frecuentes de INDECOPI dicen que sí; el art. 4-A lo liga a los establecimientos. Mientras tanto se guarda uno en el domicilio fiscal.
20. **Domicilio.** ¿Basta la dirección web como "domicilio del establecimiento" de la hoja (art. 3.2), o hay que mostrar el domicilio fiscal?
21. **Nuevo reglamento.** ¿Ya se aprobó el proyecto publicado con la R.M. N.° 244-2026-PCM (18 de julio de 2026)? Si se aprobó, ¿qué cambia en el formulario?

## Contratos de alquiler

22. **Contrato vencido.** Si el inquilino sigue en el inmueble y pagando después de la fecha de fin, ¿el arrendamiento continúa (art. 1700 del Código Civil)? Hoy Casero cierra el contrato en su fecha de fin si el arrendador no la extiende. ¿Conviene, en cambio, dejarlo activo como "vencido" hasta que el arrendador lo termine?

## Portal del inquilino

23. **Aviso en el portal del inquilino.** ¿Basta este texto para cumplir el art. 18 de la Ley N.° 29733 cuando los datos del inquilino los registra el arrendador? "{arrendador} registró tu nombre y tus pagos de alquiler en Casero, una herramienta para llevar el control de los cobros. Se usan solo para eso: Casero los guarda por encargo de {arrendador} y no los comparte con nadie más. Para pedir que se corrijan o se borren, habla con {arrendador} o escribe a {correo de privacidad}." (CS-18)
