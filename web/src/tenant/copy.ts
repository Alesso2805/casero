export const tenantCopy = {
  title: "Tu cuenta de alquiler",
  greeting: (renter: string, unit: string, landlord: string) =>
    `Hola, ${renter}. Alquilas ${unit} a ${landlord}.`,
  owes: (amount: string) => `Debes ${amount}`,
  inFavor: (amount: string) => `Tienes ${amount} a favor`,
  upToDate: "Estás al día",
  charges: "Cobros",
  payments: "Pagos",
  noPayments: "Todavía no hay pagos registrados.",
  partial: (paid: string, total: string) => `Pagaste ${paid} de ${total}`,
  privacyTitle: "Tus datos",
  privacy: (landlord: string, inbox: string) =>
    `${landlord} registró tu nombre y tus pagos de alquiler en Casero, una herramienta para llevar el control de los cobros. Se usan solo para eso: Casero los guarda por encargo de ${landlord} y no los comparte con nadie más. Para pedir que se corrijan o se borren, habla con ${landlord} o escribe a ${inbox}.`,
  loading: "Cargando…",
  errors: {
    link_not_found: "Este enlace no funciona o ya venció. Pide uno nuevo a quien te alquila.",
    portal_unavailable: "Este enlace no está disponible por ahora. Pregunta a quien te alquila.",
    too_many_requests: "Hubo demasiados intentos. Vuelve a intentarlo en una hora.",
    failure: "Algo salió mal. Vuelve a intentarlo en unos minutos.",
  },
} as const;
