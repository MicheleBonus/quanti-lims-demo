# Paste Weigh-Ins Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Ctrl+V bulk-paste to the weigh-in table so TAs can fill multiple Proben at once from any tab-separated source (Excel, balance output, text file), starting from any anchor row.

**Architecture:** Pure JavaScript and CSS additions inline in `templates/ta/weighing.html`. No backend changes, no new files. The paste handler reads clipboard text, parses it into `{m_s, m_ges}` pairs, fills the existing input fields starting from the anchor row, and fires `InputEvent('input')` on each field to trigger the already-present live-calculation JS.

**Tech Stack:** Vanilla JS (ES6), Jinja2 template, Bootstrap 5, existing `weighing-input` CSS class and `data-field` attributes.

---

## Files

| Action | Path | What changes |
|---|---|---|
| Modify | `templates/ta/weighing.html` | Add `<style>` block + JS block at bottom of `{% block scripts %}` |

No other files change.

---

## Reference: Key DOM facts

Before starting, keep these in mind:

- Every sample `<tr>` has `data-row-sample-id="{{ s.id }}"`.
- The running number is rendered as `<td><strong>{{ s.running_number }}</strong></td>` — first `<td>` in each row.
- Mass-based mode: each row has `[data-field="m_s"]` and `[data-field="m_ges"]` inputs.
- Standardization mode: each row has only `[data-field="m_ges"]` input (reused for V_disp).
- All inputs share class `weighing-input`.
- `const MODE = '...'` is already rendered at the top of the `{% block scripts %}` block — use it for mode detection.
- The existing `input` event listener (line 217–302) triggers all live calculations when fired — dispatching `new InputEvent('input', { bubbles: true })` on a filled field is sufficient to update G_wahr, Max. m_ges, status icons, etc.

---

## Task 1: Add CSS — anchor row highlight + toast

**Files:**
- Modify: `templates/ta/weighing.html` (before `{% endblock %}` of `{% block content %}`, or inside `{% block scripts %}` as an inline `<style>`)

- [ ] **Step 1: Add the `<style>` block**

  Add this as the first thing inside `{% block scripts %}`, before the existing `<script>` tag:

  ```html
  <style>
  .paste-anchor-row td:first-child {
    border-left: 3px solid #fd7e14;
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
  </style>
  ```

- [ ] **Step 2: Verify CSS loads**

  Open the weigh-in page in the browser. Open DevTools console and run:
  ```js
  document.querySelector('tbody tr').classList.add('paste-anchor-row');
  ```
  Expected: first row gets orange left border and subtle orange tint.
  Then run `document.querySelector('tbody tr').classList.remove('paste-anchor-row')` to clean up.

- [ ] **Step 3: Commit**

  ```bash
  git add templates/ta/weighing.html
  git commit -m "feat: add CSS for paste anchor row and toast"
  ```

---

## Task 2: Add `parseClipboard` pure function

**Files:**
- Modify: `templates/ta/weighing.html` (add inside `{% block scripts %}` after the existing `</script>` closing tag — add a new `<script>` block)

The function is mode-agnostic: it always returns `{m_s, m_ges}`. In standardization mode the caller only uses `m_ges`.

- [ ] **Step 1: Add the function**

  Add a new `<script>` block at the bottom of `{% block scripts %}` (after the existing `</script>`):

  ```html
  <script>
  // ── Clipboard paste feature ──────────────────────────────────────────────

  /**
   * Parse tab-separated clipboard text into an array of {m_s, m_ges} pairs.
   * - Decimal separator: both '.' and ',' accepted.
   * - Column detection: determined from the FIRST parseable row, applied uniformly.
   *   - 1 col  → m_s only (m_ges null)
   *   - 2 cols → col0=m_s, col1=m_ges
   *   - 3+ cols → scan left-to-right for first numeric col (m_s), then next numeric (m_ges).
   *              If only one numeric found → m_s only.
   * - Blank/unparseable rows → skipped (do NOT advance probe counter).
   * @param {string} text
   * @returns {{m_s: number|null, m_ges: number|null}[]}
   */
  function parseClipboard(text) {
    const lines = text.split('\n').map(l => l.replace(/\r$/, ''));
    const toNum = s => { const n = parseFloat(s.replace(',', '.')); return isFinite(n) ? n : null; };

    // Detect column offsets from first parseable row
    let msCol = null, mgesCol = null;
    for (const line of lines) {
      if (!line.trim()) continue;
      const cols = line.split('\t');
      if (cols.length === 1) {
        const v = toNum(cols[0]);
        if (v !== null) { msCol = 0; mgesCol = null; break; }
      } else if (cols.length === 2) {
        const v0 = toNum(cols[0]), v1 = toNum(cols[1]);
        if (v0 !== null) { msCol = 0; mgesCol = v1 !== null ? 1 : null; break; }
      } else {
        // 3+ columns: scan for first two numeric columns
        let first = null, second = null;
        for (let i = 0; i < cols.length; i++) {
          const v = toNum(cols[i]);
          if (v !== null) {
            if (first === null) first = i;
            else { second = i; break; }
          }
        }
        if (first !== null) { msCol = first; mgesCol = second; break; }
      }
    }

    if (msCol === null) return []; // nothing parseable

    const result = [];
    for (const line of lines) {
      if (!line.trim()) continue;
      const cols = line.split('\t');
      const ms = toNum(cols[msCol] ?? '');
      const mges = mgesCol !== null ? toNum(cols[mgesCol] ?? '') : null;
      if (ms === null && mges === null) continue; // skip fully unparseable rows
      result.push({ m_s: ms, m_ges: mges });
    }
    return result;
  }
  </script>
  ```

