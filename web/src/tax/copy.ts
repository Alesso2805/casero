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
    copyLabel: (field: string) => `Copiar ${field.toLowerCase()}`,
    copied: (field: string) => `${field} copiado.`,
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
