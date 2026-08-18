(function () {
  const state = CCCD.state;

  const App = {
    data() {
      return {
        state,
        calendar: null, // { field, anchorRect } | null
        reviewOpen: false,
        reviewSummary: "",
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
      documentTabLayout() {
        return state.layouts.document;
      },
      tabsList() {
        const t = state.ui.tabs;
        return [
          { id: "customer", label: t.customerLabel, visible: true },
          { id: "new_owner", label: t.newOwnerLabel, visible: t.newOwnerTabVisible },
          { id: "document", label: t.documentLabel, visible: true },
        ];
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
      CCCD.bridge.onOcrFileResult((target, result) => {
        const up = state.ui.upload[target];
        if (result.error || result.side === "unknown") {
          up.status = "Chưa xác định được mặt CCCD";
          up.invalid = true;
          up.note = result.error || "Ảnh chưa đủ rõ để nhận biết mặt trước/mặt sau. Ảnh cũ vẫn được giữ nguyên.";
          return;
        }
        up[result.side] = { thumbnail: result.thumbnail_data_url, filename: `${result.filename} · ${result.source}` };
        const person = target === "customer" ? state.customer : state.new_owner;
        CCCD.mergeNonEmpty(person, result.fields);
      });
      CCCD.bridge.onOcrBatchFinished((target, result) => {
        const up = state.ui.upload[target];
        up.progress = null;
        up.busy = false;
        if (result.accepted) {
          const person = target === "customer" ? state.customer : state.new_owner;
          Object.assign(person, result.fields);
        }
        up.note = (result.warnings || []).join("\n");
        up.invalid = !!up.note;
        const label = target === "customer" ? "KHÁCH HÀNG" : "CHỦ THUÊ BAO MỚI";
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
      async onDocumentTypeChange(newType) {
        const previous = state.document_type;
        const snapshot = CCCD.reportDataSnapshot();
        const result = await CCCD.bridge.onDocumentTypeChanged({
          previous_document_type: previous,
          new_document_type: newType,
          state: { ...snapshot, document_type: newType },
        });
        state.document_type = newType;
        CCCD.applyStatePatch(result.state_patch);
        Object.assign(state.ui, result.ui, { errors: state.ui.errors, upload: state.ui.upload, toasts: state.ui.toasts });
        state.layouts.customer = result.layouts.customer;
        state.layouts.new_owner = result.layouts.new_owner;
        state.layouts.document = result.layouts.document;
        state.ui.activeTab = "customer";
      },
      async onEntityTypeChange(form) {
        const entityType = form === "customer" ? state.customer.entity_type : state.new_owner.entity_type;
        const layout = await CCCD.bridge.onEntityTypeChanged(form, entityType);
        state.layouts[form] = layout;
      },
      openCalendar({ field, $event }) {
        this.calendar = { field, anchorRect: $event.target.getBoundingClientRect() };
      },
      pickDate(value) {
        CCCD.setByPath(state, this.calendar.field.path, value);
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
          state.ui.activeTab = first.startsWith("customer.") ? "customer" : first.startsWith("new_owner.") ? "new_owner" : "document";
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
    },
    template: `
      <div class="header">
        <div class="header__brand">
          <h1 class="header__title">CCCD Report</h1>
          <span class="header__subtitle">Nhận dạng căn cước và tạo tài liệu</span>
        </div>
        <div class="header__spacer"></div>
        <button class="btn" type="button">Thông tin công ty</button>
      </div>

      <div class="workspace" v-if="state.booted">
        <div class="column-scan">
          <div style="display:flex; gap: var(--space-sm); align-items:flex-start;">
            <div class="field" style="flex:1;">
              <input class="field__control" type="text" placeholder="Nhập số thuê bao"
                v-model="state.subscriber_number">
            </div>
            <button class="btn btn--ghost" type="button">↻ Hồ sơ mới</button>
          </div>

          <upload-card target="customer" />
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
              <form-grid :rows="customerTabRows.primary_rows" :root="state" @open-calendar="openCalendar" />
              <disclosure v-if="customerTabRows.has_detail" v-model="state.ui.detailOpen.customer" label="Thông tin chi tiết" style="margin-top: var(--space-sm);">
                <form-grid :rows="customerTabRows.detail_rows" :root="state" @open-calendar="openCalendar" />
              </disclosure>
            </div>

            <div class="tabpanel" v-show="state.ui.activeTab === 'new_owner'" style="overflow-y:auto; flex:1;">
              <form-grid :rows="newOwnerTabRows.primary_rows" :root="state" @open-calendar="openCalendar" />
              <disclosure v-if="newOwnerTabRows.has_detail" v-model="state.ui.detailOpen.new_owner" label="Thông tin chi tiết" style="margin-top: var(--space-sm);">
                <form-grid :rows="newOwnerTabRows.detail_rows" :root="state" @open-calendar="openCalendar" />
              </disclosure>
            </div>

            <div class="tabpanel" v-show="state.ui.activeTab === 'document'" style="overflow-y:auto; flex:1;">
              <form-grid :rows="documentTabLayout.common_rows" :root="state" @open-calendar="openCalendar" />
              <form-grid :rows="documentTabLayout.primary_rows" :root="state" @open-calendar="openCalendar" style="margin-top:11px;" />
              <disclosure v-if="documentTabLayout.has_detail" v-model="state.ui.detailOpen.document" label="Thông tin chi tiết" style="margin-top: var(--space-sm);">
                <form-grid :rows="documentTabLayout.detail_rows" :root="state" @open-calendar="openCalendar" />
              </disclosure>
              <div class="field" style="margin-top: var(--space-sm);" v-if="documentTabLayout.notes_field">
                <label class="field__label">{{ documentTabLayout.notes_field.label }}</label>
                <textarea class="field__control" style="max-height:76px;" :placeholder="documentTabLayout.notes_field.placeholder"
                  v-model="state.notes"></textarea>
              </div>
            </div>
          </template>

          <div v-else class="empty-state">
            <div class="empty-state__title">Chưa chọn biểu mẫu</div>
            <div class="empty-state__hint">Chọn một loại tài liệu ở trên để bắt đầu điền thông tin</div>
          </div>

          <div class="action-bar">
            <button class="btn" type="button" :disabled="!documentReady" @click="preview">Xem trước</button>
            <button class="btn btn--primary" type="button" :disabled="!documentReady" @click="openReview">Tạo tài liệu</button>
          </div>
        </div>
      </div>

      <calendar-popover v-if="calendar" :anchor-rect="calendar.anchorRect"
        :value="CCCD.getByPath(state, calendar.field.path)"
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
  app.component("FormGrid", CCCD.components.FormGrid);
  app.component("Disclosure", CCCD.components.Disclosure);
  app.component("Tabs", CCCD.components.Tabs);
  app.component("UploadCard", CCCD.components.UploadCard);
  app.component("CalendarPopover", CCCD.components.CalendarPopover);
  app.component("ToastStack", CCCD.components.ToastStack);
  app.mount("#app");
})();
