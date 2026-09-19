# Bilan Challenge — Financial Field Extraction

Pipeline that extracts financial fields from French annual filings (bilans), with grounded bounding boxes and unit detection.

## How to run

```bash
git clone https://github.com/lucaslibanio/engineering-challenges.git
cd engineering-challenges

python3 -m venv .venv
source .venv/bin/activate
pip install pymupdf pillow

python3 run_pipeline.py
```

## What the pipeline does

1. **Loads OCR** from the provided JSON files (one per page), merging horizontally adjacent text fragments into logical lines. For numeric fragments specifically, the merge uses a wider tolerance, since digits in dense forms are often split across multiple OCR bounding boxes — for example, "1 987 385" arriving as three separate boxes ("1", "987", "385"). Without this, each fragment would be counted as a separate column, breaking column selection.
2. **Detects the unit** (EUR vs kEUR) by scanning for declaration phrases like "Les montants sont indiqués en K€", with accent-tolerant patterns since OCR drops French accents inconsistently.
3. **Maps each page to a financial section** (Bilan Actif, Bilan Passif, Compte de Résultat) by looking for short header lines — this prevents matching field labels that appear in narrative/prose pages.
4. **Extracts each field** by searching for its label in the OCR of the relevant section. Numeric cells on the same row are grouped into logical columns (fragments within 80px are treated as parts of the same number; gaps >80px mark column boundaries). The pipeline then selects the correct column by counting from the right.

## Results

- **Fields implemented:** 7 of 12
  - 4 reliable: `BS_CAPITAL_EQUITY_FRGAAP`, `PL_EXT_SERVICES_COSTS_FRGAAP`, `BS_TOTAL_ASSETS_FRGAAP`, `PL_REVENUE_FRGAAP`
  - 3 with caveats: `PL_PERSONNEL_COSTS_FRGAAP`, `BS_TOTAL_EQUITY_FRGAAP`, `PL_DEPRECIATION_AMORTIZATION_FRGAAP`
- **Coverage:** 62 / 105 field-document pairs found (59%)
- **Time:** ~6.5 seconds total, 0.016s per page
- **Cost:** €0.00 per page (no API calls)

### Fields with caveats

- **PL_REVENUE_FRGAAP**: reliable after column-selection fixes, but may pick France-only instead of the consolidated total on documents where Export is in a separate column with a wide gap.
- **PL_PERSONNEL_COSTS_FRGAAP**: works when the document has "TOTAL charges de personnel" as a single line. Returns NOT FOUND when the form separates it into "Salaires et traitements" + "Charges sociales" with only a generic "Total" underneath — the pipeline doesn't yet support section-scoped total detection.
- **BS_TOTAL_EQUITY_FRGAAP**: works when labeled "TOTAL situation nette" or "TOTAL capitaux propres". Returns NOT FOUND when the label is just "TOTAL (I)" or "Total" within the equity section.
- **PL_DEPRECIATION_AMORTIZATION_FRGAAP**: inconsistent across companies. Sometimes picks a sub-total (amortization on fixed assets only) instead of the full total including provisions on current assets.

## The trade-off

I chose a **rule-based approach on the provided OCR** rather than calling a vision model or running my own OCR. This gives:

- **Speed:** ~0.016s/page (vs seconds per page with a vision API)
- **Cost:** €0 (vs ~€0.01-0.05/page with Claude/GPT-4V)
- **Accuracy:** good for well-structured tabular pages, but struggles with label variation across companies. It is worth noting that some texts and labels are virtually irretrievable, since the quality of the scan does not allow the numbers to be recognized. Therefore, even LVMs would have difficulties with some of the fields.

**With more time**, I would:
- Add a fallback layer: when OCR confidence is low or a field is not found, render the page as an image and send it to Claude or another model with a structured prompt asking for the specific field value. This would be easy to implement (only needing a prompt attribute for each FIELDS element) and would improve coverage significantly at ~€0.01/page.
- Build a more flexible label-matching system: currently, each field has a fixed list of query strings. A better approach would detect section headers (e.g., "CHARGES DE PERSONNEL") and then look for "TOTAL" lines within that section, rather than relying on the full label appearing in a single OCR line.
- Cross-validate fields across years: each filing restates N-1 figures, so the current year's values should match the following filing's N-1 column.

## What I cut, and why

### Fields not implemented (3 of 12)

- **PL_FINANCIAL_RESULTS_FRGAAP**: "Resultat financier" appears on the second page of the Compte de Resultat, which some documents don't map to the `compte_resultat` section reliably. Cut for time.
- **PL_INCOME_TAX_FRGAAP**: same section-mapping issue as financial results.
- **BS_CASH_CURRENT_ASSET_FRGAAP**: "Disponibilites" is too close to "DISPONIBILITES ET DIVERS" (a subtotal), causing the pipeline to pick the wrong value. Needs more specific label targeting.

