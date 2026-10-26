# Configuración tributaria por año

Las reglas del impuesto, la UIT, el cronograma de SUNAT y los feriados viven solo en `infra/seed/tax/{año}.yaml` (CLAUDE.md, regla 6). Cada sección (`rules`, `due_dates`, `holidays`) lleva su `source_url`, y el cargador rechaza el archivo si falta.

## Cómo se carga

- 2026 se carga en la migración 0006.
- El migrador, en cada arranque y después de las migraciones, carga con upsert todos los archivos como `casero_owner` (`python -m casero.tax.infrastructure.tax_config`). Corregir un valor es editar el YAML y desplegar.
- En local: `make load-tax-config`.
- Un día o un período que se quita del YAML no se borra de la base. Si hace falta, se corrige con una migración.

## Calendario anual

| Cuándo | Qué | Fuente |
| --- | --- | --- |
| Diciembre | `rules` del año siguiente con la nueva UIT (`uit_cents`) y cualquier cambio de tasa o umbral | Decreto supremo de la UIT (El Peruano) y la LIR |
| Diciembre | Revisar los `holidays` del año siguiente, ya cargados desde la ley; confirmar Jueves y Viernes Santo y cualquier feriado nuevo | gob.pe/feriados y El Peruano |
| Enero o febrero | `due_dates` del año, cuando SUNAT publique su página del cronograma | `sunat.gob.pe/orientacion/cronogramas/{año}/cObligacionMensual{año}.html` |
| Antes de cargar | Validar los valores con el contador | — |

Mientras falte el cronograma de un año, Casero muestra "fecha por confirmar" y el worker avisa (CS-21 y CS-26).

`test_every_2026_due_date_follows_the_sunat_rule` comprueba que cada vencimiento sea el día hábil que fija la R.S. N.° 000281-2022/SUNAT. Al agregar un año, se extiende a ese año.

## Pendiente con el contador

- **Redondeo de la base.** Casero redondea a soles enteros la base y luego el tributo, como en los ejemplos del SPEC (450.50 + 100.50 → base 551, tributo 28). La R.S. N.° 025-2000/SUNAT solo exige enteros en el tributo de las declaraciones por internet, y con 549.50 cobrados los dos métodos dan 28 y 27. El contador confirma el método antes de la beta. Si cambia, se cambia `rounding` en el YAML.

## Registro

| Fecha | Archivo | Cambio | Validado por |
| --- | --- | --- | --- |
| 2026-10-26 | 2026.yaml | Carga inicial: reglas, 84 vencimientos y 16 feriados | Pendiente |
| 2026-10-26 | 2027.yaml | Solo feriados | Pendiente |
