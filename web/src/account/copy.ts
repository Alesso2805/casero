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
    greeting: "Inicio",
    loading: "Cargando…",
    failure: "No pudimos cargar tu cuenta. Vuelve a intentarlo en unos minutos.",
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
    profile: "Mis datos",
    plan: "Mi plan",
    properties: "Mis inmuebles",
    leases: "Mis contratos",
    declarations: "Formularios de SUNAT",
    templates: "Mensajes de cobro",
  },
  nav: {
    label: "Principal",
    home: "Inicio",
    leases: "Contratos",
    declarations: "SUNAT",
    more: "Más",
  },
  plan: {
    title: "Mi plan",
    trial: (date: string) => `Estás en la prueba gratis de Casero hasta el ${date}.`,
    active: (date: string) => `Tienes el plan Casero hasta el ${date}.`,
    activeOpen: "Tienes el plan Casero.",
    grace: (date: string) => `Tu plan venció, pero puedes seguir usando todo hasta el ${date}.`,
    free: "Estás en el plan Gratis.",
    plansTitle: "Los planes",
    noPrice: "Gratis",
    price: (month: string, year: string) => `${month} al mes o ${year} al año`,
    leases: (count: number) =>
      `Hasta ${String(count)} ${count === 1 ? "contrato activo" : "contratos activos"}`,
    freeFeatures: "Cobros, mensajes por WhatsApp y enlace del inquilino.",
    paidFeatures:
      "Además, Formularios de SUNAT con sus recordatorios, constancias en PDF y archivos para tu contador.",
    payTitle: "Cómo pagar",
    payYape: (number: string, name: string) =>
      `Yapea el monto del plan al ${number}, a nombre de ${name}.`,
    payProof: "Envía la captura por WhatsApp a ese mismo número, con el correo de tu cuenta.",
    payActivation: "Activamos tu plan a mano y te enviamos tu boleta.",
  },
  trialNotice: {
    ended: (date: string) =>
      `Tu prueba gratis terminó. Puedes seguir usando todo hasta el ${date}. Después tu cuenta pasa al plan Gratis, sin los Formularios de SUNAT ni sus recordatorios.`,
    owed: "Todavía tienes formularios 1683 por pagar:",
    due: (period: string, amount: string, date: string) =>
      `${period}: ${amount}, vencen el ${date}`,
    open: "Ver mi plan",
  },
  deletion: {
    title: "Eliminar mi cuenta",
    intro:
      "Se borrarán tus inmuebles, contratos, inquilinos, cobros y declaraciones 30 días después de pedirlo. Hasta entonces puedes cancelarlo con el enlace que te enviaremos por correo.",
    sunat:
      "SUNAT puede revisar tus declaraciones hasta 4 años después. Antes de eliminar tu cuenta, descarga tus datos y guárdalos.",
    button: "Eliminar mi cuenta",
    question:
      "Desde ahora no podrás ingresar a Casero, y tus datos se borrarán en 30 días. ¿Eliminas tu cuenta?",
    confirm: "Sí, eliminar mi cuenta",
    cancel: "Cancelar",
    failure:
      "No pudimos enviarte el correo para cancelarlo, así que no eliminamos tu cuenta. Vuelve a intentarlo en unos minutos.",
  },
  deleted: {
    title: "Pediste eliminar tu cuenta",
    body: (date: string) =>
      `Tus datos se borrarán el ${date}. Si cambias de opinión, usa antes de esa fecha el enlace que te enviamos por correo.`,
    home: "Volver al inicio",
  },
  cancelDeletion: {
    title: "Cancelar la eliminación de tu cuenta",
    intro: "Tu cuenta volverá a funcionar con todos tus datos.",
    confirm: "Sí, conservar mi cuenta",
    done: "Listo, tu cuenta sigue activa. Ya puedes ingresar con tu correo y tu contraseña.",
    invalid: "Este enlace no funciona: ya se usó o venció.",
    taken: (inbox: string) =>
      `Ese correo ya tiene otra cuenta en Casero, así que no pudimos recuperar la tuya. Escríbenos a ${inbox}.`,
    login: "Ingresar",
  },
  dataDownload: {
    title: "Tus datos",
    intro:
      "Descarga una copia de todo lo que tienes en Casero, en archivos que se abren en Excel. Trae los documentos completos de tus inquilinos: guárdala en un lugar seguro.",
    link: "Descargar mis datos",
  },
  legalGate: {
    updatedTitle: "Actualizamos nuestros documentos",
    updatedIntro: "Para seguir usando Casero, lee los cambios y acéptalos.",
    withdrawnTitle: "Tu cuenta está bloqueada",
    withdrawnIntro:
      "Retiraste tu consentimiento para que Casero trate tus ingresos por alquiler. Mientras tanto, Casero no genera tus cobros ni te envía recordatorios. Si lo das otra vez, todo sigue donde lo dejaste.",
    acceptPrivacy: "Acepto la",
    version: (version: string) => `(versión ${version})`,
    submit: "Aceptar y continuar",
    sending: "Guardando…",
    outdated: "Hay una versión más nueva. Vuelve a abrir Casero, revísala y acéptala.",
  },
  profile: {
    title: "Mis datos",
    consentTitle: "Tu consentimiento",
    consentIntro:
      "Diste tu consentimiento para que Casero trate tus ingresos por alquiler. Puedes retirarlo cuando quieras.",
    withdraw: "Retirar mi consentimiento",
    withdrawQuestion:
      "Tu cuenta quedará bloqueada: Casero dejará de generar tus cobros y de enviarte recordatorios, y solo podrás descargar o eliminar tus datos. ¿Lo retiras?",
    withdrawConfirm: "Sí, retirar mi consentimiento",
    withdrawCancel: "Cancelar",
    back: "Volver a mi cuenta",
    paused: "Tu cuenta está pausada. Vuelve al inicio para ver qué falta.",
    displayName: "Tu nombre",
    displayNameHint: "Así te verán tus inquilinos cuando abran su enlace.",
    taxpayerKind: "¿Quién declara estos alquileres ante SUNAT?",
    person: "Yo, como persona",
    estate: "Una sucesión indivisa",
    declarantLocked:
      "Ya no puedes cambiarlo porque esta cuenta tiene inmuebles registrados, aunque estén archivados. Para declarar con otro RUC, crea otra cuenta con otro correo.",
    estateHint:
      "La sucesión indivisa tiene su propio RUC. Si además alquilas inmuebles a tu nombre, necesitas otra cuenta de Casero, con otro correo, para declararlos con tu RUC.",
    ruc: "RUC (puedes completarlo después)",
    rucPerson: "Son los 11 números de tu RUC.",
    rucEstate: "Son los 11 números del RUC de la sucesión.",
    noRuc:
      "Sin RUC, Casero te dice cuánto pagar a SUNAT, pero no la fecha límite de cada formulario.",
    goodTaxpayer: "SUNAT me calificó como buen contribuyente",
    goodTaxpayerHint: "Si no estás seguro, déjalo sin marcar.",
    goodTaxpayerGroup:
      "Tus fechas límite son las de los buenos contribuyentes en el cronograma de SUNAT.",
    digitGroup: (digits: string) =>
      `Tus fechas límite son las de los RUC que terminan en ${digits} en el cronograma de SUNAT.`,
    groupDigits: {
      "0": "0",
      "1": "1",
      "2-3": "2 o 3",
      "4-5": "4 o 5",
      "6-7": "6 o 7",
      "8-9": "8 o 9",
    },
    taxReminders: "Recibir los recordatorios de SUNAT por correo",
    taxRemindersHint:
      "Te escribimos 5 días y 1 día antes de que venzan tus formularios 1683. Si te diste de baja desde un correo, marca la casilla para volver a recibirlos.",
    dailyDigest: "Quiero un resumen diario por correo",
    dailyDigestHint:
      "A las 8:00, solo los días en que tengas algo que hacer. Lo empezaremos a enviar pronto; puedes dejarlo elegido desde ahora.",
    submit: "Guardar mis datos",
    sending: "Guardando…",
    saved: "Listo, guardamos tus datos.",
    rucLength: "El RUC tiene 11 números, sin espacios ni guiones.",
    rucInvalid: "Ese RUC no es válido. Revisa los 11 números en tu ficha RUC.",
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