### Fields not attempted (2 of 12)

- **PL_COGS_FRGAAP**: cost of goods sold is not printed as a single line — it must be computed from "Achats de marchandises" + "Variation de stock de marchandises" + "Achats de matieres premieres" + "Variation de stock de matieres premieres". This requires multi-line extraction and arithmetic, which the current pipeline doesn't support.
- **META_AVG_WORKFORCE_FRGAAP**: average workforce is a non-monetary field (unit: "count") that appears in a different section (2058-C or "Autres informations"). It needs separate handling for both location and unit.

### Known issues

- **fiscal_year_end is null**: the exercise closing date (e.g., "Exercice clos le 30/06/2020") is printed in the header of most pages and could be extracted with a simple regex on the OCR. It was deprioritized since it does not affect the financial field extraction and is not a required field in the schema.
- **Label variation across companies**: the main source of NOT FOUND results. Some companies print "TOTAL charges de personnel" as a single line (which the pipeline finds), while others separate it into "Salaires et traitements" and "Charges sociales" under a "CHARGES DE PERSONNEL" header, with only a generic "Total" line for the sum. The pipeline doesn't yet support detecting these section-scoped totals — it would need to find the section header first, then locate the "Total" line within that section and sum accordingly.
- **Generic "TOTAL" labels**: similarly, BS_TOTAL_EQUITY_FRGAAP is sometimes labeled "TOTAL situation nette" or "TOTAL capitaux propres" (which the pipeline finds), but in other companies it appears as just "TOTAL (I)" or simply "Total" within the equity section. The current approach of matching full labels misses these cases.
- **Numeric bbox fragmentation in dense forms**: the OCR splits individual numbers across multiple bounding boxes in tightly-spaced liasse fiscale scans. The pipeline handles this by grouping numeric fragments within 80px into a single logical number before column selection. This works for most cases, but the 80px threshold is a heuristic.
- **Unit detection is document-wide**: the pipeline detects EUR vs kEUR once per document, but at least one company (328024377) uses EUR as the default with kEUR only in specific sections. A per-section unit detection would be more accurate.

## How I used AI

I used Claude Free Plan (via claude.ai) throughout the project as a pair programmer:

- **Code generation**: Claude wrote specific parts of the code, mainly tied to documentation of libraries that I did not know (and did not have time to learn), arithmetic related to the PDFs resolution, fuzzy algorithm, regex, and time-consuming mechanical tasks like rewriting fields definitions or JSON mapping. I reviewed, tested, and modified each change. Also, AI helped me correct and better develop my observations in this README.
Notably, AI made also the merging bug fixes, since I was running out of time. Therefore, I focused only in debugging this part.
- **Debugging**: In the interest of time, Claude wrote the tests for each iteration.
- **Where AI was wrong**: Claude's initial `filter_table_pages` approach (filtering entire pages as "narrative" or "table") was too aggressive and dropped valid pages. I replaced it with section-based page mapping, which is more granular. The initial field queries also matched narrative mentions instead of table labels, which required several rounds of refinement. Claude also initially suggested a simple "closest number to the right" strategy for value extraction, which failed on multi-column forms — this had to be replaced with a column-grouping approach that clusters numeric bbox fragments before selecting.

## My Difficulties

My main difficulty was, as expected, the time. I had a hard time trying to make quality code while also doing it quickly. Probably if I had Claude Pro or Max I could have done more.

Another problem was the testing. I estimated that if I took the time to do an "answer sheet" for each of the 15 documents, I would spend more than 1h, and that would not even be relevant if I didn't succeed to make the pipeline itself. Therefore, I took a few documents of 3 different corporations and did my testing and development based on them — which probably will reflect in the precision of results.json in the other values.

Moreover, I should have been more careful with the initial inspection of the documents, because I found out way too late basic problems that did not exist in the PDFs Ichose as base.

## Files

- `bilan_core.py` — core logic: OCR loading, bbox conversion, number parsing, text search, unit detection, numeric fragment grouping
- `extract_fields.py` — field definitions and extraction logic with section-based page mapping
- `run_pipeline.py` — processes all 15 documents and generates results.json
- `results.json` — extraction output matching the schema
- `.env.example` — environment variables (none needed for this pipeline)

## Time Dedicated to the Project
~ 10h until ~ 16h
~ 21h30 until ~ 23h30
Approximately 8h of work

## Screen recording
[https://drive.google.com/file/d/1yKhai1J-WkNbb3zj2BgoTlseLhemUm2E/view?usp=sharing]
