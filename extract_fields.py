import json
from bilan_core import (
    load_ocr_pages, get_page_size_at_300dpi, polygon_to_bbox_normalized,
    search_text_exact, search_text_fuzzy, find_value_near_label,
    detect_unit_ker
)

FIELDS = [
    {
        "field_key": "PL_REVENUE_FRGAAP",
        "queries": ["chiffre d'affaires", "chiffre d affaires", "montant net du chiffre"],
        "unit_type": "monetary",
    },
    {
        "field_key": "PL_PERSONNEL_COSTS_FRGAAP",
        "queries": ["salaires et traitements", "salaires et traitement"],
        "unit_type": "monetary",
        "note": "need to add charges sociales too — this is wages only"
    },
    {
        "field_key": "PL_EXT_SERVICES_COSTS_FRGAAP",
        "queries": ["autres achats et charges externes", "autres achats & charges externes"],
        "unit_type": "monetary",
    },
    {
        "field_key": "PL_DEPRECIATION_AMORTIZATION_FRGAAP",
        "queries": ["dotations d'exploitation", "dotations d exploitation",
                     "amortissements et provisions", "amortissements provisions"],
        "unit_type": "monetary",
    },
    {
        "field_key": "PL_FINANCIAL_RESULTS_FRGAAP",
        "queries": ["résultat financier", "resultat financier"],
        "unit_type": "monetary",
    },
    {
        "field_key": "PL_INCOME_TAX_FRGAAP",
        "queries": ["impôts sur les bénéfices", "impots sur les benefices",
                     "impôt sur les bénéfices", "impot sur les benefices"],
        "unit_type": "monetary",
    },
    {
        "field_key": "BS_TOTAL_ASSETS_FRGAAP",
        "queries": ["total général", "total general"],
        "unit_type": "monetary",
        "note": "appears on both actif and passif — we want the one on the ACTIF page"
    },
    {
        "field_key": "BS_TOTAL_EQUITY_FRGAAP",
        "queries": ["total des capitaux propres", "total capitaux propres"],
        "unit_type": "monetary",
    },
    {
        "field_key": "BS_CAPITAL_EQUITY_FRGAAP",
        "queries": ["capital social", "capital souscrit"],
        "unit_type": "monetary",
    },
    {
        "field_key": "BS_CASH_CURRENT_ASSET_FRGAAP",
        "queries": ["disponibilités", "disponibilites", "disponibilite"],
        "unit_type": "monetary",
    },
]

def extract_one_field (field_desc: dict, pages: list, pdf_path: str) -> dict | None:
    for query in field_desc["queries"]:
        for page_data in pages:
            page_num = page_data["page"]
            ocr_lines = page_data.get("ocr", [])

            matches = search_text_exact(ocr_lines, query)

            if not matches:
                fuzzy = search_text_fuzzy(ocr_lines, query, threshold=0.75)
                if fuzzy:
                    # only best match
                    matches = [fuzzy[0]["line"]]

                    for label_line in matches:
                        result = find_value_near_label(ocr_lines, label_line, ocr_lines)
                        if result and result["value"] is not None:
                            w_px, h_px = get_page_size_at_300dpi(pdf_path, page_num)
                            bbox = polygon_to_bbox_normalized(
                                result["source_line"]["polygon"], w_px, h_px
                            )
                            return {
                                "field_key": field_desc["field_key"],
                                "value": result["value"],
                                "page": page_num,
                                "bbox": bbox,
                                "snippet": result["source_line"]["text"],
                                "label_matched": label_line["text"]
                            }

    return None

def process_document (siren: srt, doc_id: str, deposit_date: str) -> dict:
    pdf_path = f"data/{siren}/bilans/pdf/bilan_{deposit_date}_{doc_id}.pdf"
    ocr_dir = f"data/{siren}/bilans/ocr/{doc_id}"

    pages = load_ocr_pages(ocr_dir)
    unit = detect_unit_ker(pages)

    extracted_fields = []
    for field_def in FIELDS:
        result = extract_one_field(field_def, pages, pdf_path)
        if result:
            field_unit = unit  # EUR or kEUR from document detection
            result["unit"] = field_unit
            extracted_fields.append(result)
            print(f"  ✓ {result['field_key']}: {result['value']} {field_unit}")
            print(f"    page {result['page']}, matched: '{result['label_matched']}'")
        else:
            print(f"  ✗ {field_def['field_key']}: NOT FOUND")

    return {
        "pdf": pdf_path,
        "siren": siren,
        "fiscal_year_end": None,  # TODO: extract from document
        "fields": extracted_fields,
    }


if __name__ == "__main__":
    print("=== Extracting from 445070311 (2022-02-14) ===\n")
    result = process_document(
        siren="445070311",
        doc_id="63e2481c916269756a09542b",
        deposit_date="2022-02-14"
    )
    print(f"\nFound {len(result['fields'])} / {len(FIELDS)} fields")
