export const taxCopy = {
  title: "Formularios de SUNAT",
  intro:
    "Un Formulario 1683 por cada inquilino que te pagó en el mes, sumando todos sus contratos. Preséntalo cuando termine el mes, no apenas cobres.",
  month: (month: string) => `Cobros de ${month}`,
  previousMonth: "Mes anterior",
  nextMonth: "Mes siguiente",
  loading: "Cargando tus formularios…",
  failure: "No pudimos cargar tus formularios. Vuelve a intentarlo en unos minutos.",
  notInPlan:
    "Los formularios de SUNAT son parte del plan Casero. Tus cobros siguen funcionando en el plan Gratis.",
  paused: "Tu cuenta está pausada. Vuelve al inicio para ver qué falta.",
  goHome: "Ir al inicio",
  unknownYear: (year: string) => `Todavía no tenemos las reglas de ${year}.`,
  due: {
    known: (date: string) => `Vencen el ${date}, según el último dígito de tu RUC.`,
    noRuc:
      "Registra tu RUC en Mis datos para ver la fecha límite. Si todavía no tienes RUC, lo sacas gratis en SUNAT con tu DNI.",
    unknownSchedule: (year: string) =>
      `Fecha por confirmar: SUNAT todavía no publica el cronograma de ${year}.`,
    goToProfile: "Ir a Mis datos",
  },
  total: (amount: string, count: number) =>
    count === 1
      ? `Total del mes: ${amount} en 1 Formulario 1683.`
      : `Total del mes: ${amount} en ${String(count)} formularios 1683, uno por inquilino.`,
  empty: (month: string) =>
    `No registraste cobros en ${month}, así que no hay formularios 1683 de ese mes.`,
  card: {
    company: "Inquilino empresa",
    companyNotice:
      "Tu inquilino es una empresa: necesita este pago hecho a tiempo para poder deducir el gasto.",
    incomplete: (name: string) =>
      `Falta el documento de ${name}. Sin él no puedes presentar este formulario.`,
    ruc: "RUC del arrendador",
    noRuc: "Falta tu RUC",
    period: "Período",
    docType: "Tipo de documento del inquilino",
    docNumber: "Número de documento del inquilino",
    propertyKind: "Tipo de bien",
    property: "Predio",
    base: "Monto de la renta",
    tax: "Tributo a pagar",
    collected: (amount: string) =>
      `Cobrado en el mes: ${amount}. El monto y el tributo se redondean a soles enteros.`,
    oldDebt: (amount: string) =>
      `Además cobraste ${amount} de deuda de 2025 o antes. No va en este formulario porque ese alquiler ya se gravó cuando venció; revísalo con tu contador.`,
    copy: "Copiar",
    // Acronyms like RUC keep their capitals; other labels read in lower case after "Copiar".
    copyLabel: (field: string) =>
      `Copiar ${/^\p{Lu}{2}/u.test(field) ? field : field.charAt(0).toLowerCase() + field.slice(1)}`,
    copied: (field: string) => `${field} copiado.`,
  },
  complete: {
    title: (name: string) => `Completa el documento de ${name}`,
    docType: "Tipo de documento",
    docNumber: "Número del documento",
    save: "Guardar documento",
    saving: "Guardando…",
    required: "Escribe el número del documento.",
    invalid: "Revisa el número del documento.",
    duplicate:
      "Ya registraste a otro inquilino con ese documento. Revisa que el número sea el correcto.",
    failure: "No pudimos guardar el documento. Vuelve a intentarlo en unos minutos.",
  },
  accountant: {
    title: "Para tu contador",
    intro: "Descarga los cobros y los formularios del año en archivos que se abren en Excel.",
    payments: (year: string) => `Cobros de ${year} (CSV)`,
    declarations: (year: string) => `Formularios de ${year} (CSV)`,
  },
  dueNotice: {
    today: (period: string, amount: string) =>
      `Hoy vencen tus formularios 1683 de ${period}: falta pagar ${amount}.`,
    tomorrow: (period: string, amount: string) =>
      `Mañana vencen tus formularios 1683 de ${period}: falta pagar ${amount}.`,
    soon: (period: string, date: string, days: number, amount: string) =>
      `Tus formularios 1683 de ${period} vencen el ${date} (en ${String(days)} días): falta pagar ${amount}.`,
    open: "Ver formularios",
    failure: "No pudimos revisar tus vencimientos de SUNAT. Vuelve a intentarlo en unos minutos.",
  },
  sunat: {
    title: "Pago a SUNAT",
    paid: (amount: string, date: string, order: string) =>
      `Pagaste ${amount} el ${date} · orden ${order}`,
    pending: (amount: string) => `Falta pagar ${amount}`,
    fullyPaid: "Pagado",
    record: "Registrar pago a SUNAT",
    amount: "Monto pagado en soles",
    paidOn: "Fecha en que pagaste",
    orderNumber: "Número de orden",
    orderHint: "Está en la constancia de pago de SUNAT.",
    save: "Guardar pago a SUNAT",
    saving: "Guardando…",
    cancel: "Cancelar",
    saved: "Listo, guardamos el pago a SUNAT.",
    void: "Anular",
    voidLabel: (amount: string) => `Anular el pago de ${amount}`,
    reason: "¿Por qué lo anulas?",
    confirmVoid: "Sí, anular",
    voided: "Listo, anulamos el pago a SUNAT.",
    errors: {
      amount: "Escribe el monto en soles, por ejemplo: 28 o 28.50.",
      paidOn: "Elige la fecha en que pagaste.",
      order: "Escribe solo los números de la orden.",
      reason: "Escribe el motivo.",
      paid_before_period: "La fecha no puede ser anterior al mes que declaras.",
      paid_in_future: "La fecha no puede ser posterior a hoy.",
      conflict:
        "Este pago ya se había guardado con otros datos. Revisa los pagos de la tarjeta y vuelve a intentarlo.",
      failure: "No pudimos guardar. Vuelve a intentarlo en unos minutos.",
    },
  },
  after: {
    up: (difference: string, period: string, taxDifference: string) =>
      `Cobraste ${difference} más en ${period} después de declarar. Presenta una declaración rectificatoria del 1683 con la nueva base y paga la diferencia de ${taxDifference} con intereses. Consúltalo con tu contador.`,
    down: (period: string) =>
      `La base de ${period} bajó después de declarar. Una rectificatoria que reduce el tributo la revisa SUNAT antes de surtir efecto; consulta con tu contador si conviene presentarla o pedir la devolución.`,
    document_changed:
      "Esta declaración se pagó con otro documento del inquilino. Ese dato no se corrige con una rectificatoria sino con el Formulario 1693 (solicitud de modificación de datos del pago). Revísalo con tu contador.",
    overdue_unpaid: (date: string) =>
      `Esta declaración venció el ${date}. Si la presentas y pagas antes de que SUNAT te notifique, la multa tiene una rebaja importante por gradualidad, y se pagan intereses. Consúltalo con tu contador.`,
  },
  docTypes: {
    dni: "DNI",
    ce: "Carné de extranjería",
    passport: "Pasaporte",
    ruc: "RUC",
  },
  untaxed: {
    title: "Contratos que Casero no calcula",
    line: (name: string, amount: string) => `${name}: cobraste ${amount}.`,
    explain:
      "Alquileres en dólares, subarriendos, sociedad conyugal que declara por mitades y otros casos especiales: Casero no arma su formulario. Consúltalo con tu contador.",
  },
  minimumRent: {
    title: "Alquiler por debajo del mínimo",
    line: (name: string) =>
      `El alquiler de ${name} está por debajo del mínimo que la ley presume según su autovalúo y la parte que alquilas.`,
    explain:
      "La diferencia no va en estos formularios: se paga en la declaración anual. Revísalo con tu contador.",
  },
  howTo: {
    title: "Cómo presentarlo y pagarlo",
    steps: [
      "Entra a SUNAT Operaciones en Línea con tu RUC y tu Clave SOL.",
      "Busca el Formulario Virtual 1683, el pago a cuenta por alquileres.",
      "Llena un formulario por cada tarjeta de esta página. Usa los botones para copiar los datos.",
      "Paga en línea con tu cuenta, tarjeta o Yape, o con el número de orden en un banco o agente.",
    ],
    neverSol: "Casero nunca te pide tu Clave SOL.",
  },
  disclaimer:
    "Casero calcula con los cobros que registraste. No presenta ni paga por ti; confírmalo con tu contador.",
} as const;
