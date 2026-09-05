(function () {
  const state = CCCD.state;

  const App = {
    data() {
      return {
        state,
        calendar: null,
        cropModal: null,
        // job id (from generate_service_template_documents' dispatch-ack) ->
        // the CCCD.reportDataSnapshot() taken at the moment it was dispatched.
        // Generation now finishes on its own thread/signal, arbitrarily long
        // after the click and possibly after the user has switched to a
        // different case -- persistOperatorFields (see onGenerationFinished
        // below) must use the snapshot from when THIS job was started, never
        // a fresh one taken when it happens to finish.
        pendingGenerations: {},
        profile: null,
        profileLayout: null,
        representative: null,
        representativeLayout: null,
        representative2: null,
        representative2Layout: null,
        operatorProfiles: null,
        providerSignature: null,
        documentSetSettings: null,
        profileTab: "company",
        profileLoading: false,
        sourceQueue: null,
        serviceChangeRevision: 0,
      };
    },
    computed: {
      selectedServiceOption() {
        return (state.serviceTemplateOptions || []).find(
          (item) => item.value === state.service_template,
        ) || null;
      },
      serviceLayout() {
        return state.serviceFormLayout || {};
      },
      serviceTabs() {
        return this.serviceLayout.tabs || [];
      },
      currentOwnerSections() {
        return this.serviceLayout.current_owner?.sections || [];
      },
      newOwnerSections() {
        return this.serviceLayout.new_owner?.sections || [];
      },
      transactionSections() {
        return this.serviceLayout.transaction?.sections || [];
      },
      providerSections() {
        return this.serviceLayout.provider?.sections || [];
      },
      subscriberLayout() {
        return state.subscriberLayout || { columns: [] };
      },
      requiredSourceNumbers() {
        if (!this.selectedServiceOption) return [1, 2, 3];
        return this.selectedServiceOption.required_images || [1, 2, 3];
      },
      missingSourceNumbers() {
        return this.requiredSourceNumbers.filter(
          (number) => !state.ui.sourceFiles?.[number],
        );
      },
      sourceSlotNumbers() {
        return this.selectedServiceOption ? this.requiredSourceNumbers : [1, 2, 3, 4, 5, 6];
      },
      firstSubscriberNumber() {
        return String(state.subscribers?.[0]?.subscriber_number || "");
      },
      canGenerateService() {
        return !!state.service_template
          && !!state.ui.sourceFolder
          && !this.missingSourceNumbers.length
          && !!this.firstSubscriberNumber.trim()
          && !state.ui.sourceProcessing;
      },
      // Informational only -- unlike the old state.ui.busy, this never
      // gates canGenerateService, since a generation job running in the
      // background is exactly the point: the button stays clickable so a
      // second (or third...) case can dispatch its own job right away.
      hasPendingGenerations() {
        return Object.keys(this.pendingGenerations).length > 0;
      },
      calendarValue() {
        if (!this.calendar) return "";
        return CCCD.getByPath(this.calendar.root || state, this.calendar.field.path) || "";
      },
      calendarInProfile() {
        const path = this.calendar?.field?.path || "";
        return !!this.profile && (
          path.startsWith("profile.") || path.startsWith("representative.")
          || path.startsWith("representative_2.")
        );
      },
      profileRoot() {
        return { profile: this.profile || {} };
      },
      representativeRoot() {
        return { representative: this.representative || {} };
      },
      representative2Root() {
        return { representative_2: this.representative2 || {} };
      },
      profileNavItems() {
        return [
          { id: "company", number: "01", label: "Công ty", hint: "Pháp nhân và điểm giao dịch" },
          { id: "representative", number: "02", label: "Người đại diện", hint: "Danh tính người đại diện" },
          { id: "representative_2", number: "03", label: "Người đại diện 2", hint: "Bên A của dịch vụ Quang Hà - STT" },
          { id: "operators", number: "04", label: "Giao dịch viên", hint: "Tên, chữ ký và dịch vụ phụ trách" },
          { id: "document_sets", number: "05", label: "Tài liệu theo dịch vụ", hint: "Bật/tắt từng tài liệu cho mỗi dịch vụ" },
        ];
      },
    },
    async mounted() {
      await CCCD.bridgeReady;
      const [initial, serviceTemplateOptions, signatureCropSize] = await Promise.all([
        CCCD.bridge.getInitialState(),
        CCCD.bridge.getServiceTemplates(),
        CCCD.bridge.getSignatureCropSize(),
      ]);
      Object.assign(state, initial.state);
      state.subscriberLayout = initial.subscriber_layout;
      state.serviceTemplateOptions = serviceTemplateOptions;
      state.signatureCropSize = signatureCropSize;
      state.serviceFormLayout = {};
      state.serviceDocumentCount = 0;
      state.booted = true;
      this.sourceQueue = Promise.resolve();

      CCCD.bridge.onOcrProgress((target, done, total) => {
        const slot = this.commonSlotForTarget(target);
        if (!slot || slot.revision !== state.commonDossier.revision) return;
        const upload = state.commonDossier[`upload${slot.number}`];
        upload.progress = { done, total };
        upload.busy = true;
      });
      CCCD.bridge.onOcrFileResult((target, result) => {
        const slot = this.commonSlotForTarget(target);
        if (!slot || slot.revision !== state.commonDossier.revision) return;
        const upload = state.commonDossier[`upload${slot.number}`];
        if (result.error || result.side === "unknown") {
          upload.status = "Chưa xác định được mặt CCCD";
          upload.invalid = true;
          upload.note = result.error || "Ảnh chưa đủ rõ để nhận biết mặt CCCD.";
          return;
        }
        upload[result.side] = {
          thumbnail: result.thumbnail_data_url,
          filename: `${result.filename} · ${result.source}`,
          source: result.source,
        };
        CCCD.mergeNonEmpty(state.commonDossier[`person${slot.number}`], result.fields);
      });
      CCCD.bridge.onOcrBatchFinished((target, result) => {
        const slot = this.commonSlotForTarget(target);
        if (!slot || slot.revision !== state.commonDossier.revision) return;
        const upload = state.commonDossier[`upload${slot.number}`];
        upload.progress = null;
        upload.busy = false;
        if (result.accepted) {
          CCCD.mergeNonEmpty(state.commonDossier[`person${slot.number}`], result.fields);
          upload.status = "Đã đọc CCCD";
        }
        upload.note = (result.warnings || []).join("\n");
        upload.invalid = !!upload.note;
        state.commonDossier[`rawText${slot.number}`] = (
          `===== ẢNH ${slot.number === "123" ? "1–2" : "4–5"} =====\n${result.raw_text}`
        );
        state.ui.statusMessage = result.accepted
          ? `Đã đọc xong thông tin chung từ ảnh ${slot.number === "123" ? "1–3" : "4–6"}`
          : "Chưa nhận biết được mặt CCCD";
      });
      CCCD.bridge.onOcrBatchFailed((target, message) => {
        const slot = this.commonSlotForTarget(target);
        if (!slot || slot.revision !== state.commonDossier.revision) return;
        const upload = state.commonDossier[`upload${slot.number}`];
        upload.progress = null;
        upload.busy = false;
        upload.status = "Không đọc được ảnh";
        upload.invalid = true;
        upload.note = message;
        CCCD.pushToast(message, "error");
      });
      CCCD.bridge.onGenerationFinished((jobId, result) => {
        const snapshot = this.pendingGenerations[jobId];
        delete this.pendingGenerations[jobId];
        if (result.ok) {
          if (snapshot) CCCD.bridge.persistOperatorFields(snapshot);
          CCCD.pushToast(`Đã tạo bộ hồ sơ gồm ${result.paths.length} ảnh`, "success");
          return;
        }
        const message = result.errors?.length
          ? result.errors[0].message
          : (result.message || "Không tạo được bộ tài liệu");
        CCCD.pushToast(message, "error");
      });
    },
    methods: {
      commonSlotForTarget(target) {
        const match = /^common_(123|456):(\d+)$/.exec(String(target || ""));
        return match ? { number: match[1], revision: Number(match[2]) } : null;
      },
      bindCommonToService(templateValue = state.service_template) {
        const option = (state.serviceTemplateOptions || []).find(
          (item) => item.value === templateValue,
        );
        if (!option) return;
        const common = state.commonDossier;
        if (option.source_role === "new_owner_123") {
          state.new_owner = common.person123;
          state.new_owner_photo_path = common.photo123Path;
          state.customer_photo_path = "";
        } else if (option.source_role === "old_123_new_456") {
          state.customer = common.person123;
          state.new_owner = common.person456;
          state.customer_photo_path = common.photo123Path;
          state.new_owner_photo_path = common.photo456Path;
        } else {
          state.customer = common.person123;
          state.customer_photo_path = common.photo123Path;
          state.new_owner_photo_path = "";
        }
      },
      async onServiceTemplateChange(newTemplate, options = {}) {
        const previousTemplate = state.service_template || "";
        const requestRevision = ++this.serviceChangeRevision;
        // Reflect the user's latest choice immediately. A slower response
        // for an earlier choice is ignored below.
        state.service_template = newTemplate;
        const result = await CCCD.bridge.onServiceTemplateChanged({
          previous_service_template: previousTemplate,
          new_service_template: newTemplate,
          state: CCCD.reportDataSnapshot(),
          common_dossier: CCCD.commonDossierSnapshot(),
        });
        if (requestRevision !== this.serviceChangeRevision || state.service_template !== newTemplate) return;
        if (!result.ui.ready) {
          state.service_template = "";
          state.serviceFormLayout = {};
          state.serviceDocumentCount = 0;
          return;
        }
        // customer/new_owner may currently be references into commonDossier.
        // Detach before applying the service patch so organization defaults
        // can never overwrite person123/person456 through a shared object.
        state.customer = {};
        state.new_owner = {};
        CCCD.applyStatePatch(result.state_patch);
        state.service_template = newTemplate;
        this.bindCommonToService(newTemplate);
        state.serviceFormLayout = result.service_layout;
        state.serviceDocumentCount = result.ui.documentCount;
        state.ui.serviceFormOpen = true;
        state.ui.activeTab = (result.service_layout.tabs || []).find(
          (tab) => tab.visible !== false,
        )?.id || "current_owner";
        state.ui.errors = {};
        state.ui.statusMessage = `Đã áp dụng form ${result.ui.serviceTemplateName}`;
      },
      waitForOcrBatch(target) {
        let cleanup = () => {};
        const promise = new Promise((resolve) => {
          const finished = (receivedTarget, result) => {
            if (receivedTarget === target) {
              cleanup();
              resolve({ ok: true, result });
            }
          };
          const failed = (receivedTarget, message) => {
            if (receivedTarget === target) {
              cleanup();
              resolve({ ok: false, message });
            }
          };
          cleanup = () => {
            CCCD.rawBridge.ocrBatchFinished.disconnect(finished);
            CCCD.rawBridge.ocrBatchFailed.disconnect(failed);
          };
          CCCD.rawBridge.ocrBatchFinished.connect(finished);
          CCCD.rawBridge.ocrBatchFailed.connect(failed);
        });
        promise.cancel = cleanup;
        return promise;
      },
      async scanSourceFolder() {
        const scan = await CCCD.bridge.chooseSourceFolder();
        if (!scan.folder) return;
        // A numbered folder is a replacement dossier. Reset transaction
        // fields, but keep the independently entered subscriber rows and
        // whatever service the user may choose while this bridge call runs.
        await this.newCase({ preserveService: true, preserveSubscribers: true, preserveSource: true });
        const revision = Number(state.commonDossier?.revision || 0) + 1;
        CCCD.resetCommonDossier(revision);
        state.ui.sourceFolder = scan.folder;
        state.ui.sourcePaths = scan.images || {};
        state.ui.sourceFiles = Object.fromEntries(
          [1, 2, 3, 4, 5, 6].map((number) => [number, !!state.ui.sourcePaths[number]]),
        );
        // Portraits 3/6 are document assets, not OCR inputs. Keep their
        // original paths without copying or generating thumbnails during
        // synchronization.
        state.commonDossier.photo123Path = state.ui.sourcePaths[3] || "";
        state.commonDossier.photo456Path = state.ui.sourcePaths[6] || "";
        state.ui.errors = {};
        this.bindCommonToService();
        const paths = { ...state.ui.sourcePaths };
        state.ui.sourceProcessing = true;
        state.ui.statusMessage = "Đã nhận folder · đang đọc thông tin chung";
        const previous = this.sourceQueue || Promise.resolve();
        const job = previous.catch(() => {}).then(async () => {
          if (revision !== state.commonDossier.revision) return;
          await this.processCommonSourceImages(revision, paths);
        });
        this.sourceQueue = job;
        try {
          await job;
        } finally {
          if (revision === state.commonDossier.revision) {
            state.ui.sourceProcessing = false;
            state.ui.statusMessage = state.service_template
              ? "Đã đọc xong folder · form dịch vụ đã được cập nhật"
              : "Đã đọc xong folder · có thể chọn dịch vụ";
          }
        }
      },
      async readCommonPerson(slotNumber, frontNumber, revision, paths) {
        // The front image is always OCR'd first. Its QR code alone
        // already carries id number, full name, DOB, gender, address and
        // (usually) issue date, near-instantly -- so if it decodes, the
        // back is skipped entirely (still kept and copied into the
        // dossier, just never sent through the much slower
        // PaddleOCR/VietOCR path). Only when the front had no QR to fall
        // back on do we pay for reading the back too, for the fields that
        // only ever come from there (e.g. expiry_date).
        const target = `common_${slotNumber}:${revision}`;
        const frontPath = paths[frontNumber];
        if (!frontPath) return;
        const pending = this.waitForOcrBatch(target);
        const start = await CCCD.bridge.submitFolderImages(target, [frontPath]);
        if (!start?.started) {
          pending.cancel();
          if (revision === state.commonDossier.revision) {
            CCCD.pushToast(start?.message || "Không bắt đầu được việc đọc CCCD", "error");
          }
          return;
        }
        await pending;

        const upload = state.commonDossier[`upload${slotNumber}`];
        const frontSource = upload?.front?.source || upload?.back?.source || "";
        const backPath = paths[frontNumber + 1];
        if (frontSource === "QR CCCD" || !backPath) return;

        // append: true -- this reuses the SAME target as the front scan
        // above, so submit_folder_images must not reset _accepted_files
        // for it (that would silently drop the front's already-accepted
        // result out from under this in-flight dossier).
        const backPending = this.waitForOcrBatch(target);
        const backStart = await CCCD.bridge.submitFolderImages(target, [backPath], true);
        if (!backStart?.started) {
          backPending.cancel();
          return;
        }
        await backPending;
      },
      async processCommonSourceImages(revision, paths) {
        const batches = [this.readCommonPerson("123", 1, revision, paths)];
        if (paths[4]) {
          batches.push(this.readCommonPerson("456", 4, revision, paths));
        }
        await Promise.all(batches);
      },
      tabForError(path) {
        if (path.startsWith("new_owner.")) return "new_owner";
        if (path.startsWith("subscribers.") || path.startsWith("beautiful_subscribers.")) {
          return "";
        }
        if (
          path.startsWith("provider_company.")
          || path.startsWith("representative.")
          || path.startsWith("provider_")
          || path.startsWith("service_point_")
        ) return "provider";
        if (path.startsWith("customer.")) return "current_owner";
        return state.service_template === "sim_replacement" ? "transaction" : "provider";
      },
      async generateServiceTemplateDocuments(useSourceFolder) {
        if (!state.service_template) {
          CCCD.pushToast("Hãy chọn dịch vụ trước", "error");
          return;
        }
        if (!state.ui.sourceFolder || this.missingSourceNumbers.length) {
          const missing = this.missingSourceNumbers.map((number) => `${number}.jpg`).join(", ");
          CCCD.pushToast(
            missing ? `Bộ hồ sơ còn thiếu: ${missing}` : "Hãy chọn folder bộ hồ sơ",
            "error",
          );
          return;
        }
        const folder = useSourceFolder
          ? await CCCD.bridge.getLastSourceDir()
          : await CCCD.bridge.chooseOutputDir();
        if (!folder) return;

        // Dispatch only -- generate_service_template_documents now starts a
        // background thread and returns right away (job_id) or an
        // immediate rejection (overloaded / missing source images, both
        // still fast/local enough not to need threading). The real
        // success/failure arrives later via onGenerationFinished above, by
        // which point the user may well have moved to a different case --
        // so no state.ui.busy gating the whole run, and errors that DO
        // still arrive here (this form is still the one on screen right
        // now) are the only ones painted into state.ui.errors.
        const snapshot = CCCD.reportDataSnapshot();
        const result = await CCCD.bridge.generateServiceTemplateDocuments(
          state.service_template, snapshot, folder,
        );
        if (result.overloaded) {
          CCCD.pushToast(result.message, "error");
          return;
        }
        if (result.errors?.length) {
          state.ui.errors = {};
          for (const error of result.errors) state.ui.errors[error.path] = error.message;
          const first = result.errors.find((error) => error.path !== "source_folder");
          if (first) {
            const tab = this.tabForError(first.path);
            if (tab) state.ui.activeTab = tab;
          }
          CCCD.pushToast(
            result.errors.find((error) => error.path === "source_folder")?.message
              || `Còn ${result.errors.length} trường cần bổ sung`,
            "error",
          );
          return;
        }
        if (!result.ok) {
          CCCD.pushToast(result.message || "Không tạo được bộ tài liệu", "error");
          return;
        }
        this.pendingGenerations[result.job_id] = snapshot;
        state.ui.statusMessage = "Đang tạo bộ hồ sơ ở nền…";
        CCCD.pushToast("Đang tạo bộ hồ sơ ở nền…", "success");
      },
      openCalendar({ field, root, $event }) {
        this.calendar = { field, root, anchorRect: $event.target.getBoundingClientRect() };
      },
      pickDate(value) {
        CCCD.setByPath(this.calendar.root || state, this.calendar.field.path, value);
        delete state.ui.errors[this.calendar.field.path];
        this.calendar = null;
      },
      async newCase(options = {}) {
        const subscribers = options.preserveSubscribers
          ? JSON.parse(JSON.stringify(state.subscribers || []))
          : null;
        const fresh = await CCCD.bridge.newCase(CCCD.reportDataSnapshot());
        // Read the desired service after the async bridge call: the user is
        // allowed to change it while a reset is in flight.
        const serviceTemplate = options.preserveService === false
          ? ""
          : (state.service_template || "");
        ++this.serviceChangeRevision;
        Object.assign(state, fresh);
        if (subscribers) state.subscribers = subscribers;
        state.serviceFormLayout = {};
        state.serviceDocumentCount = 0;
        CCCD.resetCommonDossier(Number(state.commonDossier?.revision || 0) + 1);
        state.ui.sourceProcessing = false;
        state.ui.errors = {};
        state.ui.activeTab = "current_owner";
        if (!options.preserveSource) {
          state.ui.sourceFolder = "";
          state.ui.sourceFiles = {};
          state.ui.sourcePaths = {};
        }
        if (serviceTemplate) {
          await this.onServiceTemplateChange(serviceTemplate);
        } else {
          state.service_template = "";
        }
        state.ui.statusMessage = "Đã mở hồ sơ mới";
      },
      async updateFromProfileDefaults() {
        if (!state.service_template) return;
        await this.onServiceTemplateChange(state.service_template);
        CCCD.pushToast("Đã nạp lại mặc định cho form dịch vụ", "success");
      },
      async openCompanyProfile() {
        // Guards against two real failure modes that both left the dialog
        // stuck open with a blank body (header/footer render unconditionally,
        // but the nav+form only render once all 6 fetches are non-null):
        // a second click firing a redundant, overlapping fetch while the
        // first was still in flight, and a bridge call occasionally coming
        // back null with nothing telling the user it failed.
        if (this.profileLoading) return;
        this.profileLoading = true;
        state.ui.errors = {};
        try {
          const [person, layout, representative, representativeLayout, representative2, representative2Layout, operatorProfiles, providerSignature, documentSetSettings] = await Promise.all([
            CCCD.bridge.getCompanyProfile(),
            CCCD.bridge.getCompanyProfileLayout(),
            CCCD.bridge.getRepresentativeProfile(),
            CCCD.bridge.getRepresentativeProfileLayout(),
            CCCD.bridge.getRepresentative2Profile(),
            CCCD.bridge.getRepresentative2ProfileLayout(),
            CCCD.bridge.getOperatorProfiles(),
            CCCD.bridge.getProviderSignature(),
            CCCD.bridge.getDocumentSetSettings(),
          ]);
          if (!person || !layout || !representative || !representativeLayout || !representative2 || !representative2Layout || !operatorProfiles || !providerSignature || !documentSetSettings) {
            CCCD.pushToast("Không tải được thiết lập mặc định, hãy thử lại", "error");
            return;
          }
          this.profile = person;
          this.profileLayout = layout;
          this.representative = representative;
          this.representativeLayout = representativeLayout;
          this.representative2 = representative2;
          this.representative2Layout = representative2Layout;
          this.operatorProfiles = operatorProfiles;
          this.providerSignature = providerSignature;
          this.documentSetSettings = documentSetSettings;
          this.profileTab = "company";
          await this.$nextTick();
          if (!this.$refs.profileDialog.open) this.$refs.profileDialog.showModal();
        } finally {
          this.profileLoading = false;
        }
      },
      async saveProfile() {
        const result = await CCCD.bridge.saveCompanyProfile(this.profile);
        if (!result.ok) {
          for (const error of result.errors) state.ui.errors[error.path] = error.message;
          return;
        }
        // Propagate into whatever service form is already open, the same
        // way an OCR scan already does live via commonDossier -- was
        // previously only reachable by the user manually clicking "↻ Nạp
        // lại mặc định" (updateFromProfileDefaults), one of the two
        // genuinely disconnected common-store paths this was auditing.
        if (state.service_template) await this.onServiceTemplateChange(state.service_template);
        CCCD.pushToast("Đã lưu thông tin công ty mặc định", "success");
      },
      async saveRepresentativeProfile() {
        const result = await CCCD.bridge.saveRepresentativeProfile(this.representative);
        if (!result.ok) {
          for (const error of result.errors) state.ui.errors[error.path] = error.message;
          return;
        }
        if (state.service_template) await this.onServiceTemplateChange(state.service_template);
        CCCD.pushToast("Đã lưu người đại diện mặc định", "success");
      },
      async saveRepresentative2Profile() {
        const result = await CCCD.bridge.saveRepresentative2Profile(this.representative2);
        if (!result.ok) {
          for (const error of result.errors) state.ui.errors[error.path] = error.message;
          return;
        }
        if (state.service_template) await this.onServiceTemplateChange(state.service_template);
        CCCD.pushToast("Đã lưu người đại diện 2 mặc định", "success");
      },
      addOperatorProfile() {
        const suffix = `${Date.now()}_${Math.floor(Math.random() * 10000)}`;
        this.operatorProfiles.profiles.push({
          profile_id: `operator_${suffix}`,
          name: "",
          signature_path: "",
          signature_thumbnail: "",
          service_templates: [],
        });
      },
      // Every one of the 4 signature-upload sites below only picks a file
      // and hands the resulting preview to the crop modal -- nothing is
      // written to disk (or, where applicable, Settings) until the user
      // confirms a crop and confirmSignatureCrop below gets the final,
      // already-sized file back from save_cropped_signature.
      openSignatureCrop(sourceDataUrl, slug, onConfirm) {
        this.cropModal = { sourceDataUrl, slug, onConfirm };
      },
      async confirmSignatureCrop(base64Png) {
        const { slug, onConfirm } = this.cropModal;
        this.cropModal = null;
        const result = await CCCD.bridge.saveCroppedSignature(base64Png, slug);
        if (!result?.ok) {
          CCCD.pushToast("Không lưu được ảnh chữ ký", "error");
          return;
        }
        onConfirm(result);
      },
      async chooseCustomerRepresentativeSignature() {
        const result = await CCCD.bridge.chooseCustomerRepresentativeSignature();
        if (!result?.ok) return;
        this.openSignatureCrop(result.signature_source, "customer_representative", (final) => {
          state.customer.signature_path = final.signature_path;
          state.customer.signature_thumbnail = final.signature_thumbnail;
        });
      },
      // Per-case only (never persisted to Settings, same as the upload
      // side above) -- just clears the local state fields directly.
      clearCustomerRepresentativeSignature() {
        state.customer.signature_path = "";
        state.customer.signature_thumbnail = "";
      },
      async chooseRepresentativeSignature() {
        const result = await CCCD.bridge.chooseRepresentativeSignature();
        if (!result?.ok) return;
        this.openSignatureCrop(result.signature_source, "representative", (final) => {
          this.representative.signature_path = final.signature_path;
          this.representative.signature_thumbnail = final.signature_thumbnail;
          CCCD.pushToast("Đã lưu ảnh chữ ký người đại diện", "success");
        });
      },
      async clearRepresentativeSignature() {
        const result = await CCCD.bridge.clearRepresentativeSignature();
        if (!result?.ok) return;
        this.representative.signature_path = "";
        this.representative.signature_thumbnail = "";
        CCCD.pushToast("Đã xóa ảnh chữ ký người đại diện", "success");
      },
      async chooseRepresentative2Signature() {
        const result = await CCCD.bridge.chooseRepresentative2Signature();
        if (!result?.ok) return;
        this.openSignatureCrop(result.signature_source, "representative_2", (final) => {
          this.representative2.signature_path = final.signature_path;
          this.representative2.signature_thumbnail = final.signature_thumbnail;
          CCCD.pushToast("Đã lưu ảnh chữ ký người đại diện 2", "success");
        });
      },
      async clearRepresentative2Signature() {
        const result = await CCCD.bridge.clearRepresentative2Signature();
        if (!result?.ok) return;
        this.representative2.signature_path = "";
        this.representative2.signature_thumbnail = "";
        CCCD.pushToast("Đã xóa ảnh chữ ký người đại diện 2", "success");
      },
      async chooseProviderSignature() {
        const result = await CCCD.bridge.chooseProviderSignature();
        if (!result?.ok) return;
        this.openSignatureCrop(result.signature_source, "provider", (final) => {
          this.providerSignature.signature_path = final.signature_path;
          this.providerSignature.signature_thumbnail = final.signature_thumbnail;
          state.provider_signature_path = final.signature_path;
          CCCD.pushToast("Đã lưu ảnh chữ ký bên cung cấp dịch vụ", "success");
        });
      },
      async clearProviderSignature() {
        const result = await CCCD.bridge.clearProviderSignature();
        if (!result?.ok) return;
        this.providerSignature.signature_path = "";
        this.providerSignature.signature_thumbnail = "";
        state.provider_signature_path = "";
        CCCD.pushToast("Đã xóa ảnh chữ ký bên cung cấp dịch vụ", "success");
      },
      async chooseOperatorSignature(profileId) {
        const result = await CCCD.bridge.chooseOperatorSignature();
        if (!result?.ok) return;
        // profileId is already "operator_<suffix>" (see addOperatorProfile
        // below) -- it IS the slug, not a suffix to prepend one onto.
        this.openSignatureCrop(result.signature_source, profileId, (final) => {
          const item = this.operatorProfiles.profiles.find(
            (entry) => entry.profile_id === profileId,
          );
          if (item) {
            item.signature_path = final.signature_path;
            item.signature_thumbnail = final.signature_thumbnail;
          }
        });
      },
      // Operator signatures aren't persisted individually (same as every
      // other field on this card) -- cleared locally, takes effect once
      // "Lưu giao dịch viên" is pressed, same as a name edit.
      clearOperatorSignature(profileId) {
        const item = this.operatorProfiles.profiles.find(
          (entry) => entry.profile_id === profileId,
        );
        if (item) {
          item.signature_path = "";
          item.signature_thumbnail = "";
        }
      },
      removeOperatorProfile(profileId) {
        if (this.operatorProfiles.profiles.length <= 1) {
          CCCD.pushToast("Cần giữ lại ít nhất một giao dịch viên", "error");
          return;
        }
        this.operatorProfiles.profiles = this.operatorProfiles.profiles.filter(
          (item) => item.profile_id !== profileId,
        );
      },
      operatorServiceTaken(serviceValue, profileId) {
        return this.operatorProfiles.profiles.some(
          (item) => item.profile_id !== profileId
            && item.service_templates.includes(serviceValue),
        );
      },
      async saveOperatorProfiles() {
        const result = await CCCD.bridge.saveOperatorProfiles(this.operatorProfiles.profiles);
        if (!result?.ok) {
          CCCD.pushToast(result?.message || "Không lưu được người làm thủ tục", "error");
          return;
        }
        // onServiceTemplateChange's own state_patch already re-derives
        // staff_name/operator_signature_path server-side (operator_for_service,
        // web_bridge/__init__.py) from the operator_profiles just saved --
        // one source of truth instead of duplicating that same lookup here.
        if (state.service_template) await this.onServiceTemplateChange(state.service_template);
        CCCD.pushToast("Đã lưu giao dịch viên và phân công 5 dịch vụ", "success");
      },
      async saveDocumentSetSettings() {
        const result = await CCCD.bridge.saveDocumentSetSettings(this.documentSetSettings.selected);
        if (!result?.ok) {
          CCCD.pushToast(result?.message || "Không lưu được tài liệu theo dịch vụ", "error");
          return;
        }
        if (state.service_template) await this.onServiceTemplateChange(state.service_template);
        CCCD.pushToast("Đã lưu tài liệu theo dịch vụ", "success");
      },
    },
    template: `
      <div class="header">
        <div class="header__brand">
          <h1 class="header__title">CCCD Report</h1>
          <span class="header__subtitle">Tạo trọn bộ hồ sơ theo dịch vụ</span>
        </div>
        <div class="header__spacer"></div>
        <button class="btn" type="button" @click="openCompanyProfile">Thiết lập mặc định</button>
      </div>

      <div class="workspace" v-if="state.booted">
        <main class="workflow-card card card--content">
          <div class="workflow-card__heading">
            <h2 class="section-title">Folder nguồn và dịch vụ</h2>
            <button class="btn btn--ghost" type="button" @click="newCase">↻ Hồ sơ mới</button>
          </div>

          <div class="workflow-grid">
            <section class="setup-panel">
              <div class="setup-panel__label">Folder ảnh · có thể chọn trước</div>
              <div class="setup-panel__value" v-if="state.ui.sourceFolder">{{ state.ui.sourceFolder }}</div>
              <div class="setup-panel__value muted-text" v-else>Chưa chọn bộ hồ sơ</div>
              <div class="file-slot-row" v-if="state.ui.sourceFolder">
                <span v-for="number in sourceSlotNumbers" :key="number" class="file-slot"
                  :data-present="!!state.ui.sourceFiles[number]">{{ number }}</span>
              </div>
              <div class="folder-action-row">
                <button class="btn" type="button" @click="scanSourceFolder">Chọn folder hồ sơ…</button>
                <span v-if="state.ui.sourceFolder" class="folder-sync-status"
                  :data-busy="state.ui.sourceProcessing">
                  {{ state.ui.sourceProcessing ? 'Đang đồng bộ ảnh…' : 'Đã đồng bộ' }}
                </span>
              </div>
            </section>

            <section class="setup-panel">
              <label class="setup-panel__label" for="service-template">Dịch vụ</label>
              <select id="service-template" class="field__control"
                :value="state.service_template" @change="onServiceTemplateChange($event.target.value)">
                <option value="">— Chọn dịch vụ —</option>
                <option v-for="option in state.serviceTemplateOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
              <div v-if="selectedServiceOption" class="document-chip-row" aria-label="Tài liệu đầu ra">
                <span v-for="document in selectedServiceOption.documents" :key="document" class="document-chip">
                  {{ document }}
                </span>
              </div>
              <div v-if="state.ui.sourceFolder && missingSourceNumbers.length" class="inline-warning">
                Thiếu {{ missingSourceNumbers.map(number => number + '.jpg').join(', ') }}
              </div>
            </section>
          </div>

          <section class="subscriber-workflow" aria-labelledby="subscriber-workflow-title">
            <h3 id="subscriber-workflow-title" class="subscriber-workflow__heading">Số thuê bao</h3>
            <subscriber-list :layout="subscriberLayout" :root="state"
              @open-calendar="openCalendar" />
          </section>

          <div v-if="state.service_template" class="generation-bar">
            <div class="generation-bar__copy">
              <strong>Tạo {{ state.serviceDocumentCount }} loại tài liệu thành JPG</strong>
            </div>
            <button class="btn" type="button" :disabled="!canGenerateService"
              @click="generateServiceTemplateDocuments(false)">Lưu sang folder khác…</button>
            <button class="btn btn--primary" type="button" :disabled="!canGenerateService"
              @click="generateServiceTemplateDocuments(true)">
              <span v-if="hasPendingGenerations" class="btn-spinner" aria-hidden="true"></span>
              {{ hasPendingGenerations ? 'Đang tạo bộ hồ sơ ở nền…' : 'Tạo bộ hồ sơ vào folder nguồn' }}
            </button>
          </div>

          <section v-if="state.service_template" class="service-form-shell">
            <div class="service-form-heading">
              <h3>{{ selectedServiceOption && selectedServiceOption.label }}</h3>
              <div class="service-form-actions">
                <button class="btn btn--ghost" type="button" @click="updateFromProfileDefaults">
                  ↻ Nạp lại mặc định
                </button>
                <button class="btn btn--ghost" type="button"
                  :aria-expanded="state.ui.serviceFormOpen"
                  @click="state.ui.serviceFormOpen = !state.ui.serviceFormOpen">
                  {{ state.ui.serviceFormOpen ? 'Thu gọn' : 'Mở form' }}
                  <span class="collapse-caret" :data-open="state.ui.serviceFormOpen">⌄</span>
                </button>
              </div>
            </div>

            <tabs v-show="state.ui.serviceFormOpen" class="service-form-tabs"
              :tabs="serviceTabs" v-model="state.ui.activeTab" />
            <div v-show="state.ui.serviceFormOpen" class="service-tab-panel">
              <sectioned-form v-show="state.ui.activeTab === 'current_owner'"
                :sections="currentOwnerSections" :root="state" @open-calendar="openCalendar" />
              <div v-show="state.ui.activeTab === 'current_owner' && state.customer.entity_type === 'Tổ chức'"
                class="signature-upload">
                <img v-if="state.customer.signature_thumbnail" class="signature-upload__preview"
                  :src="state.customer.signature_thumbnail" alt="Chữ ký">
                <button class="btn" type="button"
                  @click="chooseCustomerRepresentativeSignature">Chọn ảnh chữ ký đại diện…</button>
                <button v-if="state.customer.signature_thumbnail" class="btn" type="button"
                  @click="clearCustomerRepresentativeSignature">Xóa ảnh chữ ký</button>
              </div>
              <sectioned-form v-show="state.ui.activeTab === 'new_owner'"
                :sections="newOwnerSections" :root="state" @open-calendar="openCalendar" />
              <sectioned-form v-show="state.ui.activeTab === 'transaction'"
                :sections="transactionSections" :root="state" @open-calendar="openCalendar" />
              <sectioned-form v-show="state.ui.activeTab === 'provider'"
                :sections="providerSections" :root="state" @open-calendar="openCalendar" />
            </div>

          </section>

        </main>
      </div>

      <calendar-popover v-if="calendar && !calendarInProfile" :anchor-rect="calendar.anchorRect"
        :value="calendarValue" @pick="pickDate" @close="calendar = null" />

      <signature-crop-modal v-if="cropModal" :source-data-url="cropModal.sourceDataUrl"
        :width-mm="state.signatureCropSize.width_mm" :height-mm="state.signatureCropSize.height_mm"
        @confirm="confirmSignatureCrop" @cancel="cropModal = null" />

      <dialog class="modal modal--settings" ref="profileDialog"
        @close="profile = null; representative = null; representative2 = null; operatorProfiles = null; providerSignature = null; documentSetSettings = null; calendar = null">
      <div class="settings-shell">
        <div class="settings-header">
          <div>
            <div class="eyebrow">Cấu hình dùng lại</div>
            <h2 class="modal__title">Thiết lập mặc định</h2>
            <p>Nhập một lần, ứng dụng sẽ sao chép vào form dịch vụ mới.</p>
          </div>
          <button class="settings-close" type="button" aria-label="Đóng"
            @click="$refs.profileDialog.close()">×</button>
        </div>

        <div class="settings-layout"
          v-if="profile && profileLayout && representative && representativeLayout && representative2 && representative2Layout && operatorProfiles && providerSignature && documentSetSettings">
          <nav class="settings-nav" aria-label="Nhóm thiết lập">
            <button v-for="item in profileNavItems" :key="item.id" type="button"
              :data-active="profileTab === item.id" @click="profileTab = item.id">
              <span class="settings-nav__number">{{ item.number }}</span>
              <span class="settings-nav__copy">
                <strong>{{ item.label }}</strong>
                <small>{{ item.hint }}</small>
              </span>
            </button>
          </nav>

          <section class="settings-content">
            <template v-if="profileTab === 'company'">
              <div class="settings-content__heading">
                <h3>Thông tin công ty</h3>
                <p>Dùng cho pháp nhân chủ cũ và đơn vị cung cấp.</p>
              </div>
              <organization-information-form :rows="profileLayout.primary_rows" :root="profileRoot"
                @open-calendar="openCalendar" />
            </template>

            <template v-else-if="profileTab === 'representative'">
              <div class="settings-content__heading">
                <h3>Người đại diện</h3>
                <p>Thông tin đại diện hợp pháp của doanh nghiệp.</p>
              </div>
              <personal-information-form :rows="representativeLayout.primary_rows"
                :root="representativeRoot" @open-calendar="openCalendar" />
              <div class="signature-upload">
                <img v-if="representative.signature_thumbnail" class="signature-upload__preview"
                  :src="representative.signature_thumbnail" alt="Chữ ký">
                <button class="btn" type="button"
                  @click="chooseRepresentativeSignature">Chọn ảnh chữ ký…</button>
                <button v-if="representative.signature_thumbnail" class="btn" type="button"
                  @click="clearRepresentativeSignature">Xóa ảnh chữ ký</button>
              </div>
            </template>

            <template v-else-if="profileTab === 'representative_2'">
              <div class="settings-content__heading">
                <h3>Người đại diện 2</h3>
                <p>Bên A ("người thực hiện chuyển chủ quyền") của dịch vụ Ccq Quang Hà - STT.</p>
              </div>
              <personal-information-form :rows="representative2Layout.primary_rows"
                :root="representative2Root" @open-calendar="openCalendar" />
              <div class="signature-upload">
                <img v-if="representative2.signature_thumbnail" class="signature-upload__preview"
                  :src="representative2.signature_thumbnail" alt="Chữ ký">
                <button class="btn" type="button"
                  @click="chooseRepresentative2Signature">Chọn ảnh chữ ký…</button>
                <button v-if="representative2.signature_thumbnail" class="btn" type="button"
                  @click="clearRepresentative2Signature">Xóa ảnh chữ ký</button>
              </div>
            </template>

            <template v-else-if="profileTab === 'operators'">
              <div class="settings-content__heading">
                <h3>Giao dịch viên</h3>
                <p>Mỗi dịch vụ phải được giao cho đúng một người. Dịch vụ đã chọn ở người khác sẽ tự khóa.</p>
              </div>
              <section class="operator-profile-card operator-profile-card--provider">
                <div class="operator-profile-card__title">Chữ ký/con dấu bên cung cấp dịch vụ (Võ Duy Nhật)</div>
                <div class="signature-upload">
                  <img v-if="providerSignature.signature_thumbnail" class="signature-upload__preview"
                    :src="providerSignature.signature_thumbnail" alt="Chữ ký">
                  <button class="btn" type="button" @click="chooseProviderSignature">Chọn ảnh chữ ký…</button>
                  <button v-if="providerSignature.signature_thumbnail" class="btn" type="button"
                    @click="clearProviderSignature">Xóa ảnh chữ ký</button>
                </div>
              </section>
              <div class="operator-profile-grid">
                <section v-for="(item, index) in operatorProfiles.profiles"
                  :key="item.profile_id" class="operator-profile-card">
                  <div class="operator-profile-card__header">
                    <div class="operator-profile-card__title">Giao dịch viên {{ index + 1 }}</div>
                    <button class="icon-button" type="button" aria-label="Xóa giao dịch viên"
                      @click="removeOperatorProfile(item.profile_id)">×</button>
                  </div>
                  <label class="field__label">Họ tên</label>
                  <input class="field__control" v-model="item.name"
                    placeholder="Nhập họ tên giao dịch viên">
                  <div class="signature-upload">
                    <img v-if="item.signature_thumbnail" class="signature-upload__preview"
                      :src="item.signature_thumbnail" alt="Chữ ký">
                    <button class="btn" type="button"
                      @click="chooseOperatorSignature(item.profile_id)">Chọn ảnh chữ ký…</button>
                    <button v-if="item.signature_thumbnail" class="btn" type="button"
                      @click="clearOperatorSignature(item.profile_id)">Xóa ảnh chữ ký</button>
                  </div>
                  <fieldset class="operator-assignment">
                    <legend>Dịch vụ phụ trách</legend>
                    <label v-for="service in operatorProfiles.services" :key="service.value"
                      :data-disabled="operatorServiceTaken(service.value, item.profile_id)">
                      <input type="checkbox" :value="service.value"
                        v-model="item.service_templates"
                        :disabled="operatorServiceTaken(service.value, item.profile_id)">
                      <span>{{ service.label }}</span>
                    </label>
                  </fieldset>
                </section>
              </div>
              <button class="btn add-operator-button" type="button" @click="addOperatorProfile">
                + Thêm người giao dịch
              </button>
            </template>

            <template v-else>
              <div class="settings-content__heading">
                <h3>Tài liệu theo dịch vụ</h3>
                <p>Đề phòng dịch vụ bị xác định sai: bật/tắt tay từng tài liệu tạo ra cho mỗi dịch vụ.</p>
              </div>
              <div class="document-set-grid">
                <section v-for="service in documentSetSettings.services" :key="service.value"
                  class="document-set-card">
                  <div class="document-set-card__title">{{ service.label }}</div>
                  <label v-for="doc in documentSetSettings.documents" :key="doc.value">
                    <input type="checkbox" :value="doc.value"
                      v-model="documentSetSettings.selected[service.value]">
                    <span>{{ doc.label }}</span>
                  </label>
                </section>
              </div>
            </template>
          </section>
        </div>

        <div class="modal__actions settings-actions">
          <button v-if="profileTab === 'company'" class="btn btn--primary" type="button"
            @click="saveProfile">Lưu thông tin công ty</button>
          <button v-else-if="profileTab === 'representative'" class="btn btn--primary" type="button"
            @click="saveRepresentativeProfile">Lưu người đại diện</button>
          <button v-else-if="profileTab === 'representative_2'" class="btn btn--primary" type="button"
            @click="saveRepresentative2Profile">Lưu người đại diện 2</button>
          <button v-else-if="profileTab === 'operators'" class="btn btn--primary" type="button"
            @click="saveOperatorProfiles">Lưu giao dịch viên</button>
          <button v-else class="btn btn--primary" type="button"
            @click="saveDocumentSetSettings">Lưu tài liệu theo dịch vụ</button>
          <button class="btn" type="button" @click="$refs.profileDialog.close()">Đóng</button>
        </div>
      </div>
        <calendar-popover v-if="calendar && calendarInProfile" :anchor-rect="calendar.anchorRect"
          :value="calendarValue" @pick="pickDate" @close="calendar = null" />
      </dialog>

      <toast-stack />
      <div class="status-bar">{{ state.ui.statusMessage }}</div>
    `,
  };

  const app = Vue.createApp(App);
  app.config.globalProperties.CCCD = CCCD;
  app.component("CompositionSafeControl", CCCD.components.CompositionSafeControl);
  app.component("FieldInput", CCCD.components.FieldInput);
  app.component("CheckboxGroup", CCCD.components.CheckboxGroup);
  app.component("FormGrid", CCCD.components.FormGrid);
  app.component("SectionedForm", CCCD.components.SectionedForm);
  app.component("SubscriberList", CCCD.components.SubscriberList);
  app.component("PersonalInformationForm", CCCD.components.PersonalInformationForm);
  app.component("OrganizationInformationForm", CCCD.components.OrganizationInformationForm);
  app.component("Disclosure", CCCD.components.Disclosure);
  app.component("Tabs", CCCD.components.Tabs);
  app.component("CalendarPopover", CCCD.components.CalendarPopover);
  app.component("SignatureCropModal", CCCD.components.SignatureCropModal);
  app.component("ToastStack", CCCD.components.ToastStack);
  app.mount("#app");
})();
