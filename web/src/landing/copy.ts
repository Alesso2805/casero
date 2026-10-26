const dataController = "[nombre completo]";

export const copy = {
  hero: {
    title: "Cobra tus alquileres sin incomodarte y ten claro cuánto pagar a SUNAT cada mes",
    lead: "Registra tus alquileres una vez. Casero te muestra quién te debe y te arma el mensaje de cobro para WhatsApp. Cada mes te prepara los datos de tus formularios 1683, con el monto y la fecha límite.",
    notice: "Casero está en preparación y abrirá al público en 2027.",
    action: "Avísame cuando abra",
  },
  steps: {
    title: "Cómo funciona",
    items: [
      "Registra tus inmuebles, tus inquilinos y sus contratos.",
      "Mira quién está al día, quién te debe y cuánto.",
      "Casero arma el mensaje de cobro y tú lo envías desde tu WhatsApp. Luego anotas el pago.",
      "Al cerrar el mes, revisa tus formularios 1683: uno por cada inquilino que te pagó ese mes, con el monto y la fecha límite según tu RUC.",
    ],
  },
  limits: {
    title: "Lo que Casero no hace",
    body: "Casero no recibe el dinero de tus alquileres, nunca te pide tu Clave SOL, no presenta ni paga declaraciones por ti y no envía datos a SUNAT. Tú decides y pagas; Casero te ordena los datos.",
  },
  plans: {
    title: "Precios",
    note: "Precios desde la apertura, en soles y con impuestos incluidos.",
    items: [
      {
        name: "Gratis",
        price: "S/ 0",
        detail:
          "1 alquiler a la vez: ves quién te debe, anotas pagos, envías mensajes de cobro desde tu WhatsApp y tu inquilino ve su saldo con un enlace. No incluye los formularios 1683.",
      },
      {
        name: "Casero",
        price: "S/ 19 al mes o S/ 190 al año",
        detail:
          "Hasta 10 alquileres a la vez. Todo lo del plan Gratis, más tus formularios 1683 con su fecha límite y aviso por correo, constancias de pago para tu inquilino y un archivo con tus cobros para tu contador. Pagas por Yape y no se renueva solo.",
      },
    ],
    trial:
      "Prueba gratis: 30 días del plan Casero desde que creas tu cuenta. No pedimos tarjeta. Al terminar, si no pagas, pasas al plan Gratis y tus datos se guardan.",
  },
  waitlist: {
    title: "Te avisamos cuando abramos",
    emailLabel: "Tu correo electrónico",
    consentLabel: `Acepto que ${dataController}, responsable de Casero, use mi correo solo para avisarme cuando abra el registro. Lo guardará hasta que me registre o 12 meses como máximo, y puedo pedir que lo borre cuando quiera.`,
    privacyLink: "Ver la política de privacidad.",
    submit: "Avisarme",
    sending: "Enviando…",
    success: "¡Listo! Te escribiremos a este correo cuando abramos.",
    invalidEmail:
      "Ese correo parece incompleto. Revisa que tenga @ y un punto, por ejemplo: nombre@gmail.com.",
    missingConsent: "Marca la casilla para que podamos escribirte.",
    tooManyAttempts: "Recibimos muchos intentos desde tu conexión. Vuelve a intentarlo en una hora.",
    failure: "No pudimos guardar tu correo. Vuelve a intentarlo en unos minutos.",
  },
  footer: {
    privacy: "Política de privacidad",
    disclaimer:
      "Casero es una herramienta de registro y cálculo. No es asesoría tributaria ni legal y no reemplaza a tu contador. El cálculo depende de los datos que registres.",
  },
  privacyBack: "Volver al inicio",
} as const;
