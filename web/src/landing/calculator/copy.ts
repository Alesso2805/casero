export const calculatorCopy = {
  title: "¿Cuánto pago a SUNAT por mi alquiler?",
  intro:
    "Calcula el pago mensual por cada inquilino según lo que le cobraste en el mes. No necesitas registrarte y no guardamos los montos.",
  month: "Mes en que cobraste",
  year: "Año",
  months: [
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
  ],
  amountsTitle: "Lo que cobraste a cada inquilino en ese mes",
  renter: (index: number) => `Inquilino ${String(index)} (S/)`,
  remove: (index: number) => `Quitar inquilino ${String(index)}`,
  add: "Agregar otro inquilino",
  rucGroup: "Último dígito de tu RUC (opcional)",
  rucGroupHint: "Con este dato te mostramos la fecha límite de pago.",
  rucGroupNone: "No lo sé o no tengo RUC",
  goodTaxpayer: "Soy buen contribuyente",
  calculate: "Calcular",
  calculating: "Calculando…",
  result: {
    title: "Tu pago del mes",
    renter: "Inquilino",
    collected: "Cobrado",
    tax: "Pago a SUNAT",
    total: (amount: string, count: number) =>
      count === 1
        ? `Total del mes: ${amount} en 1 Formulario 1683.`
        : `Total del mes: ${amount} en ${String(count)} formularios 1683, uno por inquilino.`,
    dueOn: (date: string) => `Vence el ${date}, según el último dígito de tu RUC.`,
    noSchedule: (year: string) => `SUNAT todavía no publica el cronograma de ${year}.`,
    askRuc: "Indica el último dígito de tu RUC para ver la fecha límite.",
    rate: (effective: string, rate: string, net: string) =>
      `Se paga el ${effective} % de lo que cobras: ${rate} % sobre el ${net} % de lo cobrado, redondeado a soles enteros.`,
    disclaimer:
      "Es un cálculo referencial con las reglas vigentes. Casero no presenta ni paga declaraciones por ti; confírmalo con tu contador.",
  },
  waitlistTitle: "¿Quieres que Casero te recuerde cada formulario a tiempo?",
  errors: {
    amount: "Escribe el monto en soles, por ejemplo: 850 o 850.50.",
    unknownYear: (year: string) => `Todavía no tenemos las reglas de ${year}. Elige otro mes.`,
    tooManyAttempts: "Hiciste muchos cálculos seguidos. Vuelve a intentarlo en una hora.",
    failure: "No pudimos calcular. Vuelve a intentarlo en unos minutos.",
  },
} as const;
