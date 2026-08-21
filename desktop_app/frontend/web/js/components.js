window.CCCD = window.CCCD || {};
CCCD.components = {};

// Civil dates stay as dd/mm/yyyy strings throughout the UI.  Keeping this
// parser independent from JavaScript's Date string parser avoids both its
// locale ambiguity and the silent rollover of values such as 31/02/2026.
const DATE_INPUT_ERROR = "Ngày không hợp lệ. Hãy nhập đúng DD/MM/YYYY.";

function daysInMonth(year, month) {
  if (month === 2) {
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    return leap ? 29 : 28;
  }
  return [4, 6, 9, 11].includes(month) ? 30 : 31;
}

function parseDMY(value) {
  const match = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(String(value || "").trim());
  if (!match) return null;
  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = Number(match[3]);
  if (year < 1 || month < 1 || month > 12) return null;
  if (day < 1 || day > daysInMonth(year, month)) return null;
  return { y: year, m: month, d: day };
}

function fmtDMY({ y, m, d }) {
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}/${String(y).padStart(4, "0")}`;
}

function dateInputError(value) {
  return String(value || "").trim() && !parseDMY(value) ? DATE_INPUT_ERROR : "";
}

function looksLikeCompletedDate(value) {
  const text = String(value || "").trim();
  return text.length >= 10 || /^\d{1,3}\/\d{1,3}\/\d{4,}$/.test(text);
}

// Exposed for the subscriber table and lightweight regression tests.  All
// date fields, including rows added dynamically, use exactly the same rules.
CCCD.dateInput = {
  parse: parseDMY,
  format: fmtDMY,
  error: dateInputError,
  looksComplete: looksLikeCompletedDate,
};

const DUPLICATE_SUBSCRIBER_ERROR_PREFIX = "Số thuê bao bị trùng ở các dòng";

function duplicateSubscriberGroups(rows) {
  const grouped = new Map();
  (rows || []).forEach((row, index) => {
    const canonical = String(row?.subscriber_number || "").replace(/\D/g, "");
    if (canonical.length < 9 || canonical.length > 12) return;
    if (!grouped.has(canonical)) grouped.set(canonical, []);
    grouped.get(canonical).push(index);
  });
  return [...grouped.values()].filter((indexes) => indexes.length > 1);
}

CCCD.subscriberInput = { duplicateGroups: duplicateSubscriberGroups };

// ---------------------------------------------------------------------------
// CompositionSafeControl -- keep the browser's live editing buffer outside
// Vue's controlled `value` patching. QtWebEngine/Fcitx does not consistently
// expose isComposing/compositionstart for every Vietnamese IME sequence; a
// reactive :value binding can therefore put an older value back into the DOM
// between Telex/VNI keystrokes. This component writes external values only
// while the control is not being edited, but still publishes every real DOM
// input immediately to ReportData.
// ---------------------------------------------------------------------------
CCCD.components.CompositionSafeControl = {
  inheritAttrs: false,
  props: {
    modelValue: { type: [String, Number], default: "" },
    multiline: Boolean,
    numeric: Boolean,
    maxLength: { type: [String, Number], default: 0 },
  },
  emits: ["update:modelValue", "blur"],
  data() {
    return { editing: false, composing: false };
  },
  watch: {
    modelValue(value) {
      this.syncExternalValue(value);
    },
  },
  mounted() {
    this.syncExternalValue(this.modelValue, true);
  },
  methods: {
    normalized(value) {
      let text = String(value ?? "");
      if (this.numeric) text = text.replace(/\D/g, "");
      const limit = Number(this.maxLength || 0);
      return limit ? text.slice(0, limit) : text;
    },
    syncExternalValue(value, force = false) {
      const control = this.$refs.control;
      if (!control || (!force && (this.editing || this.composing))) return;
      const text = this.normalized(value);
      if (control.value !== text) control.value = text;
    },
    publish(event) {
      const value = this.normalized(event.target.value);
      if (event.target.value !== value) event.target.value = value;
      this.$emit("update:modelValue", value);
    },
    onCompositionEnd(event) {
      this.composing = false;
      this.publish(event);
    },
    onBlur(event) {
      this.composing = false;
      this.editing = false;
      this.publish(event);
      this.$emit("blur", event.target.value);
    },
  },
  template: `
    <textarea v-if="multiline" ref="control" v-bind="$attrs"
      @focus="editing = true" @blur="onBlur" @input="publish"
      @compositionstart="composing = true" @compositionend="onCompositionEnd"></textarea>
    <input v-else ref="control" v-bind="$attrs" type="text"
      :inputmode="numeric ? 'numeric' : ($attrs.inputmode || 'text')"
      :maxlength="maxLength || null"
      @focus="editing = true" @blur="onBlur" @input="publish"
      @compositionstart="composing = true" @compositionend="onCompositionEnd">
  `,
};

// ---------------------------------------------------------------------------
// FieldInput -- UI-element/FormField.md anatomy: label, required asterisk,
// placeholder (a format hint only), helper text, error message (replaces
// helper, never stacks under it -- same rule as the old FieldInput.set_error()).
// ---------------------------------------------------------------------------
CCCD.components.FieldInput = {
  props: { field: Object, root: Object },
  emits: ["open-calendar", "entity-type-changed"],
  computed: {
    value() {
      return CCCD.getByPath(this.root, this.field.path) ?? "";
    },
    error() {
      return CCCD.state.ui.errors[this.field.path] || "";
    },
    placeholder() {
      if (this.field.placeholder) return this.field.placeholder;
      if (this.field.kind === "date") return "dd/mm/yyyy";
      return `Nhập ${this.field.label.toLowerCase()}`;
    },
  },
  methods: {
    setValue(v) {
      CCCD.setByPath(this.root, this.field.path, v);
      if (this.field.kind === "date") {
        const message = CCCD.dateInput.looksComplete(v) ? CCCD.dateInput.error(v) : "";
        if (message) CCCD.state.ui.errors[this.field.path] = message;
        else if (this.error) delete CCCD.state.ui.errors[this.field.path];
      } else if (v && this.error) {
        delete CCCD.state.ui.errors[this.field.path];
      }
      // The entity_type select (Cá nhân/Tổ chức) doesn't just change a
      // value -- it changes which OTHER fields are even visible/required,
      // which only Python (resolve_person_form) knows how to recompute. A
      // plain value write here would leave the old field layout stale.
      if (this.field.name === "entity_type") {
        this.$emit("entity-type-changed", { path: this.field.path, value: v });
      }
    },
    validateDate(rawValue) {
      const value = String(rawValue ?? this.value).trim();
      if (!value) {
        if (CCCD.state.ui.errors[this.field.path] === DATE_INPUT_ERROR) {
          delete CCCD.state.ui.errors[this.field.path];
        }
        return;
      }
      const message = CCCD.dateInput.error(value);
      if (message) {
        CCCD.state.ui.errors[this.field.path] = message;
        return;
      }
      if (value) CCCD.setByPath(this.root, this.field.path, CCCD.dateInput.format(CCCD.dateInput.parse(value)));
      delete CCCD.state.ui.errors[this.field.path];
    },
  },
  template: `
    <div class="field">
      <label class="field__label" :for="field.path">
        {{ field.label }}<span v-if="field.required" class="field__required"> *</span>
      </label>
      <select v-if="field.kind === 'select'" class="field__control" :id="field.path"
        :value="value" @change="setValue($event.target.value)">
        <option v-for="opt in field.options" :key="opt" :value="opt">{{ opt }}</option>
      </select>
      <composition-safe-control v-else-if="field.kind === 'textarea'" multiline
        class="field__control" :id="field.path" :placeholder="placeholder"
        :model-value="value" @update:model-value="setValue" />
      <composition-safe-control v-else-if="field.kind === 'number'" numeric
        class="field__control" :id="field.path" :placeholder="placeholder" :data-invalid="!!error"
        :max-length="field.max_length || 0" :model-value="value" @update:model-value="setValue" />
      <div v-else-if="field.kind === 'date'" class="field__date">
        <composition-safe-control class="field__control" :id="field.path"
          :placeholder="placeholder" :data-invalid="!!error"
          :model-value="value" @update:model-value="setValue" @blur="validateDate" />
        <button type="button" class="field__date-trigger" aria-label="Chọn từ lịch"
          @click="$emit('open-calendar', { field, root, $event })">📅</button>
      </div>
      <composition-safe-control v-else class="field__control" :id="field.path"
        :placeholder="placeholder" :data-invalid="!!error"
        :model-value="value" @update:model-value="setValue" />
      <div v-if="field.helper && !error" class="field__helper">{{ field.helper }}</div>
      <div v-if="error" class="field__error">{{ error }}</div>
    </div>
  `,
};

// ---------------------------------------------------------------------------
// CheckboxGroup -- the one compound field kind (Aftersale's "Giấy tờ kèm
// theo"). Each item's path is a bare ReportData attribute name
// (has_id_attachment/has_original_sim), resolved from root same as any field.
// ---------------------------------------------------------------------------
CCCD.components.CheckboxGroup = {
  props: { field: Object, root: Object },
  template: `
    <div class="field">
      <div class="field__label">{{ field.label }}</div>
      <div style="display:flex; gap: var(--space-base);">
        <label v-for="item in field.items" :key="item.path" class="checkbox-row">
          <input type="checkbox" :checked="root[item.path]" @change="root[item.path] = $event.target.checked">
          {{ item.label }}
        </label>
      </div>
    </div>
  `,
};

// ---------------------------------------------------------------------------
// FormGrid -- renders resolved rows (span + field descriptor) from
// web_bridge/schema.py. The wrapping/packing decision was already made in
// Python (resolve_rows()); this is just a CSS grid with span classes.
// ---------------------------------------------------------------------------
CCCD.components.FormGrid = {
  props: { rows: Array, root: Object },
  emits: ["open-calendar", "entity-type-changed"],
  template: `
    <div class="form-grid">
      <template v-for="(row, ri) in rows" :key="ri">
        <div v-for="(cell, ci) in row" :key="cell.field.path"
          :class="['form-grid__cell--span-' + cell.span, ci === 0 ? 'form-grid__cell--row-start' : '']">
          <checkbox-group v-if="cell.field.kind === 'checkbox_group'" :field="cell.field" :root="root" />
          <field-input v-else :field="cell.field" :root="root" @open-calendar="$emit('open-calendar', $event)"
            @entity-type-changed="$emit('entity-type-changed', $event)" />
        </div>
      </template>
    </div>
  `,
};

// ---------------------------------------------------------------------------
// SectionedForm -- provider information is easier to scan as two semantic
// blocks while still reusing the same schema-driven FormGrid/FieldInput.
// ---------------------------------------------------------------------------
CCCD.components.SectionedForm = {
  props: { sections: Array, root: Object },
  emits: ["open-calendar"],
  template: `
    <div class="sectioned-form">
      <section v-for="section in sections" :key="section.title" class="sectioned-form__section">
        <div class="sectioned-form__title">{{ section.title }}</div>
        <form-grid :rows="section.rows" :root="root" @open-calendar="$emit('open-calendar', $event)" />
      </section>
    </div>
  `,
};

// ---------------------------------------------------------------------------
// SubscriberList -- the mẫu (service-template) workflow's own canonical,
// subscriber list (root.subscribers). Python supplies the exact columns and
// row limit for the selected service; this component never knows document
// types or branches on service identifiers.
// ---------------------------------------------------------------------------
CCCD.components.SubscriberList = {
  props: { layout: Object, root: Object },
  emits: ["open-calendar"],
  watch: {
    rows: {
      deep: true,
      handler() {
        this.validateSubscriberDuplicates();
      },
    },
  },
  mounted() {
    this.validateSubscriberDuplicates();
  },
  computed: {
    rows() {
      if (!Array.isArray(this.root.subscribers) || !this.root.subscribers.length) {
        this.root.subscribers = [this.blankRow()];
      }
      return this.root.subscribers;
    },
    columns() {
      return this.layout?.columns || [];
    },
    canAdd() {
      const maximum = Number(this.layout?.max_rows || 0);
      return !maximum || this.rows.length < maximum;
    },
  },
  methods: {
    blankRow() {
      const today = new Date();
      const pad = (n) => String(n).padStart(2, "0");
      return {
        subscriber_number: "", monthly_fee: "", commitment_months: "12",
        activation_date: `${pad(today.getDate())}/${pad(today.getMonth() + 1)}/${today.getFullYear()}`,
        sim_serial: "", commitment_note: "",
      };
    },
    descriptor(column, index) {
      return { ...column, path: `subscribers.${index}.${column.name}` };
    },
    value(column, index) {
      return String(this.rows[index]?.[column.name] ?? "");
    },
    error(column, index) {
      return CCCD.state.ui.errors[`subscribers.${index}.${column.name}`] || "";
    },
    setValue(column, index, value) {
      this.rows[index][column.name] = value;
      const path = `subscribers.${index}.${column.name}`;
      if (column.kind === "date" && CCCD.dateInput.looksComplete(value)) {
        const message = CCCD.dateInput.error(value);
        if (message) CCCD.state.ui.errors[path] = message;
        else delete CCCD.state.ui.errors[path];
      } else {
        delete CCCD.state.ui.errors[path];
      }
      if (index === 0 && column.name === "subscriber_number") {
        this.root.subscriber_number = value;
        this.root.subscriber_number_1 = value;
      }
      if (column.name === "subscriber_number") this.validateSubscriberDuplicates();
    },
    validateSubscriberDuplicates() {
      for (const [path, message] of Object.entries(CCCD.state.ui.errors)) {
        if (
          /^subscribers\.\d+\.subscriber_number$/.test(path)
          && String(message).startsWith(DUPLICATE_SUBSCRIBER_ERROR_PREFIX)
        ) delete CCCD.state.ui.errors[path];
      }
      for (const indexes of CCCD.subscriberInput.duplicateGroups(this.rows)) {
        const rowNumbers = indexes.map((index) => index + 1).join(", ");
        const message = `${DUPLICATE_SUBSCRIBER_ERROR_PREFIX} ${rowNumbers}`;
        for (const index of indexes) {
          CCCD.state.ui.errors[`subscribers.${index}.subscriber_number`] = message;
        }
      }
    },
    validateDate(column, index, rawValue) {
      const path = `subscribers.${index}.${column.name}`;
      const value = String(rawValue ?? this.value(column, index)).trim();
      if (!value) {
        if (CCCD.state.ui.errors[path] === DATE_INPUT_ERROR) delete CCCD.state.ui.errors[path];
        return;
      }
      const message = CCCD.dateInput.error(value);
      if (message) {
        CCCD.state.ui.errors[path] = message;
        return;
      }
      if (value) this.rows[index][column.name] = CCCD.dateInput.format(CCCD.dateInput.parse(value));
      delete CCCD.state.ui.errors[path];
    },
    addRow() {
      if (this.canAdd) this.rows.push(this.blankRow());
    },
    removeRow(index) {
      if (this.rows.length === 1) this.rows.splice(0, 1, this.blankRow());
      else this.rows.splice(index, 1);
      for (const path of Object.keys(CCCD.state.ui.errors)) {
        if (path.startsWith("subscribers.")) delete CCCD.state.ui.errors[path];
      }
      this.root.subscriber_number = this.rows[0]?.subscriber_number || "";
      this.root.subscriber_number_1 = this.root.subscriber_number;
      this.validateSubscriberDuplicates();
    },
    openDate(column, index, event) {
      this.$emit("open-calendar", { field: this.descriptor(column, index), root: this.root, $event: event });
    },
  },
  template: `
    <div class="subscriber-table">
      <div class="subscriber-table__header">
        <button v-if="canAdd" type="button" class="btn btn--ghost subscriber-table__add" @click="addRow">＋ Thêm số thuê bao khác</button>
      </div>
      <div class="subscriber-table__scroll">
        <table class="subscriber-table__grid">
          <colgroup><col class="subscriber-table__col-index"><col v-for="c in columns" :key="c.name"><col class="subscriber-table__col-actions"></colgroup>
          <thead><tr><th class="subscriber-table__index">STT</th><th v-for="c in columns" :key="c.name">{{ c.label }}</th><th><span class="sr-only">Thao tác</span></th></tr></thead>
          <tbody>
            <tr v-for="(row, rowIndex) in rows" :key="rowIndex">
              <td class="subscriber-table__index"><span>{{ rowIndex + 1 }}</span></td>
              <td v-for="column in columns" :key="column.name">
                <div class="subscriber-table__input-wrap" :data-invalid="!!error(column, rowIndex)">
                  <composition-safe-control class="subscriber-table__input"
                    :numeric="column.kind === 'number'"
                    :inputmode="column.kind === 'number' ? 'numeric' : 'text'"
                    :placeholder="column.kind === 'date' ? 'dd/mm/yyyy' : 'Nhập ' + column.label.toLowerCase()"
                    :model-value="value(column, rowIndex)"
                    @update:model-value="setValue(column, rowIndex, $event)"
                    @blur="column.kind === 'date' && validateDate(column, rowIndex, $event)" />
                  <button v-if="column.kind === 'date'" type="button" class="subscriber-table__date-trigger"
                    aria-label="Chọn từ lịch" @click="openDate(column, rowIndex, $event)">📅</button>
                </div>
                <div v-if="error(column, rowIndex)" class="field__error">{{ error(column, rowIndex) }}</div>
              </td>
              <td class="subscriber-table__actions"><button type="button" class="subscriber-table__remove" @click="removeRow(rowIndex)">Xóa</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  `,
};

// ---------------------------------------------------------------------------
// PersonalInformationForm / OrganizationInformationForm -- fixed reusable
// identity forms. Their row definitions still come from Python's schema,
// while these components own the distinct 3-column personal and 2-column
// organization presentation. Keeping them separate makes future changes to
// either form local instead of adding document/tab-specific CSS exceptions.
// ---------------------------------------------------------------------------
CCCD.components.PersonalInformationForm = {
  props: { rows: Array, root: Object },
  emits: ["open-calendar"],
  template: `
    <div class="information-form information-form--personal">
      <div v-for="(row, ri) in rows" :key="ri" class="information-form__row">
        <div v-for="cell in row" :key="cell.field.path" class="information-form__cell">
          <field-input :field="cell.field" :root="root"
            @open-calendar="$emit('open-calendar', $event)" />
        </div>
      </div>
    </div>
  `,
};

CCCD.components.OrganizationInformationForm = {
  props: { rows: Array, root: Object },
  emits: ["open-calendar"],
  template: `
    <div class="information-form information-form--organization">
      <div v-for="(row, ri) in rows" :key="ri" class="information-form__row">
        <div v-for="cell in row" :key="cell.field.path" class="information-form__cell">
          <field-input :field="cell.field" :root="root"
            @open-calendar="$emit('open-calendar', $event)" />
        </div>
      </div>
    </div>
  `,
};

// ---------------------------------------------------------------------------
// Disclosure -- UI-element/Accordion.md: <details>-equivalent trigger +
// indicator + panel, with a real measured-height reveal transition.
// ---------------------------------------------------------------------------
CCCD.components.Disclosure = {
  props: { modelValue: Boolean, label: String },
  emits: ["update:modelValue"],
  data() {
    return { panelHeight: 0 };
  },
  watch: {
    modelValue() {
      this.$nextTick(this.measure);
    },
  },
  mounted() {
    this.measure();
    this._ro = new ResizeObserver(() => this.modelValue && this.measure());
    this._ro.observe(this.$refs.inner);
  },
  beforeUnmount() {
    this._ro && this._ro.disconnect();
  },
  methods: {
    measure() {
      this.panelHeight = this.$refs.inner ? this.$refs.inner.scrollHeight : 0;
    },
    toggle() {
      this.$emit("update:modelValue", !this.modelValue);
    },
  },
  template: `
    <div class="disclosure" :data-open="modelValue">
      <button type="button" class="disclosure__trigger" @click="toggle">
        <span class="disclosure__indicator"></span>{{ label }}
      </button>
      <div class="disclosure__panel" :style="{ '--panel-height': modelValue ? panelHeight + 'px' : '0px' }">
        <div class="disclosure__panel-inner" ref="inner"><slot /></div>
      </div>
    </div>
  `,
};

// ---------------------------------------------------------------------------
// Tabs -- UI-element/Tabs.md: role=tablist/tab/tabpanel, arrow-key nav.
// ---------------------------------------------------------------------------
CCCD.components.Tabs = {
  props: { tabs: Array, modelValue: String }, // tabs: [{id,label,visible}]
  emits: ["update:modelValue"],
  methods: {
    onKeydown(e) {
      const visible = this.tabs.filter((t) => t.visible !== false);
      const idx = visible.findIndex((t) => t.id === this.modelValue);
      if (e.key === "ArrowRight") this.$emit("update:modelValue", visible[(idx + 1) % visible.length].id);
      if (e.key === "ArrowLeft") this.$emit("update:modelValue", visible[(idx - 1 + visible.length) % visible.length].id);
    },
  },
  template: `
    <div class="tablist" role="tablist" @keydown="onKeydown">
      <button v-for="t in tabs.filter(t => t.visible !== false)" :key="t.id" type="button" role="tab"
        class="tab" :aria-selected="modelValue === t.id" :tabindex="modelValue === t.id ? 0 : -1"
        @click="$emit('update:modelValue', t.id)">{{ t.label }}</button>
    </div>
  `,
};

// ---------------------------------------------------------------------------
// CalendarPopover -- UI-element/DatePicker.md anatomy: prev/next month
// buttons, today indicator (outlined, not filled -- independent of
// selection), selected-day fill. dd/mm/yyyy civil-date strings throughout,
// never Date-parsed-as-UTC (the classic off-by-one bug this doc warns about).
// ---------------------------------------------------------------------------
const WEEKDAYS = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
function todayYMD() {
  const t = new Date();
  return { y: t.getFullYear(), m: t.getMonth() + 1, d: t.getDate() };
}

CCCD.components.CalendarPopover = {
  props: { anchorRect: Object, value: String },
  emits: ["pick", "close"],
  data() {
    const cur = parseDMY(this.value) || todayYMD();
    return { viewYear: cur.y, viewMonth: cur.m };
  },
  computed: {
    style() {
      if (!this.anchorRect) return {};
      const width = 260;
      const estimatedHeight = 310;
      let left = this.anchorRect.left;
      const maxLeft = window.innerWidth - width - 8;
      if (left > maxLeft) left = Math.max(8, maxLeft);
      let top = this.anchorRect.bottom + 4;
      if (top + estimatedHeight > window.innerHeight - 8) {
        top = Math.max(8, this.anchorRect.top - estimatedHeight - 4);
      }
      return { left: left + "px", top: top + "px" };
    },
    weeks() {
      const first = new Date(this.viewYear, this.viewMonth - 1, 1);
      const startOffset = first.getDay(); // 0 = Sunday, matches WEEKDAYS order
      const daysInMonth = new Date(this.viewYear, this.viewMonth, 0).getDate();
      const daysInPrevMonth = new Date(this.viewYear, this.viewMonth - 1, 0).getDate();
      const selected = parseDMY(this.value);
      const today = todayYMD();
      const cells = [];
      for (let i = 0; i < startOffset; i++) {
        cells.push({ d: daysInPrevMonth - startOffset + 1 + i, muted: true, y: this.viewMonth === 1 ? this.viewYear - 1 : this.viewYear, m: this.viewMonth === 1 ? 12 : this.viewMonth - 1 });
      }
      for (let d = 1; d <= daysInMonth; d++) {
        cells.push({ d, muted: false, y: this.viewYear, m: this.viewMonth });
      }
      while (cells.length % 7 !== 0) {
        const last = cells[cells.length - 1];
        const next = last.d + 1;
        cells.push({ d: next, muted: true, y: this.viewMonth === 12 ? this.viewYear + 1 : this.viewYear, m: this.viewMonth === 12 ? 1 : this.viewMonth + 1 });
      }
      return cells.map((c) => ({
        ...c,
        isToday: c.y === today.y && c.m === today.m && c.d === today.d,
        isSelected: !!selected && c.y === selected.y && c.m === selected.m && c.d === selected.d,
      }));
    },
    monthLabel() {
      return `Tháng ${this.viewMonth}`;
    },
    yearOptions() {
      // Cover birth dates as well as long-lived SIM/identity expiry dates.
      // Always include the displayed year so opening the picker can never
      // show a month grid whose year is missing from the year selector.
      const currentYear = todayYMD().y;
      const newest = Math.max(currentYear + 100, this.viewYear);
      const oldest = Math.min(currentYear - 120, this.viewYear);
      const years = [];
      for (let y = newest; y >= oldest; y--) years.push(y);
      return years;
    },
  },
  mounted() {
    this._onDocClick = (e) => {
      if (!this.$el.contains(e.target)) this.$emit("close");
    };
    setTimeout(() => document.addEventListener("mousedown", this._onDocClick), 0);
  },
  beforeUnmount() {
    document.removeEventListener("mousedown", this._onDocClick);
  },
  methods: {
    prevMonth() {
      if (this.viewMonth === 1) { this.viewMonth = 12; this.viewYear--; } else this.viewMonth--;
    },
    nextMonth() {
      if (this.viewMonth === 12) { this.viewMonth = 1; this.viewYear++; } else this.viewMonth++;
    },
    setYear(y) {
      this.viewYear = Number(y);
    },
    pick(cell) {
      this.$emit("pick", fmtDMY({ y: cell.y, m: cell.m, d: cell.d }));
    },
  },
  template: `
    <div class="calendar-popover" :style="style">
      <div class="calendar__nav">
        <button type="button" class="calendar__nav-btn" @click="prevMonth">‹</button>
        <div class="calendar__nav-center">
          <span>{{ monthLabel }}</span>
          <select class="calendar__year-select" :value="viewYear" @change="setYear($event.target.value)">
            <option v-for="y in yearOptions" :key="y" :value="y">{{ y }}</option>
          </select>
        </div>
        <button type="button" class="calendar__nav-btn" @click="nextMonth">›</button>
      </div>
      <div class="calendar__grid">
        <div v-for="w in ['CN','T2','T3','T4','T5','T6','T7']" :key="w" class="calendar__weekday">{{ w }}</div>
        <button v-for="(c, i) in weeks" :key="i" type="button" class="calendar__day"
          :data-muted="c.muted" :data-today="c.isToday" :data-selected="c.isSelected"
          @click="pick(c)">{{ c.d }}</button>
      </div>
    </div>
  `,
};

// ---------------------------------------------------------------------------
// Toasts
// ---------------------------------------------------------------------------
CCCD.components.ToastStack = {
  template: `
    <div class="toast-stack">
      <div v-for="t in CCCD.state.ui.toasts" :key="t.id" class="toast" :data-tone="t.tone">{{ t.message }}</div>
    </div>
  `,
};
