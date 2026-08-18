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
  // ...remaining ReportData fields (document_date, shop_name, shop_address,
  // shop_phone, staff_name, payment_method, service_action,
  // has_id_attachment, has_original_sim, notes, sim_serial, ...) are added
  // directly onto this root object by boot()/on_document_type_changed's
  // state_patch -- never declared individually here, so there's exactly one
  // place (Python's DEFAULT_DOCUMENT_VALUES) that knows the full field list.

  layouts: {
    customer: { primary_rows: [], detail_rows: [], has_detail: false, allow_entity: false },
    representative: { primary_rows: [], detail_rows: [], has_detail: false, allow_entity: false },
    new_owner: { primary_rows: [], detail_rows: [], has_detail: false, allow_entity: false },
    document: { common_rows: [], primary_rows: [], detail_rows: [], has_detail: false, notes_field: null },
    sims: {},
  },

  ui: {
    ready: false,
    documentFullTitle: "",
    tabs: {
      customerLabel: "Khách hàng",
      representativeLabel: "Người đại diện",
      newOwnerLabel: "Chủ thuê bao mới",
      documentLabel: "Thông tin tài liệu",
      simsLabel: "Danh sách SIM",
      representativeTabVisible: false,
      newOwnerTabVisible: false,
      simsTabVisible: false,
      newOwnerUploadVisible: false,
    },
    activeTab: "customer",
    detailOpen: { customer: false, representative: false, new_owner: false, document: false, profile: false },
    ocrPanelOpen: false,
    ocrRawText: { customer: "", new_owner: "" },
    errors: {}, // dotted ReportData path -> message
    upload: {
      customer: { front: null, back: null, status: "Chưa có ảnh", invalid: false, note: "", busy: false, progress: null },
      new_owner: { front: null, back: null, status: "Chưa có ảnh", invalid: false, note: "", busy: false, progress: null },
      // Company Profile dialog's own "Người đại diện" intake card -- a
      // session record, not case data, so it isn't reset by "Hồ sơ mới".
      representative: { front: null, back: null, status: "Chưa có ảnh", invalid: false, note: "", busy: false, progress: null },
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

// Shallow-merge a {"customer": {...}, "new_owner": {...}, <root fields>...}
// state_patch (as returned by on_document_type_changed) onto CCCD.state.
CCCD.applyStatePatch = function (patch) {
  if (!patch) return;
  for (const [key, value] of Object.entries(patch)) {
    if ((key === "customer" || key === "new_owner" || key === "representative") && value && typeof value === "object") {
      Object.assign(CCCD.state[key], value);
    } else {
      CCCD.state[key] = value;
    }
  }
};

CCCD.reportDataSnapshot = function () {
  const { layouts, ui, ...reportData } = CCCD.state;
  return reportData;
};
