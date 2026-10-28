export const leasesCopy = {
  list: {
    title: "Mis contratos",
    empty: "Todavía no registras contratos. Cuando registres uno, aquí verás a quién le alquilas cada unidad.",
    rent: (amount: string) => `${amount} al mes`,
    dueDay: (day: number) => `Paga el día ${String(day)} de cada mes`,
    since: (date: string) => `Desde el ${date}`,
    until: (date: string) => `Hasta el ${date}`,
    endsToday: "Termina hoy. Si lo renuevas, actualiza la fecha de fin.",
    endsIn: (days: number) =>
      `Termina en ${String(days)} ${days === 1 ? "día" : "días"}. Si lo renuevas, actualiza la fecha de fin.`,
    unsupported: "Este contrato no entra al cálculo de los formularios de SUNAT.",
    ended: (count: number) => `Terminados (${String(count)})`,
    unknownRenter: "Inquilino",
    unknownUnit: "Unidad",
    back: "Volver a mi cuenta",
  },
  errors: {
    paused: "Tu cuenta está pausada hasta que confirmes tu correo.",
    failure: "Algo salió mal. Vuelve a intentarlo en unos minutos.",
  },
} as const;
