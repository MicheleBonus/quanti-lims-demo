# Design: Clipboard Paste for Weigh-In

**Date:** 2026-03-20
**Status:** Ready for Review

---

## Problem

TAs currently enter weigh-in values (`m_s` and `m_ges`) one by one into the table in `weighing.html`. When data already exists in a structured source (Excel, balance output, text file), manual re-entry is slow and error-prone.

## Goal

Allow TAs to copy tabular weigh-in data from any source and paste it directly into the weigh-in table — filling multiple Proben at once, starting from any row.

---

## Interaction Design

### Trigger

`Ctrl+V` while no input field is focused fires the bulk-paste handler. If `document.activeElement` is an `<input>` or `<textarea>`, the event is not intercepted and default behaviour applies (paste into that field).

### Anchor Row

Clicking (or tabbing into) any `weighing-input` field sets that field's row as the **paste anchor** — the row where filling begins. Anchor is tracked via a `focus` listener on all `.weighing-input` elements; the listener records the row index of the focused field in a module-level variable `anchorRowIndex`. The anchor row receives CSS class `paste-anchor-row` (orange left border + subtle background), removing the class from the previously anchored row.

The anchor persists until:
- a bulk paste fires (anchor clears and CSS class is removed after fill), or
- the user focuses a field in a different row (anchor moves to new row).

If no anchor has been set when `Ctrl+V` fires, paste starts from row 0 (first sample row).

### Fill Behaviour

- Fills from the anchor row downward, one clipboard row per Probe row.
- Overwrites existing values (allows corrections to already-filled rows).
- Blank and unparseable clipboard rows are skipped **and do not advance the Probe row counter** (skip-and-compress: next valid clipboard row fills the immediately next Probe row). Blank lines are never treated as intentional "skip this sample" markers.
- If the clipboard has fewer valid rows than remaining Proben, only those rows are filled; the rest stay unchanged.
- If the clipboard has more valid rows than remaining Proben, extra rows are ignored.

### Post-Fill Feedback

Each filled field dispatches `new InputEvent('input', { bubbles: true })` so the existing live-calculation JS (G_wahr, Max. m_ges, V_erw., status icons) updates immediately — no additional calculation code is needed.

A toast `<div>` is appended to `<body>`, positioned fixed bottom-right, and shows a German-language message (all user-facing strings are in German throughout the UI): e.g. *"3 Einwaagen eingefügt (Proben 4–6)"* or *"3 Dispensierungen eingefügt (Proben 4–6)"*. The toast fades out and is removed after 3 seconds via a CSS animation.

---

## Clipboard Parsing

### Format

Tab-separated values (`\t`), one Probe per line (`\n` or `\r\n`). Decimal separator: both `.` and `,` are accepted (replace `,` with `.` before `parseFloat`).

### Column Detection — determined once from the first valid row, applied uniformly

Read the first non-empty, parseable row and count its tab-separated columns. Apply the same column offset to all subsequent rows:

| Columns in first valid row | Interpretation |
|---|---|
| 1 | col 0 = m_s only — m_ges field left untouched |
| 2 | col 0 = m_s, col 1 = m_ges |
| 3+ | Scan columns left-to-right; find the first column that parses as a number — that is `m_s` (or `v_disp` in standardization mode). The immediately following numeric column is `m_ges`. Non-numeric leading columns (e.g. sample ID text) are skipped. These offsets are fixed for all remaining rows. If only one numeric column is found among 3+ columns (e.g. `"A\t0.1234\tpending"`), treat as 1-column: `m_s` only, `m_ges` untouched. |

### Invalid Rows

A row is invalid if it is empty or if none of its columns parse as a finite number after comma/period normalisation. Invalid rows are silently skipped and do not advance the Probe row counter.

---

## Volumendispensierung Mode

Mode is detected at runtime via the existing JS constant `const MODE = '{{ batch.analysis.calculation_mode }}'` rendered in `weighing.html`. When `MODE === 'titrant_standardization'`, the template renders no `data-field="m_s"` inputs; the single dispensed-volume input uses `data-field="m_ges"` (reusing the same field name).

In this mode:
- The paste handler collects only `[data-field="m_ges"]` inputs (there are no `[data-field="m_s"]` inputs in the DOM).
- Only the first numeric column of each clipboard row is used (`v_disp`); additional columns are ignored.
- The toast reads *"N Dispensierungen eingefügt (Proben X–Y)"*.

---

## Implementation Scope

