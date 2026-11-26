/* DBT T&E Claim Form - browser logic (vanilla JS, no build step).
 *
 * Flow: 1) fill in  ->  2) Generate claim (PDF preview, no download)
 *       ->  3) attach proofs, drag to reorder  ->  Merge & download
 *
 * Money and distance are handled as integers of 1/100 so the live totals use
 * exactly the same arithmetic (ROUND_HALF_UP) as the server's Decimal code.
 */
(() => {
  'use strict';

  const CFG = window.APP_CONFIG;
  const DRAFT_KEY = 'dbt-claim-draft-v1';
  const form = document.getElementById('claim-form');
  const SECTION_DEFS = CFG.sections;
  const MONTH_NAMES = CFG.months.map((m) => m.charAt(0) + m.slice(1).toLowerCase());

  // ------------------------------------------------------------------ utils
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const field = (name) => form.elements.namedItem(name);

  function h(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (value === null || value === undefined || value === false) continue;
      if (key === 'class') node.className = value;
      else if (key === 'text') node.textContent = value;
      else if (key === 'html') node.innerHTML = value; // static icon markup only
      else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? '' : value);
    }
    for (const child of children) if (child !== null && child !== undefined) node.append(child);
    return node;
  }

  let uidSeq = 0;
  const uid = (prefix) => `${prefix}-${++uidSeq}`;

  const ICONS = {
    copy: '<svg viewBox="0 0 20 20" aria-hidden="true"><rect x="7" y="7" width="9.5" height="9.5" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M13 7V4.8a1.3 1.3 0 00-1.3-1.3H4.8a1.3 1.3 0 00-1.3 1.3v6.9A1.3 1.3 0 004.8 13H7" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>',
    trash: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 6h12M8 6V4.5h4V6M6 6l.7 10h6.6L14 6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    up: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 12.5l5-5 5 5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    down: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 7.5l5 5 5-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    grip: '<svg viewBox="0 0 16 16" aria-hidden="true"><g fill="currentColor"><circle cx="5.5" cy="3.5" r="1.3"/><circle cx="10.5" cy="3.5" r="1.3"/><circle cx="5.5" cy="8" r="1.3"/><circle cx="10.5" cy="8" r="1.3"/><circle cx="5.5" cy="12.5" r="1.3"/><circle cx="10.5" cy="12.5" r="1.3"/></g></svg>',
  };

  const iconButton = (icon, label, action, extra = '') =>
    h('button', { type: 'button', class: `icon-btn ${extra}`, 'data-action': action, title: label, 'aria-label': label, html: ICONS[icon] });

  // ------------------------------------------------- exact number handling
  const NUM_RE = /^\d{1,9}(\.\d{1,2})?$/;

  function cleanNumber(value) {
    let s = String(value ?? '').replace(/[,\s]/g, '');
    if (/^rm/i.test(s)) s = s.slice(2);
    return s;
  }

  /** "12.5" -> 1250 ; invalid -> null */
  function toHundredths(value) {
    const s = cleanNumber(value);
    if (!NUM_RE.test(s)) return null;
    const [whole, frac = ''] = s.split('.');
    return Number(whole) * 100 + Number((frac + '00').slice(0, 2));
  }

  const RATE = {
    motorcycle: toHundredths(CFG.rates.motorcycle),
    car: toHundredths(CFG.rates.car),
    carBeyond: toHundredths(CFG.rates.carBeyondTier),
    tierKm: toHundredths(CFG.rates.carTierKm),
  };

  /** Mileage in sen for a distance in 1/100 km (mirrors models.mileage_claim). */
  function mileageSen(kmH, vehicle) {
    if (kmH <= 0) return 0;
    let raw; // unit: 1/100 sen
    if (vehicle === 'car') {
      const first = Math.min(kmH, RATE.tierKm);
      raw = first * RATE.car + (kmH - first) * RATE.carBeyond;
    } else {
      raw = kmH * RATE.motorcycle;
    }
    return Math.floor((raw + 50) / 100); // ROUND_HALF_UP
  }

  const moneyFmt = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtMoney = (sen) => moneyFmt.format(sen / 100);
  const fmtKm = (h100) => {
    const v = h100 / 100;
    if (Number.isInteger(v)) return String(v);
    return h100 % 10 === 0 ? v.toFixed(1) : v.toFixed(2);
  };
  const fmtSize = (bytes) => (bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1048576).toFixed(1)} MB`);
  const pad2 = (n) => String(n).padStart(2, '0');
  const timeNow = () => { const d = new Date(); return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`; };

  /** Next Monday-Friday after an ISO date (used when duplicating a trip). */
  function nextWorkingDay(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
    if (!m) return '';
    const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
    do d.setUTCDate(d.getUTCDate() + 1); while (d.getUTCDay() === 0 || d.getUTCDay() === 6);
    return `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}`;
  }

  // ----------------------------------------------------------------- toasts
  function toast(message, type = 'success', { action = null, timeout } = {}) {
    const node = h('div', { class: `toast ${type}`, role: type === 'error' ? 'alert' : 'status' }, h('span', { text: message }));
    if (action) {
      node.append(h('button', { type: 'button', class: 'toast-action', text: action.label, onclick: () => { action.run(); node.remove(); } }));
    }
    node.append(h('button', { type: 'button', 'aria-label': 'Dismiss', text: '×', onclick: () => node.remove() }));
    $('#toasts').append(node);
    setTimeout(() => node.remove(), timeout ?? (type === 'error' ? 8000 : action ? 6500 : 4000));
  }

  // ------------------------------------------------------ line-item sections
  const sections = {};
  for (const def of SECTION_DEFS) {
    const root = $(`section[data-section="${def.key}"]`);
    sections[def.key] = {
      def,
      root,
      rowsEl: $('.rows', root),
      headEl: $('.grid-head', root),
      emptyEl: $('.empty', root),
      capacityEl: $('.capacity', root),
      totalEl: $('.section-total', root),
      addBtn: $('[data-action="add"]', root),
      sortBtn: $('[data-action="sort"]', root),
    };
  }

  const rowEls = (key) => Array.from(sections[key].rowsEl.children);
  const fieldDef = (key, fieldKey) => sections[key].def.fields.find((f) => f.key === fieldKey);

  function rowValues(row) {
    const out = {};
    for (const input of $$('input[data-key]', row)) out[input.dataset.key] = input.value.trim();
    return out;
  }

  const isBlank = (def, values) => def.blankKeys.every((k) => !String(values[k] ?? '').trim());

  function buildRow(def, values = {}) {
    const row = h('div', { class: 'row' });
    row.append(h('div', { class: 'cell cell-index', 'aria-hidden': 'true' }));
    for (const f of def.fields) {
      const id = uid(def.key);
      const input = h('input', { id, class: 'input', 'data-key': f.key, placeholder: f.placeholder || null, autocomplete: 'off' });
      if (f.type === 'date') {
        input.type = 'date';
        input.min = '2000-01-01';
        input.max = '2100-12-31';
      } else if (f.type === 'time') {
        input.type = 'time';
      } else if (f.type === 'money' || f.type === 'distance') {
        input.type = 'text';
        input.inputMode = 'decimal';
        input.maxLength = 14;
        input.classList.add('num');
      } else {
        input.type = 'text';
        if (f.maxlength) input.maxLength = f.maxlength;
        if (f.list) input.setAttribute('list', f.list);
      }
      input.value = String(values[f.key] ?? '');
      row.append(h('label', { class: `cell cell-${f.key}${f.type === 'text' ? ' wide' : ''}`, for: id },
        h('span', { class: 'cell-label', text: f.label }), input));
    }
    row.append(h('div', { class: 'cell cell-actions' },
      iconButton('copy', 'Duplicate line', 'duplicate'),
      iconButton('trash', 'Remove line', 'remove', 'danger')));
    row.append(h('div', { class: 'row-msg', 'aria-live': 'polite' }));
    return row;
  }

  function addRow(key, { values = {}, after = null, focus = false } = {}) {
    const s = sections[key];
    if (rowEls(key).length >= s.def.capacity) {
      toast(`The printed form has room for ${s.def.capacity} lines in “${s.def.title}”.`, 'warn');
      return null;
    }
    const v = { ...values };
    if (key === 'travel' && !('start' in v) && !('finish' in v)) {
      const rows = rowEls(key);
      const prev = rows.length ? rowValues(after || rows[rows.length - 1]) : null;
      v.start = prev?.start || '09:00';
      v.finish = prev?.finish || '18:00';
    }
    const row = buildRow(s.def, v);
    if (after) after.after(row);
    else s.rowsEl.append(row);
    onChange();
    if (focus) $('input', row)?.focus();
    return row;
  }

  function removeRow(key, row) {
    const s = sections[key];
    const values = rowValues(row);
    const index = rowEls(key).indexOf(row);
    const neighbour = row.nextElementSibling || row.previousElementSibling;
    row.remove();
    onChange();
    (neighbour ? $('input', neighbour) : s.addBtn).focus();
    if (!isBlank(s.def, values)) {
      toast(`Line ${index + 1} removed from ${s.def.title}.`, 'info', {
        action: {
          label: 'Undo',
          run: () => {
            if (rowEls(key).length >= s.def.capacity) return;
            const restored = buildRow(s.def, values);
            const ref = rowEls(key)[index];
            if (ref) ref.before(restored);
            else s.rowsEl.append(restored);
            onChange();
          },
        },
      });
    }
  }

  function duplicateRow(key, row) {
    const values = rowValues(row);
    if (values.date) values.date = nextWorkingDay(values.date);
    const copy = addRow(key, { values, after: row });
    if (copy) $('input', copy).focus();
  }

  function sortRows(key) {
    const s = sections[key];
    rowEls(key)
      .map((row, i) => ({ row, i, date: rowValues(row).date || '9999-12-31' }))
      .sort((a, b) => a.date.localeCompare(b.date) || a.i - b.i)
      .forEach(({ row }) => s.rowsEl.append(row));
    onChange();
  }

  for (const [key, s] of Object.entries(sections)) {
    s.addBtn.addEventListener('click', () => addRow(key, { focus: true }));
    s.sortBtn.addEventListener('click', () => sortRows(key));
    s.rowsEl.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-action]');
      if (!btn) return;
      const row = btn.closest('.row');
      if (btn.dataset.action === 'remove') removeRow(key, row);
      else if (btn.dataset.action === 'duplicate') duplicateRow(key, row);
    });
    // Enter moves down the same column like a spreadsheet; on the last line it adds a new one.
    s.rowsEl.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' || e.isComposing || e.target.tagName !== 'INPUT') return;
      e.preventDefault();
      const row = e.target.closest('.row');
      const next = row.nextElementSibling;
      if (next) {
        $(`input[data-key="${e.target.dataset.key}"]`, next)?.focus();
      } else if (!isBlank(s.def, rowValues(row))) {
        const added = addRow(key);
        $(`input[data-key="${e.target.dataset.key}"]`, added || row)?.focus();
      }
    });
  }

  // --------------------------------------------------------- errors/warnings
  function setInvalid(input, message) {
    input.classList.add('invalid');
    input.setAttribute('aria-invalid', 'true');
    input.dataset.error = message;
    input.title = message;
  }

  function clearInvalid(input) {
    input.classList.remove('invalid');
    input.removeAttribute('aria-invalid');
    delete input.dataset.error;
    input.removeAttribute('title');
  }

  function renderRowMsg(row, warnings) {
    const errors = $$('input[data-error]', row).map((i) => i.dataset.error);
    $('.row-msg', row).replaceChildren(
      ...errors.map((t) => h('span', { class: 'err', text: `${t} ` })),
      ...warnings.map((t) => h('span', { class: 'wrn', text: `${t} ` })),
    );
  }

  function clearAllErrors() {
    $$('.invalid', form).forEach(clearInvalid);
    $$('[data-error-for]').forEach((p) => { p.hidden = true; p.textContent = ''; });
    attachments.clearErrors();
  }

  function showErrors(errors) {
    clearAllErrors();
    let first = null;
    const general = [];
    for (const [path, message] of Object.entries(errors)) {
      const [head, index, key] = path.split('.');
      if (sections[head] && key) {
        const input = rowEls(head)[Number(index)]?.querySelector(`input[data-key="${key}"]`);
        if (input) { setInvalid(input, message); first ??= input; continue; }
      }
      if (head === 'attachments' && index !== undefined) {
        attachments.setError(Number(index), message);
        first ??= $('#att-list');
        continue;
      }
      const target = $(`[data-error-for="${head}"]`);
      if (target) {
        target.textContent = message;
        target.hidden = false;
        const input = field(head);
        if (input && input.classList) { input.classList.add('invalid'); first ??= input; } else first ??= target;
        continue;
      }
      general.push(message);
    }
    refresh();
    const count = Object.keys(errors).length - general.length;
    const parts = [...general];
    if (count) parts.push(`Please fix ${count} highlighted ${count === 1 ? 'item' : 'items'}.`);
    toast(parts.join(' '), 'error');
    if (first) {
      first.scrollIntoView({ behavior: 'smooth', block: 'center' });
      if (typeof first.focus === 'function') first.focus({ preventScroll: true });
    }
  }

  // ---------------------------------------------------------- live refresh
  const currentVehicle = () => (field('vehicle_type').value === 'car' ? 'car' : 'motorcycle');
  let lastTotalSen = 0;

  function refresh() {
    const month = Number(field('month').value);
    const year = Number(field('year').value);
    const totals = {};
    const locations = new Set();

    for (const def of SECTION_DEFS) {
      const s = sections[def.key];
      const rows = rowEls(def.key);
      const valueKey = def.key === 'travel' ? 'distance' : 'amount';
      let sum = 0;

      rows.forEach((row, i) => {
        $('.cell-index', row).textContent = String(i + 1);
        const v = rowValues(row);
        const amount = toHundredths(v[valueKey]);
        if (amount) sum += amount;
        if (v.location) locations.add(v.location);

        const warnings = [];
        $$('input.warn', row).forEach((n) => n.classList.remove('warn'));
        if (!isBlank(def, v)) {
          if (v.date && month && year) {
            const [yy, mm] = v.date.split('-').map(Number);
            if (yy !== year || mm !== month) {
              warnings.push(`Date is outside ${MONTH_NAMES[month - 1]} ${year}.`);
              $('input[data-key="date"]', row).classList.add('warn');
            }
          }
          if (def.key === 'travel' && v.start && v.finish && v.finish <= v.start) {
            warnings.push('Finish time is not after start time.');
            $('input[data-key="finish"]', row).classList.add('warn');
          }
        }
        renderRowMsg(row, warnings);
      });

      totals[def.key] = sum;
      const count = rows.length;
      s.capacityEl.textContent = `${count} / ${def.capacity} lines`;
      s.capacityEl.classList.toggle('full', count >= def.capacity);
      s.addBtn.disabled = count >= def.capacity;
      s.sortBtn.hidden = count < 2;
      s.emptyEl.hidden = count > 0;
      s.headEl.hidden = count === 0;
      s.totalEl.textContent = sum ? (def.key === 'travel' ? `${fmtKm(sum)} km` : `RM ${fmtMoney(sum)}`) : '';
    }

    const vehicle = currentVehicle();
    const kmH = totals.travel;
    const travelSen = mileageSen(kmH, vehicle);
    let note = '';
    if (kmH > 0) {
      if (vehicle === 'motorcycle') note = `Motorcycle × RM ${CFG.rates.motorcycle}/km`;
      else if (kmH > RATE.tierKm && RATE.carBeyond !== RATE.car) {
        note = `Car: first ${fmtKm(RATE.tierKm)} km × RM ${CFG.rates.car}, rest × RM ${CFG.rates.carBeyondTier}`;
      } else note = `Car × RM ${CFG.rates.car}/km`;
    }
    $('#sum-km').textContent = `${fmtKm(kmH)} km`;
    $('#sum-rate').textContent = note;
    $('#sum-travel').textContent = travelSen ? `RM ${fmtMoney(travelSen)}` : '—';

    let totalSen = travelSen;
    for (const def of SECTION_DEFS) {
      if (def.key === 'travel') continue;
      totalSen += totals[def.key];
      $(`#sum-${def.key}`).textContent = totals[def.key] ? `RM ${fmtMoney(totals[def.key])}` : '—';
    }
    lastTotalSen = totalSen;
    $('#sum-total').textContent = `RM ${fmtMoney(totalSen)}`;
    $('#mobile-total').textContent = `RM ${fmtMoney(totalSen)}`;

    $('#location-options').replaceChildren(...[...locations].sort().map((l) => h('option', { value: l })));
  }

  // ------------------------------------------------------- signature pad
  class SignaturePad {
    constructor(canvas) {
      this.canvas = canvas;
      this.wrap = canvas.parentElement;
      this.ctx = canvas.getContext('2d');
      this.dataUrl = '';
      this.drawing = false;
      this.onchange = () => {};
      this.size = { width: 0, height: 0 };
      new ResizeObserver(() => this.resize()).observe(this.wrap);
      canvas.addEventListener('pointerdown', (e) => this.start(e));
      canvas.addEventListener('pointermove', (e) => this.move(e));
      canvas.addEventListener('pointerup', () => this.end());
      canvas.addEventListener('pointercancel', () => this.end());
    }

    get hasInk() { return Boolean(this.dataUrl) || this.drawing; }

    resize() {
      const { width, height } = this.wrap.getBoundingClientRect();
      if (!width || !height) return;
      const dpr = Math.max(window.devicePixelRatio || 1, 1);
      const w = Math.round(width * dpr);
      const hgt = Math.round(height * dpr);
      if (this.canvas.width === w && this.canvas.height === hgt) return;
      this.canvas.width = w;
      this.canvas.height = hgt;
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      this.size = { width, height };
      if (this.dataUrl) this.paint(this.dataUrl, false);
    }

    pen() {
      const c = this.ctx;
      c.lineCap = 'round';
      c.lineJoin = 'round';
      c.strokeStyle = '#1b2a4a';
      c.fillStyle = '#1b2a4a';
      c.lineWidth = 2.4;
    }

    point(e) {
      const r = this.canvas.getBoundingClientRect();
      return { x: e.clientX - r.left, y: e.clientY - r.top };
    }

    start(e) {
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      e.preventDefault();
      this.canvas.setPointerCapture(e.pointerId);
      this.drawing = true;
      this.pen();
      this.last = this.point(e);
      this.lastMid = null;
      this.ctx.beginPath();
      this.ctx.arc(this.last.x, this.last.y, 1.2, 0, Math.PI * 2);
      this.ctx.fill();
      this.wrap.classList.add('has-ink');
    }

    move(e) {
      if (!this.drawing) return;
      e.preventDefault();
      const p = this.point(e);
      const mid = { x: (this.last.x + p.x) / 2, y: (this.last.y + p.y) / 2 };
      const from = this.lastMid || this.last;
      this.ctx.beginPath();
      this.ctx.moveTo(from.x, from.y);
      this.ctx.quadraticCurveTo(this.last.x, this.last.y, mid.x, mid.y);
      this.ctx.stroke();
      this.last = p;
      this.lastMid = mid;
    }

    end() {
      if (!this.drawing) return;
      this.drawing = false;
      this.dataUrl = this.canvas.toDataURL('image/png');
      this.onchange();
    }

    wipe() {
      this.ctx.save();
      this.ctx.setTransform(1, 0, 0, 1, 0, 0);
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
      this.ctx.restore();
    }

    clear(notify = true) {
      this.wipe();
      this.dataUrl = '';
      this.wrap.classList.remove('has-ink');
      if (notify) this.onchange();
    }

    /** Show an existing signature (draft restore) without re-encoding it. */
    load(dataUrl) {
      this.dataUrl = dataUrl;
      this.wrap.classList.add('has-ink');
      this.paint(dataUrl, false);
    }

    /** Draw an image fitted into the pad; when ``commit`` the pad content becomes the signature. */
    paint(url, commit) {
      const img = new Image();
      img.onload = () => {
        const { width, height } = this.size.width ? this.size : this.wrap.getBoundingClientRect();
        const pad = 10;
        const scale = Math.min((width - pad * 2) / img.width, (height - pad * 2) / img.height, 1.5);
        const w = img.width * scale;
        const hgt = img.height * scale;
        this.wipe();
        this.ctx.drawImage(img, (width - w) / 2, (height - hgt) / 2, w, hgt);
        this.wrap.classList.add('has-ink');
        if (commit) {
          this.dataUrl = this.canvas.toDataURL('image/png');
          this.onchange();
        }
      };
      img.onerror = () => toast('That image could not be read.', 'error');
      img.src = url;
    }

    toDataURL() { return this.dataUrl; }
  }

  const pad = new SignaturePad($('#sig-canvas'));
  pad.onchange = () => {
    $('[data-error-for="signature"]').hidden = true;
    onChange();
  };
  $('#sig-clear').addEventListener('click', () => pad.clear());
  $('#sig-upload').addEventListener('change', (e) => {
    const file = e.target.files[0];
    e.target.value = '';
    if (!file) return;
    if (file.size > 3 * 1024 * 1024) { toast('Signature image must be 3 MB or smaller.', 'error'); return; }
    const reader = new FileReader();
    reader.onload = () => pad.paint(reader.result, true);
    reader.readAsDataURL(file);
  });

  // -------------------------------------------------------- attachments
  const attachments = (() => {
    const list = $('#att-list');
    const input = $('#att-input');
    const zone = $('#dropzone');
    const items = []; // { id, file, url, error }
    const { max, maxMb, extensions } = CFG.attachments;
    let drag = null;

    function add(files) {
      const problems = [];
      for (const file of files) {
        const ext = (file.name.match(/\.[^.]+$/)?.[0] || '').toLowerCase();
        if (!extensions.includes(ext)) problems.push(`${file.name}: only PDF, JPG, PNG or WEBP`);
        else if (file.size === 0) problems.push(`${file.name}: file is empty`);
        else if (file.size > maxMb * 1048576) problems.push(`${file.name}: larger than ${maxMb} MB`);
        else if (items.length >= max) problems.push(`${file.name}: maximum ${max} files`);
        else if (items.some((i) => i.file.name === file.name && i.file.size === file.size && i.file.lastModified === file.lastModified)) {
          problems.push(`${file.name}: already added`);
        } else {
          items.push({ id: uid('att'), file, url: ext === '.pdf' ? null : URL.createObjectURL(file), error: '' });
        }
      }
      render();
      if (problems.length) toast(problems.join(' · '), 'warn', { timeout: 7000 });
    }

    function remove(id) {
      const index = items.findIndex((i) => i.id === id);
      if (index < 0) return;
      const [item] = items.splice(index, 1);
      if (item.url) URL.revokeObjectURL(item.url);
      render();
      const next = list.children[Math.min(index, items.length - 1)];
      (next ? $('.att-handle', next) : zone).focus();
    }

    function move(id, delta) {
      const from = items.findIndex((i) => i.id === id);
      const to = from + delta;
      if (from < 0 || to < 0 || to >= items.length) return;
      items.splice(to, 0, items.splice(from, 1)[0]);
      render();
    }

    function clear() {
      items.forEach((i) => i.url && URL.revokeObjectURL(i.url));
      items.length = 0;
      render();
    }

    function setError(index, message) {
      if (items[index]) { items[index].error = message; render(); }
    }

    function clearErrors() {
      if (items.some((i) => i.error)) { items.forEach((i) => { i.error = ''; }); render(); }
    }

    function renderItem(item, index) {
      const isPdf = !item.url;
      const thumb = isPdf
        ? h('span', { class: 'att-thumb pdf', text: 'PDF' })
        : h('img', { class: 'att-thumb', src: item.url, alt: '' });
      const meta = item.error
        ? h('span', { class: 'err', text: item.error })
        : `${isPdf ? 'PDF document' : 'Image · 1 page'} · ${fmtSize(item.file.size)}`;
      const up = iconButton('up', 'Move up', 'up');
      const down = iconButton('down', 'Move down', 'down');
      up.disabled = index === 0;
      down.disabled = index === items.length - 1;
      return h('li', { class: `att-item${item.error ? ' invalid' : ''}`, 'data-id': item.id },
        h('button', {
          type: 'button', class: 'att-handle', html: ICONS.grip,
          title: 'Drag to reorder (or focus and press ↑ / ↓)',
          'aria-label': `Position ${index + 1} of ${items.length}: ${item.file.name}. Press up or down arrow to move.`,
        }),
        h('span', { class: 'att-no', text: String(index + 1) }),
        thumb,
        h('div', { class: 'att-info' },
          h('div', { class: 'att-name', text: item.file.name, title: item.file.name }),
          h('div', { class: 'att-meta' }, meta)),
        h('div', { class: 'att-actions' }, up, down, iconButton('trash', 'Remove file', 'remove', 'danger')));
    }

    function render() {
      list.replaceChildren(...items.map(renderItem));
      $('#att-count').textContent = `${items.length} file${items.length === 1 ? '' : 's'}`;
      if (!items.some((i) => i.error)) $('[data-error-for="attachments"]').hidden = true;
      if (result.snapshot) setStep(items.length ? 3 : 2);
    }

    // ---- pick / drop files
    zone.addEventListener('click', (e) => { if (e.target !== input) input.click(); });
    zone.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); }
    });
    input.addEventListener('change', () => { add(Array.from(input.files)); input.value = ''; });
    const hasFiles = (e) => Array.from(e.dataTransfer?.types || []).includes('Files');
    ['dragenter', 'dragover'].forEach((type) => zone.addEventListener(type, (e) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
      zone.classList.add('is-over');
    }));
    zone.addEventListener('dragleave', (e) => { if (!zone.contains(e.relatedTarget)) zone.classList.remove('is-over'); });
    zone.addEventListener('drop', (e) => {
      e.preventDefault();
      zone.classList.remove('is-over');
      add(Array.from(e.dataTransfer.files));
    });
    // A file dropped next to the drop zone must not make the browser navigate away.
    window.addEventListener('dragover', (e) => { if (hasFiles(e)) e.preventDefault(); });
    window.addEventListener('drop', (e) => { if (hasFiles(e)) e.preventDefault(); });

    // ---- buttons + keyboard reorder
    list.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-action]');
      if (!btn) return;
      const id = btn.closest('.att-item').dataset.id;
      if (btn.dataset.action === 'remove') remove(id);
      else {
        move(id, btn.dataset.action === 'up' ? -1 : 1);
        const again = $(`[data-id="${id}"] [data-action="${btn.dataset.action}"]`, list);
        (again && !again.disabled ? again : $(`[data-id="${id}"] .att-handle`, list))?.focus();
      }
    });
    list.addEventListener('keydown', (e) => {
      const handle = e.target.closest('.att-handle');
      if (!handle || (e.key !== 'ArrowUp' && e.key !== 'ArrowDown')) return;
      e.preventDefault();
      const id = handle.closest('.att-item').dataset.id;
      move(id, e.key === 'ArrowUp' ? -1 : 1);
      $(`[data-id="${id}"] .att-handle`, list)?.focus();
    });

    // ---- drag to reorder (pointer events: mouse, touch and pen)
    list.addEventListener('pointerdown', (e) => {
      const handle = e.target.closest('.att-handle');
      if (!handle || (e.pointerType === 'mouse' && e.button !== 0)) return;
      e.preventDefault();
      handle.setPointerCapture(e.pointerId);
      const li = handle.closest('.att-item');
      drag = { li, id: li.dataset.id, startY: e.clientY, pointerId: e.pointerId };
      li.classList.add('is-dragging');
      list.classList.add('is-sorting');
    });
    /** Make the merge order (items) follow what the user sees (DOM order). */
    function syncOrderFromDom() {
      const order = Array.from(list.children).map((n) => n.dataset.id);
      items.sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
      Array.from(list.children).forEach((n, i) => { $('.att-no', n).textContent = String(i + 1); });
    }

    list.addEventListener('pointermove', (e) => {
      if (!drag || e.pointerId !== drag.pointerId) return;
      const { li } = drag;
      const siblings = Array.from(list.children);
      const from = siblings.indexOf(li);
      let to = 0; // = number of other items whose middle is above the pointer
      for (const other of siblings) {
        if (other === li) continue;
        const r = other.getBoundingClientRect();
        if (e.clientY > r.top + r.height / 2) to++;
      }
      if (to !== from) {
        const oldTop = li.offsetTop;
        // Move the neighbours, never the dragged item itself: re-inserting it
        // would make the browser drop its pointer capture mid-drag.
        for (let i = from; i > to; i--) li.after(li.previousElementSibling);
        for (let i = from; i < to; i++) li.before(li.nextElementSibling);
        drag.startY += li.offsetTop - oldTop; // keep the item under the pointer
        syncOrderFromDom();
      }
      li.style.transform = `translateY(${e.clientY - drag.startY}px)`;
    });
    const endDrag = (e) => {
      if (!drag || e.pointerId !== drag.pointerId) return;
      const { id, li } = drag;
      drag = null;
      li.style.transform = '';
      li.classList.remove('is-dragging');
      list.classList.remove('is-sorting');
      syncOrderFromDom();
      render();
      $(`[data-id="${id}"] .att-handle`, list)?.focus();
    };
    list.addEventListener('pointerup', endDrag);
    list.addEventListener('pointercancel', endDrag);
    list.addEventListener('lostpointercapture', endDrag);

    return {
      get items() { return items; },
      clear,
      setError,
      clearErrors,
    };
  })();

  // ----------------------------------------------------- collect / apply
  function collect() {
    const data = {
      name: field('name').value.trim(),
      dept: field('dept').value.trim(),
      month: Number(field('month').value),
      year: field('year').value.trim(),
      vehicle_no: field('vehicle_no').value.trim(),
      vehicle_model: field('vehicle_model').value.trim(),
      vehicle_type: currentVehicle(),
      options: { include_travel_sheet: field('include_travel_sheet').checked },
      signature: pad.toDataURL(),
    };
    for (const def of SECTION_DEFS) data[def.key] = rowEls(def.key).map(rowValues);
    return data;
  }

  function blankClaim() {
    const now = new Date();
    return {
      name: '', dept: '', month: now.getMonth() + 1, year: now.getFullYear(),
      vehicle_no: '', vehicle_model: '', vehicle_type: 'motorcycle',
      travel: [{ start: '09:00', finish: '18:00' }],
      entertainment: [], parking: [], subsistence: [], misc: [],
      options: { include_travel_sheet: true },
      signature: '',
    };
  }

  function apply(data, { keepSignature = false } = {}) {
    const now = new Date();
    for (const name of ['name', 'dept', 'vehicle_no', 'vehicle_model']) field(name).value = data[name] ?? '';
    field('month').value = String(data.month || now.getMonth() + 1);
    field('year').value = String(data.year || now.getFullYear());
    const vehicle = data.vehicle_type === 'car' ? 'car' : 'motorcycle';
    $$('input[name="vehicle_type"]', form).forEach((r) => { r.checked = r.value === vehicle; });
    field('include_travel_sheet').checked = data.options?.include_travel_sheet !== false;
    for (const def of SECTION_DEFS) {
      const rows = Array.isArray(data[def.key]) ? data[def.key].slice(0, def.capacity) : [];
      sections[def.key].rowsEl.replaceChildren(...rows.map((v) => buildRow(def, v || {})));
    }
    if (!keepSignature) {
      if (typeof data.signature === 'string' && data.signature.startsWith('data:image/')) pad.load(data.signature);
      else pad.clear(false);
    }
    clearAllErrors();
    onChange();
  }

  function hasContent() {
    if (['name', 'dept', 'vehicle_no', 'vehicle_model'].some((n) => field(n).value.trim())) return true;
    if (pad.hasInk || attachments.items.length) return true;
    return SECTION_DEFS.some((def) => rowEls(def.key).some((row) => !isBlank(def, rowValues(row))));
  }

  // ------------------------------------------------------------ drafts
  let saveTimer = 0;
  function scheduleSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveDraft, 500);
  }
  function saveDraft() {
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify({ savedAt: Date.now(), data: collect() }));
      $('#draft-status').textContent = `Draft saved on this device · ${timeNow()}`;
    } catch {
      $('#draft-status').textContent = 'Draft could not be saved (browser storage is full).';
    }
  }
  function loadDraft() {
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      return raw ? JSON.parse(raw).data : null;
    } catch {
      return null;
    }
  }

  // --------------------------------------------- generate / review / merge
  const result = { blob: null, url: null, filename: '', snapshot: null };

  function setStep(step) {
    $$('.stepper .step').forEach((li) => {
      const n = Number(li.dataset.step);
      li.classList.toggle('is-active', n === step);
      li.classList.toggle('is-done', n < step);
    });
  }

  const actionButtons = (action) => $$(`[data-action="${action}"]`);

  function setBusy(buttons, busy) {
    for (const b of buttons) {
      b.disabled = busy;
      if (busy) b.setAttribute('aria-busy', 'true');
      else b.removeAttribute('aria-busy');
    }
    if (!busy) updateStale();
  }

  function isStale() {
    return Boolean(result.snapshot) && JSON.stringify(collect()) !== result.snapshot;
  }

  function updateStale() {
    if (!result.snapshot) return;
    const stale = isStale();
    $('#stale-banner').hidden = !stale;
    const chip = $('#result-state');
    chip.textContent = stale ? 'Out of date' : 'Up to date';
    chip.className = `chip ${stale ? 'chip-warn' : 'chip-ok'}`;
    for (const b of [...actionButtons('merge'), ...actionButtons('download-claim')]) {
      if (b.getAttribute('aria-busy')) continue;
      b.disabled = stale;
      b.title = stale ? 'Regenerate the claim first - the form has changed.' : '';
    }
  }

  function onChange() {
    refresh();
    scheduleSave();
    updateStale();
  }

  function filenameFrom(res) {
    const direct = res.headers.get('X-Filename');
    if (direct) return direct;
    const cd = res.headers.get('Content-Disposition') || '';
    const star = /filename\*=UTF-8''([^;]+)/i.exec(cd);
    if (star) return decodeURIComponent(star[1]);
    const plain = /filename="?([^";]+)"?/i.exec(cd);
    return plain ? plain[1] : 'claim.pdf';
  }

  async function post(url, body, buttons) {
    setBusy(buttons, true);
    try {
      const res = await fetch(url, { method: 'POST', body });
      if (res.ok) return { blob: await res.blob(), filename: filenameFrom(res) };
      let errors = null;
      try { errors = (await res.json()).errors; } catch { /* not JSON */ }
      if (errors) showErrors(errors);
      else toast(`The server returned an error (${res.status}). Please try again.`, 'error');
    } catch {
      toast('Cannot reach the claim server. Is it still running?', 'error');
    } finally {
      setBusy(buttons, false);
    }
    return null;
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = h('a', { href: url, download: filename });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }

  async function generateClaim() {
    const payload = collect();
    const body = new FormData();
    body.append('payload', JSON.stringify(payload));
    const res = await post('/api/generate', body, actionButtons('generate'));
    if (!res) return;

    if (result.url) URL.revokeObjectURL(result.url);
    result.blob = res.blob;
    result.filename = res.filename;
    result.snapshot = JSON.stringify(payload);
    result.url = URL.createObjectURL(res.blob);

    const pages = 2 + (payload.options.include_travel_sheet ? 1 : 0);
    $('#result-meta').textContent =
      `${res.filename} · ${pages} pages · total RM ${fmtMoney(lastTotalSen)} · generated ${timeNow()}`;
    $('#preview').src = `${result.url}#view=FitH`;
    $('#result').hidden = false;
    updateStale();
    setStep(attachments.items.length ? 3 : 2);
    requestAnimationFrame(() => $('#result').scrollIntoView({ behavior: 'smooth', block: 'start' }));
    toast('Claim generated. Review it below, then attach your proofs and merge.', 'success');
  }

  async function mergeAndDownload() {
    if (!result.snapshot) return;
    if (isStale()) { toast('The form changed - regenerate the claim first.', 'warn'); return; }
    const files = attachments.items;
    if (!files.length) {
      toast('Add at least one proof to merge, or use “Download claim only”.', 'warn');
      $('#dropzone').focus();
      return;
    }
    attachments.clearErrors();
    const body = new FormData();
    body.append('payload', result.snapshot);
    files.forEach((a) => body.append('attachments', a.file, a.file.name));
    const res = await post('/api/merge', body, actionButtons('merge'));
    if (!res) return;
    downloadBlob(res.blob, res.filename);
    toast(`Downloaded ${res.filename} (claim + ${files.length} proof${files.length === 1 ? '' : 's'}).`, 'success');
  }

  function downloadClaimOnly() {
    if (!result.blob) return;
    if (isStale()) { toast('The form changed - regenerate the claim first.', 'warn'); return; }
    downloadBlob(result.blob, result.filename);
  }

  function resetResult() {
    if (result.url) URL.revokeObjectURL(result.url);
    Object.assign(result, { blob: null, url: null, filename: '', snapshot: null });
    $('#preview').removeAttribute('src');
    $('#result').hidden = true;
    setStep(1);
  }

  // ------------------------------------------------------------- wiring
  form.addEventListener('submit', (e) => e.preventDefault());
  form.addEventListener('input', (e) => {
    const t = e.target;
    if (t.classList?.contains('invalid')) clearInvalid(t);
    if (t.name) {
      const p = $(`[data-error-for="${t.name}"]`);
      if (p) p.hidden = true;
    }
    onChange();
  });
  form.addEventListener('change', onChange);
  field('include_travel_sheet').addEventListener('change', onChange);

  // Tidy numbers when leaving a field: "75" -> "75.00", "RM 1,200" -> "1200.00".
  form.addEventListener('focusout', (e) => {
    const input = e.target;
    if (!input.matches?.('input[data-key]')) return;
    const key = input.closest('section[data-section]')?.dataset.section;
    const f = key && fieldDef(key, input.dataset.key);
    if (!f || (f.type !== 'money' && f.type !== 'distance') || !input.value.trim()) return;
    const value = toHundredths(input.value);
    if (value === null) {
      setInvalid(input, `${f.type === 'money' ? 'Amount' : 'Distance'} must be a number, e.g. ${f.type === 'money' ? '12.50' : '32'}.`);
    } else if (value === 0) {
      setInvalid(input, `${f.type === 'money' ? 'Amount' : 'Distance'} must be greater than 0.`);
    } else {
      const tidy = f.type === 'money' ? (value / 100).toFixed(2) : fmtKm(value);
      if (tidy !== input.value) { input.value = tidy; onChange(); }
      return;
    }
    renderRowMsg(input.closest('.row'), []);
    refresh();
  });

  actionButtons('generate').forEach((b) => b.addEventListener('click', generateClaim));
  actionButtons('merge').forEach((b) => b.addEventListener('click', mergeAndDownload));
  actionButtons('download-claim').forEach((b) => b.addEventListener('click', downloadClaimOnly));

  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); generateClaim(); }
  });

  $('#btn-sample').addEventListener('click', async () => {
    if (hasContent() && !window.confirm('Replace the current entries with the sample data?')) return;
    try {
      const res = await fetch('/api/sample');
      if (!res.ok) throw new Error(String(res.status));
      apply(await res.json(), { keepSignature: true });
      window.scrollTo({ top: 0, behavior: 'smooth' });
      toast('Sample data loaded. Click “Generate claim” to see the PDF.', 'success');
    } catch {
      toast('Could not load the sample data.', 'error');
    }
  });

  $('#btn-clear').addEventListener('click', () => {
    if (hasContent() && !window.confirm('Clear the whole form? Your signature and attached files are removed too.')) return;
    attachments.clear();
    resetResult();
    apply(blankClaim());
    toast('Form cleared.', 'info');
  });

  window.addEventListener('beforeunload', (e) => {
    if (attachments.items.length) { e.preventDefault(); e.returnValue = ''; }
  });

  // --------------------------------------------------------------- start
  const draft = loadDraft();
  if (draft) {
    apply(draft);
    if (hasContent()) toast('Your saved draft was restored.', 'info');
  } else {
    apply(blankClaim());
  }
  if (new URLSearchParams(window.location.search).has('sample')) $('#btn-sample').click();
})();
