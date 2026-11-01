# Publicar una nueva versión de un documento legal

Términos, privacidad y consentimiento de datos sensibles tienen versión. La aplicación pide aceptar la versión vigente antes de seguir: mientras falte, `current_account` responde 403 `legal_acceptance_required` y solo funcionan las rutas de derechos (AR-20).

Antes de publicar, revisa el texto con el abogado y **decide la fecha con anticipación**: la política de privacidad promete avisar por correo y en la aplicación antes de que la nueva versión rija.

1. **Guarda el texto anterior.** Copia el documento a `docs/legal/archive/<documento>-<versión>.md`, por ejemplo `docs/legal/archive/terms-0.1.md`. Quien lo aceptó debe poder volver a leerlo tal como estaba.
2. **Actualiza el documento.** Cambia el texto en `docs/legal/` y su línea "Versión X · Fecha de publicación: …".
3. **Regístralo en la web.** En `web/src/landing/legalDocuments.ts`, importa el archivo de `archive/` para la versión anterior y agrega la nueva al final: la última de la lista es la vigente. `legal.test.ts` comprueba que cada versión coincide con la que dice su texto.
4. **Agrega la fila.** Una migración de datos inserta la fila en `legal_documents`, con `published_at` en la fecha en que empieza a regir y `url` = `/legal/<ruta>/<versión>`. Hasta esa fecha nadie tiene que aceptarla.
5. **Avisa a los arrendadores.** Escríbeles antes de esa fecha, con lo que cambia y desde cuándo rige.

El consentimiento de datos sensibles merece más cuidado: al publicar una versión nueva, nadie puede usar la aplicación hasta darlo otra vez.
