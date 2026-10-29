export const remindersCopy = {
  send: "Enviar por WhatsApp",
  sendTo: (name: string) => `Enviar por WhatsApp a ${name}`,
  sending: "Preparando el mensaje…",
  hint: "Te abrimos WhatsApp con el mensaje listo; puedes cambiarlo antes de enviarlo. Mejor entre las 8:00 y las 20:00.",
  errors: {
    whatsapp_unavailable:
      "Este contrato no tiene WhatsApp ni enlace del inquilino en tu plan actual.",
    nothing_due: "No hay un alquiler pendiente que recordar.",
    failure: "No pudimos preparar el mensaje. Vuelve a intentarlo en unos minutos.",
  },
} as const;
