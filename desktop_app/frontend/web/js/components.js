window.CCCD = window.CCCD || {};
CCCD.components = {};

// ---------------------------------------------------------------------------
// FieldInput -- UI-element/FormField.md anatomy: label, required asterisk,
// placeholder (a format hint only), helper text, error message (replaces
// helper, never stacks under it -- same rule as the old FieldInput.set_error()).
// ---------------------------------------------------------------------------
CCCD.components.FieldInput = {
  props: { field: Object, root: Object },
  emits: ["open-calendar"],
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
      if (v && this.error) delete CCCD.state.ui.errors[this.field.path];
    },
    onNumberInput(e) {
      const cleaned = e.target.value.replace(/[^0-9 ]/g, "");
      e.target.value = cleaned;
      this.setValue(cleaned);
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
      <textarea v-else-if="field.kind === 'textarea'" class="field__control" :id="field.path"
        :placeholder="placeholder" :value="value" @input="setValue($event.target.value)"></textarea>
      <input v-else-if="field.kind === 'number'" class="field__control" type="text" inputmode="numeric"
        :id="field.path" :placeholder="placeholder" :value="value" :data-invalid="!!error"
        @input="onNumberInput">
      <input v-else-if="field.kind === 'date'" class="field__control" type="text" :id="field.path"
        :placeholder="placeholder" :value="value" :data-invalid="!!error" readonly
        @click="$emit('open-calendar', { field, $event })">
      <input v-else class="field__control" type="text" :id="field.path"
        :placeholder="placeholder" :value="value" :data-invalid="!!error"
        @input="setValue($event.target.value)">
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
  emits: ["open-calendar"],
  template: `
    <div class="form-grid">
      <template v-for="(row, ri) in rows" :key="ri">
        <div v-for="cell in row" :key="cell.field.path" :class="'form-grid__cell--span-' + cell.span">
          <checkbox-group v-if="cell.field.kind === 'checkbox_group'" :field="cell.field" :root="root" />
          <field-input v-else :field="cell.field" :root="root" @open-calendar="$emit('open-calendar', $event)" />
        </div>
      </template>
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
function parseDMY(s) {
  const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec((s || "").trim());
  if (!m) return null;
  const [, d, mo, y] = m.map(Number);
  return { y, m: mo, d };
}
function fmtDMY({ y, m, d }) {
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}/${y}`;
}
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
      let left = this.anchorRect.left;
      const maxLeft = window.innerWidth - width - 8;
      if (left > maxLeft) left = Math.max(8, maxLeft);
      return { left: left + "px", top: this.anchorRect.bottom + 4 + "px" };
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
    label() {
      return `Tháng ${this.viewMonth}, ${this.viewYear}`;
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
    pick(cell) {
      this.$emit("pick", fmtDMY({ y: cell.y, m: cell.m, d: cell.d }));
    },
  },
  template: `
    <div class="calendar-popover" :style="style">
      <div class="calendar__nav">
        <button type="button" class="calendar__nav-btn" @click="prevMonth">‹</button>
        <span>{{ label }}</span>
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
// UploadCard -- UI-element/drap&drop.md + progresssRing...md: a single
// intake dropzone (click -> native file dialog; HTML5 drop -> base64 bytes,
// since Chromium never exposes a real path for a dropped File), two
// front/back preview cards, and a determinate progress bar during OCR.
// ---------------------------------------------------------------------------
CCCD.components.UploadCard = {
  props: { target: String }, // "customer" | "new_owner"
  data() {
    return { dragActive: false };
  },
  computed: {
    upload() {
      return CCCD.state.ui.upload[this.target];
    },
  },
  methods: {
    click() {
      CCCD.bridge.selectAndScanImages(this.target);
    },
    onDragOver(e) {
      e.preventDefault();
      this.dragActive = true;
    },
    onDragLeave() {
      this.dragActive = false;
    },
    async onDrop(e) {
      e.preventDefault();
      this.dragActive = false;
      const files = [...e.dataTransfer.files].filter((f) => /\.(jpe?g|png|bmp|webp)$/i.test(f.name));
      for (const file of files) {
        const base64 = await this.readAsBase64(file);
        CCCD.bridge.submitDroppedImage(this.target, file.name, base64);
      }
    },
    readAsBase64(file) {
      return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(",", 2)[1]);
        reader.readAsDataURL(file);
      });
    },
  },
  template: `
    <div class="card card--upload">
      <div class="dropzone" :data-drag-active="dragActive" :data-invalid="upload.invalid"
        @click="click" @dragover="onDragOver" @dragleave="onDragLeave" @drop="onDrop">
        <div class="dropzone__title">Gửi ảnh vào đây</div>
      </div>
      <div v-if="upload.progress" class="progress">
        <div class="progress__value" :style="{ width: (100 * upload.progress.done / upload.progress.total) + '%' }"></div>
      </div>
      <div v-if="upload.front || upload.back" class="eyebrow">ẢNH ĐÃ NHẬN DIỆN</div>
      <div class="preview-row" v-if="upload.front || upload.back">
        <div class="preview-card" v-for="side in ['front','back']" :key="side" v-show="upload[side]">
          <img v-if="upload[side]" class="preview-card__media" :src="upload[side].thumbnail">
          <div class="preview-card__body" v-if="upload[side]">
            <span class="badge" data-detected="true">{{ side === 'front' ? 'MẶT TRƯỚC' : 'MẶT SAU' }}</span>
            <span class="preview-card__filename">{{ upload[side].filename }}</span>
          </div>
        </div>
      </div>
      <div v-if="upload.note" class="upload-note" :data-invalid="upload.invalid">{{ upload.note }}</div>
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