- [ ] **Step 2: Verify function in browser console**

  Open the weigh-in page. In DevTools console, test:

  ```js
  // 2-column
  console.assert(parseClipboard("0.1823\t1.2045\n0.1756\t1.1987").length === 2, "2-col length");
  console.assert(parseClipboard("0.1823\t1.2045\n0.1756\t1.1987")[0].m_s === 0.1823, "m_s col0");
  console.assert(parseClipboard("0.1823\t1.2045\n0.1756\t1.1987")[0].m_ges === 1.2045, "m_ges col1");

  // 1-column
  console.assert(parseClipboard("0.1823\n0.1756").length === 2, "1-col length");
  console.assert(parseClipboard("0.1823\n0.1756")[0].m_ges === null, "1-col m_ges null");

  // German comma decimals
  console.assert(parseClipboard("0,1823\t1,2045")[0].m_s === 0.1823, "comma decimal");

  // 3+ col with text ID
  console.assert(parseClipboard("S1\t0.1823\t1.2045")[0].m_s === 0.1823, "3-col skip text");
  console.assert(parseClipboard("S1\t0.1823\t1.2045")[0].m_ges === 1.2045, "3-col m_ges");

  // Blank line skipped
  const r = parseClipboard("0.1823\t1.2045\n\n0.1756\t1.1987");
  console.assert(r.length === 2, "blank line skipped");

  // Empty input
  console.assert(parseClipboard("").length === 0, "empty string");
  console.assert(parseClipboard("no numbers here").length === 0, "no numbers");

  console.log("All parseClipboard assertions passed");
  ```

  Expected: no assertion errors, last log line printed.

- [ ] **Step 3: Commit**

  ```bash
  git add templates/ta/weighing.html
  git commit -m "feat: add parseClipboard function for weigh-in paste"
  ```

---

## Task 3: Add anchor tracking + probe-number map

**Files:**
- Modify: `templates/ta/weighing.html` (append to the paste feature `<script>` block from Task 2)

- [ ] **Step 1: Add anchor state + probe-number map init**

  Append inside the paste feature `<script>` block (after `parseClipboard`):

  ```js
  // ── Anchor tracking ───────────────────────────────────────────────────────

  let anchorRowIndex = null;

  // sampleRows: ordered array of <tr> elements in tbody (one per sample)
  const sampleRows = [...document.querySelectorAll('#weighing-table tbody tr')];

  // probeNumberByRowIndex: maps row index → running_number (integer)
  // Read from the <strong> in the first <td> of each row at page load.
  const probeNumberByRowIndex = sampleRows.map(tr => {
    const strong = tr.querySelector('td:first-child strong');
    return strong ? parseInt(strong.textContent, 10) : null;
  });

  function setAnchorRow(rowIndex) {
    sampleRows.forEach(tr => tr.classList.remove('paste-anchor-row'));
    anchorRowIndex = rowIndex;
    if (rowIndex !== null && sampleRows[rowIndex]) {
      sampleRows[rowIndex].classList.add('paste-anchor-row');
    }
  }

  function clearAnchorRow() {
    setAnchorRow(null);
  }

  // Attach focus listener to all weighing inputs
  document.querySelectorAll('.weighing-input').forEach(input => {
    input.addEventListener('focus', () => {
      const tr = input.closest('tr');
      const idx = sampleRows.indexOf(tr);
      if (idx >= 0) setAnchorRow(idx);
    });
  });
  ```

