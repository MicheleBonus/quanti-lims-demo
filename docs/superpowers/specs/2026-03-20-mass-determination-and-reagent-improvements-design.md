# Design: Mass Determination Analysis Type & Reagent Requirements Improvements

**Date:** 2026-03-20
**Status:** Approved
**Project:** quanti-lims (Quantitatives Analytisch-Chemisches Praktikum, HHU Düsseldorf)

---

## Background

Two independent improvement areas were identified:

1. **Mass determination analysis type** — The Glycerol determination performed in the practical course is a pure mass determination: the TA weighs a certain amount of Glycerol, the student performs the titration procedure and announces a calculated mass (mg). Currently the system has no mode for this — it only supports percentage assays (`assay_mass_based`) and titrant standardization (`titrant_standardization`). There is no blend (Verschnitt); the sample is pure substance. The procedure does involve aliquoting (20 mL from a 100 mL volumetric flask).

2. **Reagent requirements (Reagenzienbedarf)** — Two problems:
   - The safety factor is hardcoded at 1.2 and cannot be adjusted per semester/batch.
   - The base count `n` assumes all k determinations per sample, which is overly pessimistic — only first analyses (Erstanalysen) are guaranteed; B and C analyses are only needed for students who fail.
   - The reagent requirements report mixes orderable simple reagents and lab-prepared composite reagents without distinguishing them, and the base substances (Grundsubstanzen) of composite reagents are missing entirely — making the list unusable for ordering and preparation planning.

---

## Feature 1: Mass Determination Analysis Type (`mass_determination`)

### Overview

A new `calculation_mode` value `"mass_determination"` is introduced alongside the existing `"assay_mass_based"` and `"titrant_standardization"` modes. It follows the same architectural patterns as the existing modes.

**Workflow:**
1. TA weighs pure substance (e.g., Glycerol) into a sample container — a single mass within a defined min/max range.
2. Student dissolves in volumetric flask, performs the titration procedure (optionally with aliquoting), calculates the mass.
3. Student announces the calculated mass (mg) to the TA.
4. TA enters the announced mass into the system.
5. System validates: announced mass must be within ±X% of the actual weighed-in mass (using `g_ab_min_pct` / `g_ab_max_pct`).

Aliquoting is fully supported (as in the Glycerol protocol: 20 mL from 100 mL flask). Non-aliquoting is also supported.

### Data Model Changes

#### `Analysis` model
- New `calculation_mode` enum value: `"mass_determination"`
- New field: `m_einwaage_min_mg` (Float, nullable) — minimum weighing mass for the TA (Mindesteinwaage)
- New field: `m_einwaage_max_mg` (Float, nullable) — maximum weighing mass for the TA (Maximaleinwaage)
- Existing fields `g_ab_min_pct` / `g_ab_max_pct` serve as relative tolerance bounds for the announced result
- Existing field `e_ab_g` is **not repurposed** — it retains its meaning as the pharmacopoeia entry weight for `assay_mass_based` mode and is hidden/unused in `mass_determination` mode

#### `SampleBatch` model (for `mass_determination` mode)
- `gehalt_min_pct`, `blend_description`, `mortar_loss_factor` — not used; hidden in UI for this mode (nullable, no validation enforced)
- `target_m_s_min_g`, `target_m_ges_g` — not applicable; replaced by `m_einwaage_min_mg` / `m_einwaage_max_mg` guidance from Analysis

#### `Sample` model (for `mass_determination` mode)
- Only `m_s_actual_g` is used (the actual Glycerol mass weighed by the TA)
- `m_ges_actual_g` is not used and hidden in UI

### UI Changes

#### Analysis form (`analysis_form.html`)
- When `calculation_mode = "mass_determination"` is selected:
  - Show `m_einwaage_min_mg` and `m_einwaage_max_mg` fields
  - Hide `e_ab_g` field (Arzneibuch-Einwaage)
  - Keep `g_ab_min_pct` / `g_ab_max_pct` (tolerance for the announced mass)

#### Batch form (`batch_form.html`)
- When mode is `mass_determination`:
  - Hide blend-related fields (`gehalt_min_pct`, `blend_description`, `mortar_loss_factor`)
  - Replace live target mass calculation JS with a simple display of the Einwaage range from Analysis: "Einwaagen zwischen X mg und Y mg"
  - Live validation: entered `m_s_actual_g` value shown green/red based on whether it falls within [m_einwaage_min_mg, m_einwaage_max_mg]