- **File changed:** `templates/ta/weighing.html` only
- **No backend changes required**
- **No new files**

### JavaScript additions (all inline at the bottom of the `{% block scripts %}` block)

1. **Anchor tracking**
   - At init: build `sampleRows = [...document.querySelectorAll('tbody tr')]` (one entry per sample row). Add a `focus` listener to each `.weighing-input`.
   - On focus: record `anchorRowIndex` = `sampleRows.indexOf(event.target.closest('tr'))` — a **row index**, not an input index. Remove `paste-anchor-row` class from all rows; add it to the focused input's `<tr>`.
   - Keeping the anchor as a row index means `fillRows` can use it directly with `msInputs[anchorRowIndex + i]` regardless of how many inputs exist per row.

2. **Paste handler**
   - `document.addEventListener('paste', handler)`.
   - Guard: if `document.activeElement` is an `<input>`, `<textarea>`, or `<select>`, call `return` immediately **without** calling `event.preventDefault()` — the browser must handle normal field paste.
   - Only after the guard passes: read `event.clipboardData.getData('text/plain')`, call `parseClipboard(text)`, call `fillRows(parsed, anchorRowIndex ?? 0)`, clear the anchor, then call `event.preventDefault()`.

3. **`parseClipboard(text)` — pure function**
   - Split on `\n`, trim `\r`.
   - Skip empty lines.
   - Detect column offsets from first parseable row (see Column Detection above).
   - Always return `{m_s: number|null, m_ges: number|null}`. In standardization mode the DOM reuses `data-field="m_ges"` for V_disp, so parsing into `m_ges` is correct. `m_s` is `null` in that case (no m_s inputs exist in the DOM). There is no `{v_disp}` variant.

4. **`fillRows(parsed, startIndex)` — fills DOM inputs**
   - Build a **probe-number map** once at init: for each `.weighing-input`, read the running number from the `<strong>` element in the first `<td>` of its `<tr>` and store it keyed by input index. This pre-built map avoids repeated DOM traversal and is robust to future formatting changes (as long as the `<strong>` holds the number on page load).
   - Build ordered arrays `msInputs = [...document.querySelectorAll('[data-field="m_s"]')]` and `mgesInputs = [...document.querySelectorAll('[data-field="m_ges"]')]`.
   - `startIndex` is a **row index** (from `anchorRowIndex`, not a flat input index). In mass-based mode: `msInputs[startIndex + i]` and `mgesInputs[startIndex + i]`. In standardization mode `msInputs` is empty; use `mgesInputs[startIndex + i]` only. Because `msInputs` and `mgesInputs` each have exactly one entry per sample row, the row index maps directly to the array index.
   - For each filled input: set `.value`, dispatch `new InputEvent('input', { bubbles: true })`.
   - Record running numbers of the first and last filled rows using the pre-built probe-number map. The toast shows the actual first and last running numbers (e.g. "Proben 4–6"), which may not be contiguous if buffer rows are mixed in — that is acceptable.
   - Call `showPasteToast(count, firstRunningNum, lastRunningNum)`.

5. **`showPasteToast(count, first, last)` — feedback**
   - Create a `<div class="paste-toast">` appended to `<body>`.
   - Text (German): `"${count} ${MODE === 'titrant_standardization' ? 'Dispensierungen' : 'Einwaagen'} eingefügt (Proben ${first}–${last})"`.
   - CSS: fixed, bottom-right, fade-out via `@keyframes pasteToastFade` animation; `animationend` listener removes the element.

### CSS additions (inline `<style>` block in the template)

```css
.paste-anchor-row td:first-child {
  border-left: 3px solid #fd7e14;  /* Bootstrap orange */
}
.paste-anchor-row {
  background-color: rgba(253, 126, 20, 0.07);
}
.paste-toast {
  position: fixed;
  bottom: 1.5rem;
  right: 1.5rem;
  z-index: 9999;
  background: #d1e7dd;
  border: 1px solid #a3cfbb;
  color: #0a3622;
  border-radius: 0.5rem;
  padding: 0.5rem 1rem;
  font-size: 0.85rem;
  animation: pasteToastFade 3s ease forwards;
}
@keyframes pasteToastFade {
  0%   { opacity: 1; }
  70%  { opacity: 1; }
  100% { opacity: 0; }
}
```

---

## Out of Scope

- Import from file (CSV upload)
- Pasting the `weighed_by` field
- Undo/revert after paste (browser refresh serves as undo)
- Any backend changes
