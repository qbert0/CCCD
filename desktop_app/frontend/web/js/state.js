// The single reactive FullFormState, shaped EXACTLY like ReportData (see
// desktop_app/backend/domain/models.py) at the top level -- document_date,
// shop_name, payment_method, notes, etc. are flat root keys, only
// customer/new_owner nest (as PersonData). This isn't a style choice: it's
// what lets every field path and every validation FieldError.path coming
// from Python (both use ReportData's own dotted attribute names) resolve
// with one generic getByPath() call, with zero renaming/mapping in JS.
//
// Presentational-only UI state that never needs Python authority (active
// tab, toasts, calendar popover, disclosure open/closed) lives under `ui`
// so it's never mistaken for report data.
window.CCCD = window.CCCD || {};

CCCD.state = Vue.reactive({
  booted: false,
  document_type: "",
  subscriber_number: "",
  customer: {},
  new_owner: {},
  representative: {},
  provider_company: {},
  // ...remaining ReportData fields (document_date, shop_name, shop_address,
  // shop_phone, staff_name, payment_method, service_action,
  // has_id_attachment, has_original_sim, notes, sim_serial, ...) are added
  // directly onto this root object by boot()/service selection's state_patch
  // -- never declared individually here, so there's exactly one
  // place (Python's DEFAULT_DOCUMENT_VALUES) that knows the full field list.

  serviceFormLayout: {},
  subscriberLayout: {},

  // OCR belongs to numbered image slots, not to whichever service happens
  // to be selected when a worker finishes. Service forms only bind these
  // two canonical people to their business roles (old/new owner/requester).
  commonDossier: {
    revision: 0,
    person123: { entity_type: "Cá nhân", nationality: "Việt Nam", issue_place: "Cục Cảnh sát QLHC về TTXH" },
    person456: { entity_type: "Cá nhân", nationality: "Việt Nam", issue_place: "Cục Cảnh sát QLHC về TTXH" },
    photo123Path: "",
    photo456Path: "",
    upload123: { front: null, back: null, status: "Chưa đọc", invalid: false, note: "", busy: false, progress: null },
    upload456: { front: null, back: null, status: "Chưa đọc", invalid: false, note: "", busy: false, progress: null },
    rawText123: "",
    rawText456: "",
  },

  ui: {
    ready: false,
    activeTab: "current_owner",
    serviceFormOpen: true,
    sourceProcessing: false,
    ocrPanelOpen: false,
    sourceFolder: "",
    sourceFiles: {},
    sourcePaths: {},
    ocrRawText: { customer: "", new_owner: "" },
    errors: {}, // dotted ReportData path -> message
    upload: {
      customer: { front: null, back: null, status: "Chưa có ảnh", invalid: false, note: "", busy: false, progress: null },
      new_owner: { front: null, back: null, status: "Chưa có ảnh", invalid: false, note: "", busy: false, progress: null },
    },
    busy: false,
    statusMessage: "Sẵn sàng",
    toasts: [],
  },
});

let _toastId = 0;
CCCD.pushToast = function (message, tone = "info") {
  const id = ++_toastId;
  CCCD.state.ui.toasts.push({ id, message, tone });
  const timeout = tone === "error" ? 8000 : 3500;
  setTimeout(() => {
    const i = CCCD.state.ui.toasts.findIndex((t) => t.id === id);
    if (i !== -1) CCCD.state.ui.toasts.splice(i, 1);
  }, timeout);
};

CCCD.getByPath = function (root, path) {
  return path.split(".").reduce((o, k) => (o == null ? o : o[k]), root);
};

CCCD.setByPath = function (root, path, value) {
  const parts = path.split(".");
  let obj = root;
  for (let i = 0; i < parts.length - 1; i++) {
    if (obj[parts[i]] == null) obj[parts[i]] = /^\d+$/.test(parts[i + 1]) ? [] : {};
    obj = obj[parts[i]];
  }
  obj[parts[parts.length - 1]] = value;
};

// Non-destructive merge used for the per-file OCR result (only overwrite
// keys with a non-empty value) -- mirrors PersonForm.set_values()'s
// `if value.strip()` guard.
CCCD.mergeNonEmpty = function (target, fields) {
  for (const [key, value] of Object.entries(fields || {})) {
    if (value !== "" && value != null) target[key] = value;
  }
};

CCCD.blankCommonUpload = function () {
  return {
    front: null, back: null, status: "Chưa đọc", invalid: false,
    note: "", busy: false, progress: null,
  };
};

CCCD.resetCommonDossier = function (revision) {
  CCCD.state.commonDossier = {
    revision: Number(revision || 0),
    person123: { entity_type: "Cá nhân", nationality: "Việt Nam", issue_place: "Cục Cảnh sát QLHC về TTXH" },
    person456: { entity_type: "Cá nhân", nationality: "Việt Nam", issue_place: "Cục Cảnh sát QLHC về TTXH" },
    photo123Path: "",
    photo456Path: "",
    upload123: CCCD.blankCommonUpload(),
    upload456: CCCD.blankCommonUpload(),
    rawText123: "",
    rawText456: "",
  };
};

CCCD.commonDossierSnapshot = function () {
  const common = CCCD.state.commonDossier || {};
  return {
    revision: Number(common.revision || 0),
    person123: JSON.parse(JSON.stringify(common.person123 || {})),
    person456: JSON.parse(JSON.stringify(common.person456 || {})),
    photo123Path: String(common.photo123Path || ""),
    photo456Path: String(common.photo456Path || ""),
  };
};

// Merge a service state patch onto the single dossier state.
CCCD.applyStatePatch = function (patch) {
  if (!patch) return;
  for (const [key, value] of Object.entries(patch)) {
    if (["customer", "new_owner", "representative", "provider_company"].includes(key) && value && typeof value === "object") {
      Object.assign(CCCD.state[key], value);
    } else {
      CCCD.state[key] = value;
    }
  }
};

CCCD.reportDataSnapshot = function () {
  const {
    ui, serviceFormLayout, subscriberLayout, commonDossier,
    serviceTemplateOptions, serviceDocumentCount,
    ...reportData
  } = CCCD.state;
  return reportData;
};
