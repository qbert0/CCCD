(function () {
  const state = CCCD.state;

  const App = {
    data() {
      return {
        state,
        calendar: null, // { field, anchorRect } | null
        reviewOpen: false,
        reviewSummary: "",
        profile: null, // PersonData dict while the company-profile dialog is open
        profileLayout: null,
        representative: null, // PersonData dict for the "Người đại diện" sub-tab session record
        representativeLayout: null,
        profileTab: "company", // "company" | "representative" sub-tab inside the dialog
        // Each document type owns a session-local editable copy. Saved
        // company/representative profiles are copied in only when the draft
        // is first created or the user explicitly presses the update button.
        documentDrafts: {},
        // Identity and subscriber number belong to the current customer
        // case, not to one document draft. Organization-first documents
        // render that person under `new_owner`; other documents use
        // `customer`, so document switches need an explicit shared copy.
        caseCustomer: {},
        caseSubscriberNumber: "",
        resettingCase: false,
      };
    },
    computed: {
      documentReady() {
        return !!state.document_type;
      },
      customerTabRows() {
        return state.layouts.customer;
      },
      newOwnerTabRows() {
        return state.layouts.new_owner;
      },
      representativeTabRows() {
        return state.layouts.representative;
      },
      documentTabLayout() {
        return state.layouts.document;
      },
      simTabLayout() {
        return state.layouts.sims;
      },
      isTransfer() {
        return state.document_type === "transfer";
      },
      isPrepaid() {
        return state.document_type === "prepaid_contract";
      },
      usesOrganizationCustomer() {
        return state.document_type === "transfer" || state.document_type === "aftersale" || this.isPrepaid;
      },
      calendarValue() {
        if (!this.calendar) return "";
        return CCCD.getByPath(this.calendar.root || state, this.calendar.field.path) || "";
      },
      calendarInProfile() {
        const path = this.calendar?.field?.path || "";
        return !!this.profile && (
          path.startsWith("profile.") || path.startsWith("representative.")
        );
      },
      // Organization-first documents show a single intake card (visually
      // where "customer" sits) but its images belong to the person in the
      // second tab -- mirrors
      // HomePage._upload_card_for_target()/_start_primary_ocr() in the old
      // PyQt UI: the widget position is fixed, the OCR target it feeds is
      // not.
      primaryUploadTarget() {
        return this.usesOrganizationCustomer ? "new_owner" : "customer";
      },
      // Wraps the open profile dialog's PersonData so field paths resolved
      // as "profile.full_name" (see get_company_profile_layout()) land on
      // this.profile.full_name -- same getByPath/setByPath FieldInput uses
      // everywhere else, just a differently-rooted object than CCCD.state.
      profileRoot() {
        return { profile: this.profile || {} };
      },
      representativeRoot() {
        return { representative: this.representative || {} };
      },
      profileTabsList() {
        return [
          { id: "company", label: "Thông tin công ty", visible: true },
          { id: "representative", label: "Người đại diện", visible: true },
        ];
      },
      tabsList() {
        const t = state.ui.tabs;
        return [
          { id: "customer", label: t.customerLabel, visible: true },
          { id: "representative", label: t.representativeLabel, visible: t.representativeTabVisible },
          { id: "new_owner", label: t.newOwnerLabel, visible: t.newOwnerTabVisible },
          { id: "document", label: t.documentLabel, visible: true },
          { id: "sims", label: t.simsLabel, visible: t.simsTabVisible },
        ];
      },
    },
    watch: {
      // One-directional only: typing a subscriber number in the scan column
      // pushes it into Beautiful Number's table row 1, but editing row 1
      // itself must never write back here (explicit request) -- an empty
      // scan-column value leaves row 1 exactly as it already is.
      "state.subscriber_number"(value) {
        this.caseSubscriberNumber = value == null ? "" : String(value);
        if (value) state.subscriber_number_1 = value;
        if (state.document_type === "beautiful_number" && state.beautiful_subscribers?.length && value) {
          state.beautiful_subscribers[0].subscriber_number = value;
        }
        if (state.document_type === "prepaid_contract" && state.prepaid_subscribers?.length) {
          state.prepaid_subscribers[0].subscriber_number = value || "";
        }
      },
      "state.customer": {
        deep: true,
        handler(value) {
          this.rememberCaseCustomer("customer", value);
        },
      },
      "state.new_owner": {
        deep: true,
        handler(value) {
          this.rememberCaseCustomer("new_owner", value);
        },
      },
    },
    async mounted() {
      await CCCD.bridgeReady;
      const initial = await CCCD.bridge.getInitialState();
      Object.assign(state, initial.state);
      state.documentTypeOptions = initial.document_type_options;
      state.booted = true;

      CCCD.bridge.onOcrProgress((target, done, total) => {
        state.ui.upload[target].progress = { done, total };
        state.ui.upload[target].busy = true;
      });
      // "representative" is a 3rd OCR target -- the Company Profile dialog's
      // own "Người đại diện" intake card, writing into this.representative
      // (a dialog-local session record) instead of the main case's
      // state.customer/new_owner, and skipping the main-window raw-OCR
      // panel/tab switch below (that dialog has no such panel of its own).
      const personFor = (target) =>
        target === "customer" ? state.customer : target === "new_owner" ? state.new_owner : this.representative;

      CCCD.bridge.onOcrFileResult((target, result) => {
        const up = state.ui.upload[target];
        if (result.error || result.side === "unknown") {
          up.status = "Chưa xác định được mặt CCCD";
          up.invalid = true;
          up.note = result.error || "Ảnh chưa đủ rõ để nhận biết mặt trước/mặt sau. Ảnh cũ vẫn được giữ nguyên.";
          return;
        }
        up[result.side] = { thumbnail: result.thumbnail_data_url, filename: `${result.filename} · ${result.source}` };
        const person = personFor(target);
        if (person) {
          CCCD.mergeNonEmpty(person, result.fields);
          this.rememberCaseCustomer(target, result.fields);
        }
      });
      CCCD.bridge.onOcrBatchFinished((target, result) => {
        const up = state.ui.upload[target];
        up.progress = null;
        up.busy = false;
        const person = personFor(target);
        if (result.accepted && person) {
          // A missing OCR field means "not read", not "erase the value the
          // user already had". This also updates the shared case identity
          // immediately, before any document switch can occur.
          CCCD.mergeNonEmpty(person, result.fields);
          this.rememberCaseCustomer(target, result.fields);
        }
        up.note = (result.warnings || []).join("\n");
        up.invalid = !!up.note;
        if (target === "representative") {
          state.ui.statusMessage = result.accepted
            ? "Đã đọc xong CCCD người đại diện · hãy đối chiếu các trường vừa điền"
            : "Chưa nhận biết được mặt CCCD · ảnh hiện có vẫn được giữ";
          return;
        }
        const label = target === "customer" || (
          target === "new_owner" && ["aftersale", "prepaid_contract"].includes(state.document_type)
        )
          ? "KHÁCH HÀNG"
          : "CHỦ THUÊ BAO MỚI";
        state.ui.ocrRawText[target] = `===== ${label} =====\n${result.raw_text}`;
        state.ui.ocrPanelOpen = true;
        state.ui.activeTab = target === "customer" ? "customer" : "new_owner";
        state.ui.statusMessage = result.accepted
          ? "Đã đọc xong các mặt CCCD · hãy đối chiếu những trường vừa điền"
          : "Chưa nhận biết được mặt CCCD · ảnh hiện có vẫn được giữ";
      });
      CCCD.bridge.onOcrBatchFailed((target, message) => {
        const up = state.ui.upload[target];
        up.progress = null;
        up.busy = false;
        up.status = "Không đọc được ảnh mới";
        up.invalid = true;
        up.note = message;
        CCCD.pushToast(message, "error");
      });
    },
    methods: {
      caseCustomerKey(documentType = state.document_type) {
        return ["transfer", "aftersale", "prepaid_contract"].includes(documentType)
          ? "new_owner"
          : "customer";
      },
      rememberCaseCustomer(sourceKey, fields) {
        if (this.resettingCase || sourceKey === "representative") return;
        if (sourceKey !== this.caseCustomerKey()) return;
        CCCD.mergeNonEmpty(this.caseCustomer, fields);
      },
      captureCaseContext(documentType = state.document_type) {
        if (this.resettingCase) return;
        const sourceKey = this.caseCustomerKey(documentType);
        CCCD.mergeNonEmpty(this.caseCustomer, state[sourceKey] || {});
        this.caseSubscriberNumber = state.subscriber_number == null
          ? ""
          : String(state.subscriber_number);
      },
      applyCaseContext(snapshot, documentType) {
        const targetKey = this.caseCustomerKey(documentType);
        if (!snapshot[targetKey] || typeof snapshot[targetKey] !== "object") {
          snapshot[targetKey] = {};
        }
        // Sparse merge by design: fields absent from the shared customer
        // record must not blank a value already edited in this document.
        CCCD.mergeNonEmpty(snapshot[targetKey], this.caseCustomer);
        if (this.caseSubscriberNumber) {
          snapshot.subscriber_number = this.caseSubscriberNumber;
          snapshot.subscriber_number_1 = this.caseSubscriberNumber;
          // These two documents print row 1 from their structured table,
          // not directly from the root subscriber_number. Update the row
          // here as well; relying on the Vue watcher would miss switches
          // where the root value happens to be unchanged.
          if (documentType === "beautiful_number" && snapshot.beautiful_subscribers?.length) {
            snapshot.beautiful_subscribers[0].subscriber_number = this.caseSubscriberNumber;
          }
          if (documentType === "prepaid_contract" && snapshot.prepaid_subscribers?.length) {
            snapshot.prepaid_subscribers[0].subscriber_number = this.caseSubscriberNumber;
          }
        }
      },
      async onDocumentTypeChange(newType, options = {}) {
        const previous = state.document_type;
        const switching = previous !== newType;
        const clone = (value) => JSON.parse(JSON.stringify(value));

        this.captureCaseContext(previous);
        if (switching && previous && !options.skipDraftSave) {
          this.documentDrafts[previous] = clone(CCCD.reportDataSnapshot());
        }

        let snapshot;
        let applyProfileDefaults = !!options.forceProfileDefaults;
        if (!switching) {
          snapshot = clone(CCCD.reportDataSnapshot());
        } else if (newType && this.documentDrafts[newType]) {
          snapshot = clone(this.documentDrafts[newType]);
        } else {
          snapshot = await CCCD.bridge.getNewDocumentState(newType);
          applyProfileDefaults = !!newType;
        }
        snapshot.document_type = newType;
        this.applyCaseContext(snapshot, newType);

        const result = await CCCD.bridge.onDocumentTypeChanged({
          previous_document_type: previous,
          new_document_type: newType,
          state: snapshot,
          apply_profile_defaults: applyProfileDefaults,
          preserve_subject: false,
        });
        if (switching || options.replaceState) Object.assign(state, snapshot);
        state.document_type = newType;
        CCCD.applyStatePatch(result.state_patch);
        Object.assign(state.ui, result.ui, { errors: state.ui.errors, upload: state.ui.upload, toasts: state.ui.toasts });
        state.layouts.customer = result.layouts.customer;
        state.layouts.representative = result.layouts.representative;
        state.layouts.new_owner = result.layouts.new_owner;
        state.layouts.document = result.layouts.document;
        state.layouts.sims = result.layouts.sims;
        state.ui.activeTab = "customer";
        if (newType) this.documentDrafts[newType] = clone(CCCD.reportDataSnapshot());
      },
      async onEntityTypeChange(form) {
        const entityType = form === "customer" ? state.customer.entity_type : state.new_owner.entity_type;
        const layout = await CCCD.bridge.onEntityTypeChanged(form, entityType);
        state.layouts[form] = layout;
      },
      openCalendar({ field, root, $event }) {
        this.calendar = { field, root, anchorRect: $event.target.getBoundingClientRect() };
      },
      pickDate(value) {
        CCCD.setByPath(this.calendar.root || state, this.calendar.field.path, value);
        delete state.ui.errors[this.calendar.field.path];
        if (this.calendar.field.path === "prepaid_subscribers.0.activation_date") {
          state.activation_date = value;
        }
        this.calendar = null;
      },
      toggleDetail(section) {
        state.ui.detailOpen[section] = !state.ui.detailOpen[section];
      },
      async openReview() {
        const errors = await CCCD.bridge.validate(CCCD.reportDataSnapshot());
        state.ui.errors = {};
        if (errors.length) {
          for (const e of errors) state.ui.errors[e.path] = e.message;
          const first = errors[0].path;
          state.ui.activeTab = first.startsWith("customer.") ? "customer"
            : first.startsWith("representative.") ? "representative"
            : first.startsWith("new_owner.") ? "new_owner"
            : first.startsWith("prepaid_subscribers.") ? "sims" : "document";
          state.ui.statusMessage = `Còn ${errors.length} trường cần bổ sung · xem thông báo màu đỏ dưới ô nhập`;
          return;
        }
        this.reviewSummary = await CCCD.bridge.getReviewSummary(CCCD.reportDataSnapshot());
        this.reviewOpen = true;
        this.$nextTick(() => this.$refs.reviewDialog.showModal());
      },
      async confirmExport() {
        this.$refs.reviewDialog.close();
        this.reviewOpen = false;
        const result = await CCCD.bridge.exportDocument(CCCD.reportDataSnapshot());
        if (result.ok) {
          CCCD.pushToast(`Đã tạo ${result.path}`, "success");
          state.ui.statusMessage = `Đã tạo tài liệu`;
        } else if (result.message) {
          CCCD.pushToast(result.message, "error");
        }
      },
      async preview() {
        const result = await CCCD.bridge.previewDocument(CCCD.reportDataSnapshot());
        if (!result.ok) CCCD.pushToast(result.message, "error");
      },
      async newCase() {
        const documentType = state.document_type;
        this.resettingCase = true;
        try {
          const fresh = await CCCD.bridge.newCase(CCCD.reportDataSnapshot());
          this.caseCustomer = {};
          this.caseSubscriberNumber = "";
          this.documentDrafts = {};
          Object.assign(state, fresh);
          state.ui.upload.customer = { front: null, back: null, status: "Chưa có ảnh", invalid: false, note: "", busy: false, progress: null };
          state.ui.upload.new_owner = { front: null, back: null, status: "Chưa có ảnh", invalid: false, note: "", busy: false, progress: null };
          state.ui.ocrRawText = { customer: "", new_owner: "" };
          state.ui.ocrPanelOpen = false;
          state.ui.errors = {};
          state.ui.activeTab = "customer";
          if (documentType) {
            await this.onDocumentTypeChange(documentType, {
              forceProfileDefaults: true,
              replaceState: true,
              skipDraftSave: true,
            });
          }
        } finally {
          this.resettingCase = false;
        }
        state.ui.statusMessage = "Đã mở hồ sơ mới · đã áp dụng thông tin mặc định mới nhất";
      },
      async updateFromProfileDefaults() {
        if (!state.document_type) return;
        const patch = await CCCD.bridge.applyProfileDefaults(state.document_type);
        CCCD.applyStatePatch(patch);
        for (const path of Object.keys(state.ui.errors)) {
          if (
            path.startsWith("customer.") || path.startsWith("representative.") ||
            [
              "shop_name", "shop_address", "shop_phone", "shop_phone_2",
              "shop_id_number", "shop_issue_date", "shop_issue_place",
              "provider_representative", "provider_position", "provider_phone",
              "provider_email", "provider_unit_address",
            ].includes(path)
          ) delete state.ui.errors[path];
        }
        this.documentDrafts[state.document_type] = JSON.parse(
          JSON.stringify(CCCD.reportDataSnapshot())
        );
        CCCD.pushToast("Đã cập nhật tài liệu từ thông tin công ty và người đại diện", "success");
      },
      async openCompanyProfile() {
        const [person, layout, representative, representativeLayout] = await Promise.all([
          CCCD.bridge.getCompanyProfile(), CCCD.bridge.getCompanyProfileLayout(),
          CCCD.bridge.getRepresentativeProfile(), CCCD.bridge.getRepresentativeProfileLayout(),
        ]);
        this.profile = person;
        this.profileLayout = layout;
        this.representative = representative;
        this.representativeLayout = representativeLayout;
        this.profileTab = "company";
        for (const key of Object.keys(state.ui.errors)) {
          if (key.startsWith("profile.") || key.startsWith("representative.")) delete state.ui.errors[key];
        }
        this.$nextTick(() => this.$refs.profileDialog.showModal());
      },
      async saveProfile() {
        const result = await CCCD.bridge.saveCompanyProfile(this.profile);
        if (!result.ok) {
          for (const e of result.errors) state.ui.errors[e.path] = e.message;
          return;
        }
        this.$refs.profileDialog.close();
        this.profile = null;
        this.representative = null;
        CCCD.pushToast("Đã lưu mặc định công ty · dùng nút cập nhật để áp dụng lại vào tài liệu đang sửa", "success");
      },
      async saveRepresentativeProfile() {
        const result = await CCCD.bridge.saveRepresentativeProfile(this.representative);
        if (!result.ok) {
          for (const e of result.errors) state.ui.errors[e.path] = e.message;
          return;
        }
        this.$refs.profileDialog.close();
        this.profile = null;
        this.representative = null;
        CCCD.pushToast("Đã lưu mặc định người đại diện · dùng nút cập nhật để áp dụng lại vào tài liệu đang sửa", "success");
      },
    },
    template: `
      <div class="header">
        <div class="header__brand">
          <h1 class="header__title">CCCD Report</h1>
          <span class="header__subtitle">Nhận dạng căn cước và tạo tài liệu</span>
        </div>
        <div class="header__spacer"></div>
        <button class="btn" type="button" @click="openCompanyProfile">Thông tin công ty</button>
      </div>

      <div class="workspace" v-if="state.booted">
        <div class="column-scan">
          <div style="display:flex; gap: var(--space-sm); align-items:flex-start;">
            <div class="field" style="flex:1;">
              <input class="field__control" type="text" placeholder="Nhập số thuê bao"
                v-model="state.subscriber_number">
            </div>
            <button class="btn btn--ghost" type="button" @click="newCase">↻ Hồ sơ mới</button>
          </div>

          <upload-card :target="primaryUploadTarget" />
          <upload-card v-if="state.ui.tabs.newOwnerUploadVisible" target="new_owner" />

          <div class="card card--ocr">
            <disclosure v-model="state.ui.ocrPanelOpen" label="Kết quả OCR">
              <textarea class="field__control" readonly style="min-height:220px; font-family: var(--font-family-mono); font-size:11px;"
                :value="Object.values(state.ui.ocrRawText).filter(Boolean).join('\\n\\n')"
                placeholder="Văn bản từ CCCD sẽ hiển thị tại đây"></textarea>
            </disclosure>
          </div>
        </div>

        <div class="column-form card card--content">
          <select class="field__control" style="min-width:420px; max-width:420px;"
            :value="state.document_type" @change="onDocumentTypeChange($event.target.value)">
            <option value="">Chọn biểu mẫu</option>
            <option v-for="opt in state.documentTypeOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>

          <template v-if="documentReady">
            <p class="document-title">{{ state.ui.documentFullTitle }}</p>
            <tabs :tabs="tabsList" v-model="state.ui.activeTab" />

            <div class="tabpanel" v-show="state.ui.activeTab === 'customer'" style="overflow-y:auto; flex:1;">
              <subscriber-information-form v-if="isTransfer" :rows="customerTabRows.primary_rows"
                :root="state" @open-calendar="openCalendar"
                @entity-type-changed="onEntityTypeChange('customer')" />
              <organization-information-form v-else-if="usesOrganizationCustomer" :rows="customerTabRows.primary_rows"
                :root="state" @open-calendar="openCalendar" />
              <form-grid v-else :rows="customerTabRows.primary_rows" :root="state" @open-calendar="openCalendar" @entity-type-changed="onEntityTypeChange('customer')" />
              <disclosure v-if="customerTabRows.has_detail" v-model="state.ui.detailOpen.customer" label="Thông tin chi tiết" style="margin-top: var(--space-sm);">
                <form-grid :rows="customerTabRows.detail_rows" :root="state" @open-calendar="openCalendar" @entity-type-changed="onEntityTypeChange('customer')" />
              </disclosure>
            </div>

            <div class="tabpanel" v-show="state.ui.activeTab === 'new_owner'" style="overflow-y:auto; flex:1;">
              <subscriber-information-form v-if="isTransfer" :rows="newOwnerTabRows.primary_rows"
                :root="state" @open-calendar="openCalendar"
                @entity-type-changed="onEntityTypeChange('new_owner')" />
              <personal-information-form v-else-if="isPrepaid" :rows="newOwnerTabRows.primary_rows"
                :root="state" @open-calendar="openCalendar" />
              <form-grid v-else :rows="newOwnerTabRows.primary_rows" :root="state" @open-calendar="openCalendar" @entity-type-changed="onEntityTypeChange('new_owner')" />
              <disclosure v-if="newOwnerTabRows.has_detail" v-model="state.ui.detailOpen.new_owner" label="Thông tin chi tiết" style="margin-top: var(--space-sm);">
                <form-grid :rows="newOwnerTabRows.detail_rows" :root="state" @open-calendar="openCalendar" @entity-type-changed="onEntityTypeChange('new_owner')" />
              </disclosure>
            </div>

            <div class="tabpanel" v-show="state.ui.activeTab === 'representative'" style="overflow-y:auto; flex:1;">
              <personal-information-form :rows="representativeTabRows.primary_rows"
                :root="state" @open-calendar="openCalendar" />
            </div>

            <div class="tabpanel" v-show="state.ui.activeTab === 'document'" style="overflow-y:auto; flex:1;">
              <sectioned-form v-if="isPrepaid" :sections="documentTabLayout.sections || []"
                :root="state" @open-calendar="openCalendar" />
              <template v-else>
                <form-grid :rows="documentTabLayout.common_rows" :root="state" @open-calendar="openCalendar" />
                <form-grid :rows="documentTabLayout.primary_rows" :root="state" @open-calendar="openCalendar"
                  :style="{ marginTop: documentTabLayout.common_rows.length ? '11px' : '0' }" />
              </template>
              <disclosure v-if="documentTabLayout.has_detail" v-model="state.ui.detailOpen.document" label="Thông tin chi tiết" style="margin-top: var(--space-sm);">
                <form-grid :rows="documentTabLayout.detail_rows" :root="state" @open-calendar="openCalendar" />
              </disclosure>
              <div class="field" style="margin-top: var(--space-sm);" v-if="documentTabLayout.notes_field">
                <label class="field__label">{{ documentTabLayout.notes_field.label }}</label>
                <textarea class="field__control" style="max-height:76px;" :placeholder="documentTabLayout.notes_field.placeholder"
                  v-model="state.notes"></textarea>
              </div>
            </div>

            <div class="tabpanel" v-show="state.ui.activeTab === 'sims'" style="overflow-y:auto; flex:1;">
              <prepaid-sim-table v-if="isPrepaid" :layout="simTabLayout" :root="state"
                @open-calendar="openCalendar" />
            </div>
          </template>

          <div v-else class="empty-state">
            <div class="empty-state__title">Chưa chọn biểu mẫu</div>
            <div class="empty-state__hint">Chọn một loại tài liệu ở trên để bắt đầu điền thông tin</div>
          </div>

          <div class="action-bar">
            <button class="btn btn--ghost" style="margin-right:auto;" type="button"
              :disabled="!documentReady" @click="updateFromProfileDefaults">
              ↻ Cập nhật từ thông tin mặc định
            </button>
            <button class="btn" type="button" :disabled="!documentReady" @click="preview">Xem trước</button>
            <button class="btn btn--primary" type="button" :disabled="!documentReady" @click="openReview">Tạo tài liệu</button>
          </div>
        </div>
      </div>

      <calendar-popover v-if="calendar && !calendarInProfile" :anchor-rect="calendar.anchorRect"
        :value="calendarValue"
        @pick="pickDate" @close="calendar = null" />

      <dialog class="modal" ref="reviewDialog" @close="reviewOpen = false">
        <div class="modal__body">
          <h2 class="modal__title">Kiểm tra lần cuối trước khi tạo tài liệu</h2>
          <p class="muted-text">Đối chiếu các thông tin dưới đây với hai mặt CCCD. Quay lại nếu có bất kỳ sai lệch nào.</p>
          <pre style="white-space:pre-wrap; font-size:13px;">{{ reviewSummary }}</pre>
        </div>
        <div class="modal__actions">
          <button class="btn" type="button" @click="$refs.reviewDialog.close()">Quay lại chỉnh sửa</button>
          <button class="btn btn--primary" type="button" @click="confirmExport">Thông tin chính xác</button>
        </div>
      </dialog>

      <dialog class="modal" ref="profileDialog" @close="profile = null; representative = null; calendar = null" style="width:min(900px,92vw);">
        <div class="modal__body" v-if="profile && profileLayout && representative && representativeLayout">
          <h2 class="modal__title">Thông tin công ty</h2>
          <tabs :tabs="profileTabsList" v-model="profileTab" style="margin-bottom: var(--space-sm);" />

          <template v-if="profileTab === 'company'">
            <p class="muted-text">Thông tin cố định của công ty, ít thay đổi — tự áp dụng làm mặc định cho mọi tài liệu (Bên A, người đại diện ký...). Sửa riêng cho một tài liệu cụ thể ở màn hình kiểm tra thông tin sẽ không ghi đè lên hồ sơ mặc định này.</p>
            <organization-information-form :rows="profileLayout.primary_rows" :root="profileRoot"
              @open-calendar="openCalendar" />
          </template>

          <template v-else>
            <p class="muted-text">Hồ sơ người đại diện hợp pháp của công ty — lưu riêng một lần, tự áp dụng làm "Người đại diện" cho các tài liệu cần đến (Giấy cam kết sau bán hàng...).</p>
            <upload-card target="representative" />
            <personal-information-form :rows="representativeLayout.primary_rows" :root="representativeRoot"
              @open-calendar="openCalendar" style="margin-top: var(--space-sm);" />
          </template>
        </div>
        <div class="modal__actions">
          <button class="btn" type="button" @click="$refs.profileDialog.close()">Hủy</button>
          <button v-if="profileTab === 'company'" class="btn btn--primary" type="button" @click="saveProfile">Lưu thông tin công ty</button>
          <button v-else class="btn btn--primary" type="button" @click="saveRepresentativeProfile">Lưu thông tin người đại diện</button>
        </div>
        <calendar-popover v-if="calendar && calendarInProfile" :anchor-rect="calendar.anchorRect"
          :value="calendarValue" @pick="pickDate" @close="calendar = null" />
      </dialog>

      <toast-stack />
      <div class="status-bar">{{ state.ui.statusMessage }}</div>
    `,
  };

  const app = Vue.createApp(App);
  // In-DOM/string templates resolve bare identifiers via `with(this)`, so a
  // plain global like `CCCD` is invisible inside a <template> string unless
  // it's also exposed as an instance property -- globalProperties does that
  // for every component at once instead of repeating a `computed: { CCCD:
  // () => CCCD }` on each one that needs it (ToastStack, FieldInput, ...).
  app.config.globalProperties.CCCD = CCCD;
  app.component("FieldInput", CCCD.components.FieldInput);
  app.component("CheckboxGroup", CCCD.components.CheckboxGroup);
  app.component("SubscriberTable", CCCD.components.SubscriberTable);
  app.component("FormGrid", CCCD.components.FormGrid);
  app.component("SectionedForm", CCCD.components.SectionedForm);
  app.component("PrepaidSimTable", CCCD.components.PrepaidSimTable);
  app.component("PersonalInformationForm", CCCD.components.PersonalInformationForm);
  app.component("OrganizationInformationForm", CCCD.components.OrganizationInformationForm);
  app.component("SubscriberInformationForm", CCCD.components.SubscriberInformationForm);
  app.component("Disclosure", CCCD.components.Disclosure);
  app.component("Tabs", CCCD.components.Tabs);
  app.component("UploadCard", CCCD.components.UploadCard);
  app.component("CalendarPopover", CCCD.components.CalendarPopover);
  app.component("ToastStack", CCCD.components.ToastStack);
  app.mount("#app");
})();
