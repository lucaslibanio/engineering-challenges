# Bilan Challenge — Financial Field Extraction

Pipeline that extracts financial fields from French annual filings (bilans), with grounded bounding boxes and unit detection.

## How to run

```bash
git clone https://github.com/SEU_USUARIO/engineering-challenges.git
cd engineering-challenges

python3 -m venv .venv
source .venv/bin/activate
pip install pymupdf pillow

python3 run_pipeline.py
```

No API keys needed — this is a rule-based pipeline that runs entirely on the provided OCR.

## What the pipeline does

1. **Loads OCR** from the provided JSON files (one per page), merging horizontally adjacent text fragments into logical lines.
2. **Detects the unit** (EUR vs kEUR) by scanning for declaration phrases like "Les montants sont indiqués en K€", with accent-tolerant patterns since OCR drops French accents inconsistently.
3. **Maps each page to a financial section** (Bilan Actif, Bilan Passif, Compte de Résultat) by looking for short header lines — this prevents matching field labels that appear in narrative/prose pages.
4. **Extracts each field** by searching for its label in the OCR of the relevant section, finding the nearest numeric value to the right of the label, and converting the OCR bounding box from 300-dpi pixels to normalized 0–1 coordinates.

## Results (provisório)

- **Fields implemented:** 6 of 12 (see "What I cut" below)
- **Coverage:** 51 / 90 field-document pairs found (57%)
- **Time:** ~3.3 seconds total, 0.008s per page
- **Cost:** €0.00 per page (no API calls)

## The trade-off

I chose a **rule-based approach on the provided OCR** rather than calling a vision model or running my own OCR. This gives:

- **Speed:** ~0.008s/page (vs seconds per page with a vision API)
- **Cost:** €0 (vs ~€0.01–0.05/page with Claude/GPT-4V)
- **Accuracy:** good for well-structured tabular pages, but struggles with narrative text contamination and multi-columns. It is worth to note that some texts and labels are virtually irretrievables, since the quality of the scan does not allow the numbers to be recognized. Therefore, even LVMs would have difficulties in some of the fields.

The main accuracy limitation is **column selection**: when a label has multiple numeric values to its right (Brut/Amortissements/Net columns on Bilan Actif, or France/Export/Total on the Compte de Résultat), the pipeline picks the closest number to the right of the label, which is not always the correct column. A vision model or layout-aware table parser would handle this better. The logic is easy enough to implement, but not in the 8h time window.

**With more time**, I would:
- Add a fallback layer: when OCR confidence is low or a field is not found, render the page as an image and send it to Claude or another model with a structured prompt asking for the specific field value. This would improve coverage significantly at ~€0.01/page.
- Implement column disambiguation using the header row (detecting "Net (N)" vs "Net (N-1)" vs "Brut" column positions).
- Cross-validate fields across years: each filing restates N-1 figures, so the current year's values should match the following filing's N-1 column.

## What I cut, and why

### Fields not implemented (4 of 12)

- **PL_DEPRECIATION_AMORTIZATION_FRGAAP**: the label "TOTAL dotations d'exploitation" exists in most documents but the query needs refinement across all 5 companies. Cut for time.
- **PL_FINANCIAL_RESULTS_FRGAAP**: "Résultat financier" appears on the second page of the Compte de Résultat, which some documents don't map to the `compte_resultat` section reliably. Cut for time.
- **PL_INCOME_TAX_FRGAAP**: same section-mapping issue as financial results.
- **BS_CASH_CURRENT_ASSET_FRGAAP**: "Disponibilités" is too close to "DISPONIBILITÉS ET DIVERS" (a subtotal), causing the pipeline to pick the wrong value. Needs more specific label targeting.

### Fields not attempted (2 of 12)

- **PL_COGS_FRGAAP**: cost of goods sold is not printed as a single line — it must be computed from "Achats de marchandises" + "Variation de stock de marchandises" + "Achats de matières premières" + "Variation de stock de matières premières". This requires multi-line extraction and arithmetic, which the current pipeline doesn't support.
- **META_AVG_WORKFORCE_FRGAAP**: average workforce is a non-monetary field (unit: "count") that appears in a different section (2058-C or "Autres informations"). It needs separate handling for both location and unit.

### Known issues

- **Column disambiguation**: BS_TOTAL_ASSETS picks the Brut column instead of Net (N) on Bilan Actif pages with multiple columns. PL_REVENUE picks France-only instead of the consolidated total on some documents.
- **Unit detection is document-wide**: the pipeline detects EUR vs kEUR once per document, but at least one company (328024377) uses EUR as the default with kEUR only in specific sections. A per-section unit detection would be more accurate.
- **merge_horizontal_lines** occasionally fuses adjacent numbers, producing absurdly large values (e.g., 1.2 billion for personnel costs on one document).

## How I used AI

I used Claude Free Plan (via claude.ai) throughout the project as a pair programmer:

- **Code generation**: Claude wrote specific parts of the code, mainly tied to documentation of libraries that I did not know (and did not have time to learn), arithmetic related to the PDFs resolution, fuzzy algorithm, regex, and time-consuming mechanical tasks like rewriting fields definitions or JSON mapping. I reviewed, tested, and modified each change.
- **Debugging**: In the interest of time, Claude wrote the tests for each iteration.
- **Where AI was wrong**: Claude's initial `filter_table_pages` approach (filtering entire pages as "narrative" or "table") was too aggressive and dropped valid pages. I replaced it with section-based page mapping, which is more granular. The initial field queries also matched narrative mentions instead of table labels, which required several rounds of refinement.

## My Difficulties

My main difficulty was, like expected, the time. I had a hard time trying to make quality code while also doing it quickly. Probably if I had Claude Pro or Max I could have done more. 

Another problem was the testing. I estimated that if I took the time to do an "answer sheet" for each of the 15 documents, I would spend more than 1h, and that would not even be relevant if I didn't suceed to make the pipeline itself. Therefore, I took a few documents of 3 different corporations and did my testing and development based on them -- which probably will reflect in the precision of results.json.

## Files

- `bilan_core.py` — core logic: OCR loading, bbox conversion, number parsing, text search, unit detection
- `extract_fields.py` — field definitions and extraction logic with section-based page mapping
- `run_pipeline.py` — processes all 15 documents and generates results.json
- `results.json` — extraction output matching the schema
- `.env.example` — environment variables (none needed for this pipeline)

## Screen recording
[falta o link]
