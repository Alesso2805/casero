export const propertiesCopy = {
  list: {
    title: "Mis inmuebles",
    empty:
      "Todavía no registras inmuebles. Empieza por la casa o el edificio donde están los cuartos o departamentos que alquilas.",
    add: "Agregar inmueble",
    units: (count: number) => (count === 1 ? "1 unidad" : `${String(count)} unidades`),
    archived: (count: number) => `Archivados (${String(count)})`,
    details: "Ver y editar",
    detailsOf: (name: string) => `Ver y editar ${name}`,
    back: "Volver a mi cuenta",
  },
  form: {
    newTitle: "Nuevo inmueble",
    name: "Nombre del inmueble",
    nameHint: "Por ejemplo: Casa de Surco o Edificio Los Pinos.",
    addressLine: "Dirección (opcional)",
    district: "Distrito (opcional)",
    ownership: "¿De quién es este inmueble?",
    ownerships: {
      sole: {
        label: "Solo mío",
        hint: "Declaras y pagas a SUNAT por todo lo que cobras de este inmueble.",
      },
      co_owned: {
        label: "De varios dueños, y yo declaro por todos",
        hint: "Cualquier copropietario puede declarar y pagar el total. Elígelo solo si eres tú quien lo declara.",
      },
      conjugal_option: {
        label: "De mi sociedad conyugal, y yo declaro por los dos",
        hint: "Aplica si tu cónyuge y tú eligieron que uno solo declare, con el pago de enero.",
      },
      conjugal_split: {
        label: "De mi sociedad conyugal, y cada uno declara su mitad",
        hint: "Casero todavía no calcula este caso: podrás registrar tus cobros, pero no armará el Formulario 1683 de estos alquileres.",
      },
      estate: {
        label: "De la sucesión indivisa",
        hint: "Esta cuenta es de una sucesión indivisa: todos sus inmuebles se declaran con el RUC de la sucesión.",
      },
    },
    conjugalConfirmation:
      "Confirmo que el RUC de esta cuenta es el del cónyuge que declara por los dos.",
    autovaluo: "Autovalúo en soles (opcional)",
    autovaluoHint:
      "Está en tu declaración del impuesto predial (HR y PU). Casero lo usa solo para avisarte si tu alquiler queda por debajo de la renta mínima.",
    rentedShare: "¿Qué porcentaje del inmueble alquilas?",
    rentedShareHint: "Si alquilas todo el inmueble, deja 100.",
    units: "Unidades que alquilas",
    unitsHint: "Cada cuarto, departamento, local o cochera que alquilas por separado.",
    unitName: (position: number) => `Nombre de la unidad ${String(position)}`,
    unitKind: (position: number) => `Tipo de la unidad ${String(position)}`,
    addUnit: "Agregar otra unidad",
    removeUnit: (position: number) => `Quitar la unidad ${String(position)}`,
    submit: "Guardar inmueble",
    sending: "Guardando…",
    cancel: "Volver a mis inmuebles",
  },
  edit: {
    saved: "Listo, guardamos los cambios.",
    notFound: "No encontramos este inmueble.",
    archivedNotice: "Este inmueble está archivado.",
    units: "Unidades",
    unitName: "Nombre de la unidad",
    unitKind: "Tipo de unidad",
    editUnit: (name: string) => `Editar ${name}`,
    saveUnit: "Guardar unidad",
    cancel: "Cancelar",
    archiveUnit: (name: string) => `Archivar ${name}`,
    confirmArchiveUnit: (name: string) =>
      `¿Archivar ${name}? Ya no podrás registrar contratos en esta unidad.`,
    confirm: "Sí, archivar",
    addUnitTitle: "Agregar una unidad",
    addUnit: "Agregar unidad",
    archiveProperty: "Archivar inmueble",
    confirmArchiveProperty:
      "¿Archivar este inmueble y todas sus unidades? Seguirá en tu historial, pero ya no podrás registrar contratos en él.",
    unitActiveLease: "Esta unidad tiene un contrato activo. Termínalo antes de archivarla.",
    propertyActiveLease:
      "Una de sus unidades tiene un contrato activo. Termínalo antes de archivar el inmueble.",
  },
  unitKinds: {
    room: "Cuarto",
    mini_apartment: "Minidepartamento",
    apartment: "Departamento",
    shop: "Local",
    parking: "Cochera",
    other: "Otro",
  },
  errors: {
    required: "Completa este dato.",
    autovaluo: "Escribe el monto en soles, sin comas de miles. Por ejemplo: 250000.",
    rentedShare: "Escribe un número del 1 al 100.",
    conjugalConfirmation:
      "Para elegir esta opción, confirma que el RUC de esta cuenta es el del cónyuge que declara.",
    paused: "Tu cuenta está pausada hasta que confirmes tu correo.",
    failure: "Algo salió mal. Vuelve a intentarlo en unos minutos.",
  },
} as const;