- [ ] **Step 2: Verify anchor in browser console**

  Open the weigh-in page. Click into the m_s field of the 3rd sample row.
  In DevTools console:
  ```js
  console.log('anchorRowIndex:', anchorRowIndex); // expect 2
  console.log('probeNumberByRowIndex:', probeNumberByRowIndex); // expect [1,2,3,...]
  ```
  Also verify visually: the 3rd row should have an orange left border.
  Click a field in row 1 — orange border should move to row 1.

- [ ] **Step 3: Commit**

  ```bash
  git add templates/ta/weighing.html
  git commit -m "feat: add anchor row tracking for paste weigh-in"
  ```

---

## Task 4: Add `fillRows` + `showPasteToast` functions

**Files:**
- Modify: `templates/ta/weighing.html` (append to paste feature `<script>` block)

- [ ] **Step 1: Add `showPasteToast`**

  Append inside the paste feature `<script>` block:

  ```js
  // ── Toast feedback ────────────────────────────────────────────────────────

  function showPasteToast(count, firstNum, lastNum) {
    const label = MODE === 'titrant_standardization' ? 'Dispensierungen' : 'Einwaagen';
    const rangeText = firstNum === lastNum ? `Probe ${firstNum}` : `Proben ${firstNum}–${lastNum}`;
    const div = document.createElement('div');
    div.className = 'paste-toast';
    div.textContent = `${count} ${label} eingefügt (${rangeText})`;
    div.addEventListener('animationend', () => div.remove());
    document.body.appendChild(div);
  }
  ```

- [ ] **Step 2: Add `fillRows`**

  Append inside the paste feature `<script>` block:

  ```js
  // ── Fill rows from parsed clipboard data ──────────────────────────────────

  /**
   * Fill sample input fields starting at startIndex (row index, 0-based).
   * @param {{m_s: number|null, m_ges: number|null}[]} parsed
   * @param {number} startIndex - row index of first row to fill
   */
  function fillRows(parsed, startIndex) {
    const msInputs  = [...document.querySelectorAll('[data-field="m_s"]')];
    const mgesInputs = [...document.querySelectorAll('[data-field="m_ges"]')];

    let filled = 0;
    let firstFilledRow = null;
    let lastFilledRow = null;

    for (let i = 0; i < parsed.length; i++) {
      const rowIdx = startIndex + i;
      const { m_s, m_ges } = parsed[i];

      const msInput  = msInputs[rowIdx];
      const mgesInput = mgesInputs[rowIdx];

      if (!msInput && !mgesInput) break; // past end of table

      if (msInput && m_s !== null) {
        msInput.value = String(m_s);
        msInput.dispatchEvent(new InputEvent('input', { bubbles: true }));
      }
      if (mgesInput && m_ges !== null) {
        mgesInput.value = String(m_ges);
        mgesInput.dispatchEvent(new InputEvent('input', { bubbles: true }));
      }

      // Count as filled if at least one value was written
      if ((msInput && m_s !== null) || (mgesInput && m_ges !== null)) {
        filled++;
        if (firstFilledRow === null) firstFilledRow = rowIdx;
        lastFilledRow = rowIdx;
      }
    }

    if (filled > 0) {
      const firstNum = probeNumberByRowIndex[firstFilledRow] ?? (firstFilledRow + 1);
      const lastNum  = probeNumberByRowIndex[lastFilledRow]  ?? (lastFilledRow  + 1);
      showPasteToast(filled, firstNum, lastNum);
    }
  }
  ```

- [ ] **Step 3: Verify `fillRows` in browser console**

  Open the weigh-in page (mass-based batch). In DevTools console:

  ```js
  // Fill rows 0 and 1 with test data
  fillRows([{ m_s: 0.1234, m_ges: 1.2345 }, { m_s: 0.1111, m_ges: 1.1111 }], 0);
  ```

  Expected:
  - First two rows have their m_s and m_ges fields filled with the test values.
  - G_wahr, Max. m_ges, V_erw., status icons update immediately.
  - Toast appears bottom-right: "2 Einwaagen eingefügt (Proben 1–2)", fades after 3 s.

- [ ] **Step 4: Verify in standardization mode** (if a standardization batch is available)

  ```js
  fillRows([{ m_s: null, m_ges: 14.23 }, { m_s: null, m_ges: 13.87 }], 0);
  ```

  Expected: V_disp fields filled, Zielfaktor updated, toast reads "2 Dispensierungen eingefügt".