#### Sample entry form
- When mode is `mass_determination`: show only `m_s_actual_g` (hide `m_ges_actual_g`)

#### Result entry
- TA enters announced mass (mg)
- System shows pass/fail based on: `m_announced` within [(1 - g_ab_min_pct/100) × m_actual, (1 + g_ab_max_pct/100) × m_actual]

### Method configuration
- No new fields on `Method` required
- `aliquot_enabled`, `v_solution_ml`, `v_aliquot_ml` work exactly as for other modes
- `method_type` can be set freely (e.g., `"back"` for the Glycerol back-titration)

---

## Feature 2: Reagent Requirements Improvements

### 2a: Configurable Safety Factor per SampleBatch

**Problem:** Safety factor is hardcoded at 1.2 in two places in `app.py`.

**Solution:** Add `safety_factor` field to `SampleBatch` (Float, default 1.2). Both the reagent report route and the export route read `batch.safety_factor` instead of the literal `1.2`.

The field is editable in the SampleBatch form with a sensible default.

### 2b: Base Count for Grundbedarf (Erstanalysen only)

**Problem:** Current formula uses `k = analysis.k_determinations` (e.g., 3 for A/B/C), meaning reagents are planned for all possible determinations of all samples — which is overly pessimistic since B and C analyses only occur for students who fail A.

**Solution:** Fix `k = 1` in the reagent requirements calculation (Grundbedarf = only first analyses). The formula becomes:

```
Grundbedarf = n × (1 × amount_per_det + b × amount_per_blind) × safety_factor
```

Where:
- `n` = `batch.total_samples_prepared`
- `b` = `method.b_blind_determinations` if `method.blind_required` else 0
- `safety_factor` = `batch.safety_factor` (default 1.2)

The existing `k_determinations` field on Analysis is not changed; it continues to be used for expected volume calculations and other parts of the system.

The reagent report UI makes the formula explicit: `n × (1 × V_Einzel + b × V_Blind) × Sicherheitsfaktor` with a note that this covers Erstanalysen only.

### 2c: Reagent Requirements Report Redesign

**Problem:** Composite reagents (lab-prepared solutions) and their base substances (orderable from ZCL) are not distinguished. Base substances are missing from the list entirely.

**Solution:** Three-layer presentation:

#### Main reagent table (existing, enhanced)
- Composite reagents are shown with an expand/collapse toggle
- Expanded view shows: components list with calculated amounts for the required total volume
- Amounts are scaled from the reagent's bill-of-materials (ReagentComponent) to the total required volume

#### Printable Bestellliste (new)
- Route: `/reports/reagents/order-list` (or export button on the existing report page)
- Content: only base/simple reagents (where `is_composite = False`), aggregated across all batches of the semester
- Each entry shows: substance name, CAS number, total amount needed, and a note indicating which composite reagent(s) it feeds into (`→ für NaOH-Lösung (0,1 mol/L)`)
- Directly orderable substances (used as-is in procedures) are also listed
- Formatted for printing (clean table, no interactive elements)

#### Printable Herstellliste per Block (new)
- Route: `/reports/reagents/prep-list` (or export button)
- Grouped by Block
- Each composite reagent shown as a card with:
  - Name and total volume to prepare
  - Component list with calculated quantities
  - Optional preparation instruction (from reagent notes or a new `prep_instruction` field)
- Formatted for printing

### Database Migration
- `ALTER TABLE analysis ADD COLUMN m_einwaage_min_mg REAL`
- `ALTER TABLE analysis ADD COLUMN m_einwaage_max_mg REAL`
- `ALTER TABLE sample_batch ADD COLUMN safety_factor REAL DEFAULT 1.2`
- Extend `calculation_mode` enum to include `"mass_determination"`

---

## Out of Scope

- No changes to the `titrant_standardization` mode
- No changes to how `k_determinations` is used outside reagent requirements
- No new reagent management features (BOM editing, etc.)
- No changes to how the student-facing result display works (TAs only)

---

## Open Questions

None — all design decisions resolved during brainstorming.
