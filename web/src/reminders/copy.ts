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
  templates: {
    title: "Mensajes de cobro",
    intro:
      "Estos son los mensajes que Casero te prepara para WhatsApp. Puedes cambiarlos; al enviarlos, Casero pone los datos de cada inquilino.",
    variables: "Puedes usar estas palabras entre llaves y Casero las reemplaza:",
    variableList: [
      ["{inquilino}", "el nombre del inquilino"],
      ["{monto}", "lo que falta pagar"],
      ["{periodo}", "el mes del alquiler"],
      ["{fecha}", "la fecha de pago"],
      ["{enlace}", "el enlace donde tu inquilino ve su cuenta"],
    ],
    kinds: {
      friendly: { title: "Recordatorio amable", when: "Se usa antes del día de pago." },
      due_today: { title: "Vence hoy", when: "Se usa el día de pago." },
      overdue: { title: "Atraso", when: "Se usa cuando el pago está atrasado." },
    },
    save: "Guardar mensaje",
    saving: "Guardando…",
    restore: "Volver al mensaje original",
    saved: "Listo, guardamos el mensaje.",
    loading: "Cargando tus mensajes…",
    failure: "No pudimos cargar tus mensajes. Vuelve a intentarlo en unos minutos.",
    back: "Volver al inicio",
    errors: {
      required: "Escribe el mensaje.",
      tooLong: "El mensaje puede tener hasta 1,000 caracteres.",
      unknownVariable: "Usa solo las palabras entre llaves de la lista.",
      failure: "No pudimos guardar el mensaje. Vuelve a intentarlo en unos minutos.",
    },
  },
} as const;
