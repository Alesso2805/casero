export const accountCopy = {
  fields: {
    displayName: "¿Cómo te llamamos?",
    email: "Tu correo electrónico",
    password: "Contraseña",
    passwordHint: "Mínimo 10 caracteres. Puedes usar una frase que recuerdes.",
    show: "Mostrar",
    hide: "Ocultar",
  },
  register: {
    title: "Crea tu cuenta",
    inviteNotice:
      "Durante la beta, Casero funciona solo por invitación. Usa el correo al que llegó tu invitación.",
    acceptTerms: "Acepto los",
    terms: "términos y condiciones",
    and: "y la",
    privacy: "política de privacidad",
    consent: (controller: string) =>
      `Consiento de forma expresa que ${controller}, responsable de Casero, trate mis ingresos por alquiler para darme el servicio, como explica el`,
    consentLink: "documento de consentimiento",
    controllerFallback: "la persona responsable de Casero",
    submit: "Crear mi cuenta",
    sending: "Creando tu cuenta…",
    haveAccount: "¿Ya tienes una cuenta?",
    logIn: "Ingresa",
  },
  login: {
    title: "Ingresa a Casero",
    submit: "Ingresar",
    sending: "Ingresando…",
    forgot: "¿Olvidaste tu contraseña?",
    noAccount: "¿Todavía no tienes cuenta? Casero está en beta y funciona por invitación.",
  },
  home: {
    greeting: "Tu cuenta está lista",
    soon: "Pronto podrás registrar aquí tus inmuebles, tus inquilinos y sus contratos.",
    verify: (email: string, date: string) =>
      `Confirma tu correo: te enviamos un enlace a ${email}. Tienes hasta el ${date} para confirmarlo.`,
    blocked: (email: string) =>
      `Tu cuenta está pausada hasta que confirmes tu correo. Te enviamos el enlace a ${email}.`,
    resend: "Reenviar el correo",
    resent: "Te enviamos un nuevo enlace. Revisa también tu carpeta de spam.",
    resendLimited: "Ya te enviamos 3 correos en la última hora. Vuelve a intentarlo más tarde.",
    resendSuppressed:
      "No podemos enviar correos a esa dirección porque antes rebotó. Escríbenos para revisarlo.",
    resendFailed: "No pudimos enviar el correo. Vuelve a intentarlo en unos minutos.",
    logOut: "Cerrar sesión",
    logOutEverywhere: "Cerrar sesión en todos mis dispositivos",
  },
  verify: {
    title: "Confirmar tu correo",
    checking: "Confirmando tu correo…",
    done: "Tu correo está confirmado.",
    invalid: "Este enlace venció o ya se usó. Ingresa a tu cuenta para pedir uno nuevo.",
    goToAccount: "Ir a mi cuenta",
  },
  forgot: {
    title: "Recupera tu contraseña",
    intro: "Escribe el correo de tu cuenta y te enviaremos un enlace para elegir una nueva contraseña.",
    submit: "Enviarme el enlace",
    sending: "Enviando…",
    sent: "Si existe una cuenta con ese correo, te enviamos un enlace para elegir una nueva contraseña. Vence en 30 minutos; revisa también tu carpeta de spam.",
  },
  newPassword: {
    title: "Elige tu nueva contraseña",
    submit: "Guardar mi nueva contraseña",
    sending: "Guardando…",
    done: "Listo. Tu contraseña cambió y cerramos tus sesiones abiertas. Ya puedes ingresar.",
    invalid: "Este enlace venció o ya se usó. Pide uno nuevo.",
    askAgain: "Pedir un nuevo enlace",
    logIn: "Ingresar",
  },
  errors: {
    required: "Completa este dato.",
    email: "Ese correo parece incompleto. Revisa que tenga @ y un punto, por ejemplo: nombre@gmail.com.",
    password: "La contraseña debe tener al menos 10 caracteres.",
    terms: "Para crear tu cuenta necesitas aceptar los términos y la política de privacidad.",
    consent:
      "Casero necesita tu consentimiento para tratar tus ingresos por alquiler; sin él no puede darte el servicio.",
    invite:
      "Necesitas una invitación válida para este correo. Revisa que abriste el enlace de tu invitación y que escribiste el mismo correo.",
    taken: "Ya existe una cuenta con ese correo. Ingresa o recupera tu contraseña.",
    invalidLogin: "Correo o contraseña incorrectos.",
    tooManyAttempts: "Recibimos muchos intentos desde tu conexión. Vuelve a intentarlo en una hora.",
    failure: "Algo salió mal. Vuelve a intentarlo en unos minutos.",
  },
} as const;