- [ ] **Step 5: Commit**

  ```bash
  git add templates/ta/weighing.html
  git commit -m "feat: add fillRows and showPasteToast for weigh-in paste"
  ```

---

## Task 5: Wire up the paste event handler

**Files:**
- Modify: `templates/ta/weighing.html` (append to paste feature `<script>` block)

- [ ] **Step 1: Add the paste handler**

  Append inside the paste feature `<script>` block:

  ```js
  // ── Global paste handler ──────────────────────────────────────────────────

  document.addEventListener('paste', event => {
    // If a field is focused, let the browser handle paste normally
    const active = document.activeElement;
    if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.tagName === 'SELECT')) {
      return;
    }

    const text = event.clipboardData.getData('text/plain');
    if (!text || !text.trim()) return;

    const parsed = parseClipboard(text);
    if (parsed.length === 0) return;

    fillRows(parsed, anchorRowIndex ?? 0);
    clearAnchorRow();
    event.preventDefault();
  });
  ```

- [ ] **Step 2: Test — paste from row 1 (no anchor)**

  1. Open a mass-based weigh-in page.
  2. Copy this text (tab between columns, newline between rows):
     ```
     0.1823	1.2045
     0.1756	1.1987
     0.1901	1.2312
     ```
  3. Click anywhere on the page that is NOT an input field (e.g. the page heading).
  4. Press Ctrl+V.
  Expected: rows 1–3 fill with the values; G_wahr / Max. m_ges / status icons update; toast shows "3 Einwaagen eingefügt (Proben 1–3)".

- [ ] **Step 3: Test — paste from anchor row**

  1. Click into the m_s field of row 4 (orange border appears on row 4).
  2. Click somewhere neutral (not an input).
  3. Copy 2 rows of data.
  4. Press Ctrl+V.
  Expected: rows 4 and 5 fill; rows 1–3 are untouched; toast shows "2 Einwaagen eingefügt (Proben 4–5)".

- [ ] **Step 4: Test — single-field paste still works**

  1. Click into any m_s field.
  2. Select all text in the field (Ctrl+A).
  3. Type a value and then press Ctrl+V with a single number in clipboard (e.g. copy "0.1234" from somewhere).
  Expected: the single value pastes into that field normally; the bulk handler does NOT fire.

- [ ] **Step 5: Test — fewer clipboard rows than remaining samples**

  Copy 2 rows. Anchor on row 5. Ctrl+V.
  Expected: only rows 5 and 6 fill; row 7 and beyond unchanged.

- [ ] **Step 6: Test — German comma decimals**

  Copy: `0,1823	1,2045`
  Paste without anchor.
  Expected: row 1 fills with 0.1823 and 1.2045 (commas converted).

- [ ] **Step 7: Test — 1-column paste (m_s only)**

  Copy a single column (e.g. from a balance printout):
  ```
  0.1823
  0.1756
  ```
  Paste without anchor.
  Expected: m_s fields of rows 1–2 fill; m_ges fields left unchanged.

- [ ] **Step 8: Test — clipboard with blank separator line**

  Copy:
  ```
  0.1823	1.2045

  0.1756	1.1987
  ```
  (blank line between rows).
  Expected: rows 1 and 2 fill (blank line skipped, counter does not skip a row).

- [ ] **Step 9: Commit**

  ```bash
  git add templates/ta/weighing.html
  git commit -m "feat: wire up Ctrl+V paste handler for weigh-in table"
  ```

---

## Task 6: Final review pass

- [ ] **Step 1: Check the page with no samples** (edge case)

  If a batch with 0 samples can be rendered, open it and press Ctrl+V. Expected: nothing happens, no errors in console.

- [ ] **Step 2: Check anchor clears after paste**

  Anchor a row (orange border visible), then Ctrl+V. Expected: orange border disappears after fill.

- [ ] **Step 3: Check anchor moves when tabbing between fields**

  Tab through the input fields using keyboard. Expected: the orange border follows focus to each new row.

- [ ] **Step 4: Check the toast disappears cleanly**

  After paste, wait 3 seconds. Expected: toast fades out and is removed from the DOM (verify with DevTools Elements panel — no `div.paste-toast` remaining).

- [ ] **Step 5: Commit final state**

  ```bash
  git add templates/ta/weighing.html
  git commit -m "feat: complete clipboard paste for weigh-in table"
  ```
