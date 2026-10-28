export const collectionsCopy = {
  title: "Quién te debe",
  loading: "Cargando tus cobros…",
  dueByMonthEnd: (amount: string) => `Por cobrar hasta fin de mes: ${amount}`,
  overdueTotal: (amount: string) => `De eso, ${amount} ya está atrasado.`,
  groups: {
    overdue: "Atrasados",
    due_today: "Vencen hoy",
    due_soon: "Por vencer",
    up_to_date: "Al día",
  },
  overdue: (amount: string, days: number) =>
    `Debe ${amount} · ${String(days)} ${days === 1 ? "día" : "días"} de atraso`,
  dueToday: (amount: string) => `Hoy vence ${amount}`,
  dueSoon: (amount: string, date: string) => `${amount} vence el ${date}`,
  nextDue: (amount: string, date: string) => `Próximo cobro: ${amount} el ${date}`,
  inFavor: (amount: string) => `Tiene ${amount} a favor`,
  nothingDue: "Sin cobros pendientes",
  ended: "Contrato terminado",
  empty: "Cuando registres un contrato, aquí verás quién te debe y cuánto.",
  addLease: "Registrar un contrato",
  failure: "No pudimos cargar tus cobros. Vuelve a intentarlo en unos minutos.",
} as const;
