# Design: Clipboard Paste for Weigh-In

**Date:** 2026-03-20
**Status:** Approved

---

## Problem

TAs currently enter weigh-in values (`m_s` and `m_ges`) one by one into the table in `weighing.html`. When data already exists in a structured source (Excel, balance output, text file), manual re-entry is slow and error-prone.

## Goal

Allow TAs to copy tabular weigh-in data from any source and paste it directly into the weigh-in table — filling multiple Proben at once, starting from any row.

---

## Interaction Design

### Trigger

`Ctrl+V` while no input field is focused fires the bulk-paste handler. If a field is focused, `Ctrl+V` behaves normally (pastes into that field only).

### Anchor Row

Clicking any field in a table row sets that row as the **paste anchor** — the row where filling begins. The anchor row is highlighted with an orange border/background and a "paste here" label. The anchor persists until:
- a paste fires (anchor clears after fill), or
- the user clicks a field in a different row (anchor moves).

If no anchor is set when `Ctrl+V` fires, paste starts from row 1.

### Fill Behaviour

- Fills from the anchor row downward, one clipboard row per Probe row.
- Overwrites existing values (allows corrections).
- If the clipboard has fewer rows than remaining Proben, only those rows are filled; the rest stay unchanged.
- If the clipboard has more rows than remaining Proben, extra rows are ignored.

### Post-Fill Feedback

Each filled field dispatches an `input` event so the existing live-calculation JS (G_wahr, Max. m_ges, V_erw., status icons) updates immediately.

A toast message appears briefly: *"3 Einwaagen eingefügt (Proben 4–6)"* — fades after 3 seconds.

---

## Clipboard Parsing

### Format

Tab-separated values, one Probe per line. Decimal separator: both `.` and `,` accepted.

### Column Detection

| Columns per row | Interpretation |
|---|---|
| 1 | m_s only — m_ges field left untouched |
| 2 | col 1 = m_s, col 2 = m_ges |
| 3+ | First two columns that parse as numbers are used; non-numeric leading column (e.g. a sample ID) is skipped |

### Invalid Rows

Blank lines and rows that cannot be parsed as numbers are silently skipped (do not advance the row counter).

---

## Volumendispensierung Mode

The same mechanism applies to the titrant standardisation mode: paste fills the single `V_disp` column starting from the anchor row.

---

## Implementation Scope

- **File changed:** `templates/ta/weighing.html` only
- **No backend changes required**
- **No new files**

### JavaScript additions (all inline in `weighing.html`)

1. **Anchor tracking** — `mousedown` / `focus` listener on all `m_s` and `m_ges` inputs records the current anchor row index. Adds CSS class to the anchor row; removes it from the previous anchor row.

2. **Paste handler** — `document.addEventListener('paste', ...)`. Guards:
   - If `document.activeElement` is an `<input>` or `<textarea>`, return early (normal paste).
   - Otherwise, read `event.clipboardData.getData('text/plain')`, parse, and fill.

3. **Parser** — pure function: `parseClipboard(text) → [{m_s, m_ges}]`. Handles tab/comma/period variants. Returns only valid rows.

4. **Filler** — iterates parsed rows against the ordered list of `[m_s_input, m_ges_input]` pairs (derived from the existing sample order in the DOM), starting at anchor index.

5. **Toast** — a small `<div>` injected into the page, shown with a CSS fade-out animation, removed after 3 s.

### CSS additions

- `.anchor-row` — orange left border + subtle background tint
- `.paste-toast` — fixed bottom-right position, fade-out animation

---

## Out of Scope

- Import from file (CSV upload)
- Pasting the `weighed_by` field
- Undo/revert after paste (browser refresh serves as undo)
- Any backend changes
