// Bootstraps the QWebChannel connection to the Python WebBridge and exposes
// it as a promise-friendly wrapper on window.CCCD.bridge. Every generated
// bridge slot is callback-based (new QWebChannel(...) queues delivery until
// the handshake completes, so this is safe to call before "ready" as long
// as callers wait on CCCD.bridgeReady first).
window.CCCD = window.CCCD || {};

CCCD.bridgeReady = new Promise((resolve) => {
  new QWebChannel(qt.webChannelTransport, (channel) => {
    const raw = channel.objects.bridge;
    CCCD.rawBridge = raw;

    // Wrap every JSON-in/JSON-out slot as a promise returning a parsed
    // object, so calling code never touches JSON.parse/stringify directly.
    const call = (name, ...args) => new Promise((res) => {
      raw[name](...args, (resultJson) => res(resultJson ? JSON.parse(resultJson) : null));
    });

    CCCD.bridge = {
      getInitialState: () => call("get_initial_state"),
      getNewDocumentState: (documentType) => call("get_new_document_state", documentType),
      onDocumentTypeChanged: (requestObj) => call("on_document_type_changed", JSON.stringify(requestObj)),
      applyProfileDefaults: (documentType) => call("apply_profile_defaults", documentType),
      onEntityTypeChanged: (form, entityType) => call("on_entity_type_changed", form, entityType),
      selectAndScanImages: (target) => raw.select_and_scan_images(target),
      submitDroppedImage: (target, filename, base64Data) => raw.submit_dropped_image(target, filename, base64Data),
      validate: (stateObj) => call("validate", JSON.stringify(stateObj)),
      previewDocument: (stateObj) => call("preview_document", JSON.stringify(stateObj)),
      exportDocument: (stateObj) => call("export_document", JSON.stringify(stateObj)),
      getReviewSummary: (stateObj) => call("get_review_summary", JSON.stringify(stateObj)),
      getCompanyProfile: () => call("get_company_profile"),
      getCompanyProfileLayout: () => call("get_company_profile_layout"),
      saveCompanyProfile: (personObj) => call("save_company_profile", JSON.stringify(personObj)),
      getRepresentativeProfile: () => call("get_representative_profile"),
      getRepresentativeProfileLayout: () => call("get_representative_profile_layout"),
      saveRepresentativeProfile: (personObj) => call("save_representative_profile", JSON.stringify(personObj)),
      newCase: (stateObj) => call("new_case", JSON.stringify(stateObj)),

      onOcrProgress: (fn) => raw.ocrProgress.connect(fn),
      onOcrFileResult: (fn) => raw.ocrFileResult.connect((target, json) => fn(target, JSON.parse(json))),
      onOcrBatchFinished: (fn) => raw.ocrBatchFinished.connect((target, json) => fn(target, JSON.parse(json))),
      onOcrBatchFailed: (fn) => raw.ocrBatchFailed.connect(fn),
    };
    resolve(CCCD.bridge);
  });
});
