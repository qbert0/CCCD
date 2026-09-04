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
      chooseSourceFolder: () => call("choose_source_folder"),
      submitFolderImages: (target, paths, append = false) =>
        call("submit_folder_images", target, JSON.stringify(paths), append),
      getCompanyProfile: () => call("get_company_profile"),
      getCompanyProfileLayout: () => call("get_company_profile_layout"),
      saveCompanyProfile: (personObj) => call("save_company_profile", JSON.stringify(personObj)),
      getRepresentativeProfile: () => call("get_representative_profile"),
      getRepresentativeProfileLayout: () => call("get_representative_profile_layout"),
      saveRepresentativeProfile: (personObj) => call("save_representative_profile", JSON.stringify(personObj)),
      chooseRepresentativeSignature: () => call("choose_representative_signature"),
      chooseCustomerRepresentativeSignature: () => call("choose_customer_representative_signature"),
      getOperatorProfiles: () => call("get_operator_profiles"),
      saveOperatorProfiles: (profiles) => call("save_operator_profiles", JSON.stringify(profiles)),
      chooseOperatorSignature: () => call("choose_operator_signature"),
      getProviderSignature: () => call("get_provider_signature"),
      chooseProviderSignature: () => call("choose_provider_signature"),
      getSignatureCropSize: () => call("get_signature_crop_size"),
      saveCroppedSignature: (base64Png, slug) => call("save_cropped_signature", base64Png, slug),
      getDocumentSetSettings: () => call("get_document_set_settings"),
      saveDocumentSetSettings: (selected) => call("save_document_set_settings", JSON.stringify(selected)),
      newCase: (stateObj) => call("new_case", JSON.stringify(stateObj)),
      persistOperatorFields: (stateObj) => raw.persist_operator_fields(JSON.stringify(stateObj)),

      getServiceTemplates: () => call("get_service_templates"),
      onServiceTemplateChanged: (requestObj) => call("on_service_template_changed", JSON.stringify(requestObj)),
      getLastSourceDir: () => call("get_last_source_dir"),
      getDefaultOutputDir: () => call("get_default_output_dir"),
      setDefaultOutputDir: (path) => raw.set_default_output_dir(path),
      chooseOutputDir: () => call("choose_output_dir"),
      generateServiceTemplateDocuments: (template, stateObj, outputDir) =>
        call("generate_service_template_documents", template, JSON.stringify(stateObj), outputDir),

      onOcrProgress: (fn) => raw.ocrProgress.connect(fn),
      onOcrFileResult: (fn) => raw.ocrFileResult.connect((target, json) => fn(target, JSON.parse(json))),
      onOcrBatchFinished: (fn) => raw.ocrBatchFinished.connect((target, json) => fn(target, JSON.parse(json))),
      onOcrBatchFailed: (fn) => raw.ocrBatchFailed.connect(fn),
      onGenerationFinished: (fn) => raw.generationFinished.connect((jobId, json) => fn(jobId, JSON.parse(json))),
    };
    resolve(CCCD.bridge);
  });
});
