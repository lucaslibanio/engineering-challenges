import json
import re
import unicodedata
from bilan_core import (
    detect_unit_ker,
    find_value_near_label,
    get_page_size_at_300dpi,
    load_ocr_pages,
    polygon_to_bbox_normalized,
    search_text_exact,
    search_text_fuzzy,
)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join([c for c in text if not unicodedata.combining(c)]).lower()


def detect_page_sections(pages: list[dict]) -> dict:
    section_anchors = {
        "bilan_actif": [
            "bilan actif",
            "actif immobilise",
            "total actif circulant",
            "total actif immobilise",
            "actif",                          
            "actif circulant",                
            "total general (i a vi)",         
            "immobilisations incorporelles",  
        ],
        # ...
        "bilan_passif": [
            "bilan passif",
            "situation nette",
            "dettes financieres",
        ],
        "compte_resultat": [
            "compte de resultat",
            "produits d'exploitation",
            "charges d'exploitation",
            "total des produits",
            "total des charges",
            "resultat d'exploitation",
            "benefice ou perte",
        ],
    }

    page_sections = {}
    for page_data in pages:
        page_num = page_data["page"]
        ocr_lines = page_data.get("ocr", [])

        sections = set()
        for line in ocr_lines:
            text = line.get("text", "")
            # Only consider short lines — headers, not prose
            if len(text) > 80:
                continue
            norm = normalize_text(text)
            for section, anchors in section_anchors.items():
                if any(anchor in norm for anchor in anchors):
                    sections.add(section)

        page_sections[page_num] = sections

    return page_sections

FIELDS = [
    {
        "field_key": "PL_REVENUE_FRGAAP",
        "queries": [
            "chiffres d'affaires nets",
            "chiffre d'affaires net",
        ],
        "section": "compte_resultat",
        "unit_type": "monetary",
        "column_index": 2
    },
    {
        "field_key": "PL_PERSONNEL_COSTS_FRGAAP",
        "queries": [
            "total charges de personnel",
        ],
        "section": "compte_resultat",
        "unit_type": "monetary",
    },
    {
        "field_key": "PL_EXT_SERVICES_COSTS_FRGAAP",
        "queries": [
            "autres achats et charges externes",
            "autres achats & charges externes",
        ],
        "section": "compte_resultat",
        "unit_type": "monetary",
    },
{
        "field_key": "BS_TOTAL_ASSETS_FRGAAP",
        "queries": [
            "total actif",
            "total général",
            "total général (I à VI)",
            "total general",
            "total general (I à VI)",
        ],
        "section": "bilan_actif",
        "unit_type": "monetary",
        "column_index": 2
    },
    {
        "field_key": "BS_TOTAL_EQUITY_FRGAAP",
        "queries": [
            "total situation nette",
            "total capitaux propres",
        ],
        "section": "bilan_passif",
        "unit_type": "monetary",
    },
    {
        "field_key": "BS_CAPITAL_EQUITY_FRGAAP",
        "queries": [
            "capital social ou individuel",
            "capital social",
        ],
        "section": "bilan_passif",
        "unit_type": "monetary",
    },
]

def extract_one_field(
    field_desc: dict, pages: list, pdf_path: str, page_sections: dict
) -> dict | None:
    target_section = field_desc.get("section")
    target_column = field_desc.get("column_index", 0) 

    for query in field_desc["queries"]:
        for page_data in pages:
            page_num = page_data["page"]

            if target_section and target_section not in page_sections.get(page_num, set()):
                continue

            ocr_lines = page_data.get("ocr", [])

            matches = search_text_exact(ocr_lines, query)
            if not matches:
                fuzzy = search_text_fuzzy(ocr_lines, query, threshold=0.80)
                if fuzzy:
                    matches = [fuzzy[0]["line"]]

            for label_line in matches:
                text_line = label_line["text"].strip()
                if re.match(r"^\d+\.\d+", text_line):
                    continue

                result = find_value_near_label(ocr_lines, label_line, ocr_lines, column_index=target_column) 
                
                if result and result["value"] is not None:
                    # ... o resto continua igual ...
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
                        "label_matched": label_line["text"],
                    }
    return None


def process_document(siren: str, doc_id: str, deposit_date: str) -> dict:
    pdf_path = f"data/{siren}/bilans/pdf/bilan_{deposit_date}_{doc_id}.pdf"
    ocr_dir = f"data/{siren}/bilans/ocr/{doc_id}"

    pages = load_ocr_pages(ocr_dir)
    unit = detect_unit_ker(pages)
    page_sections = detect_page_sections(pages)

    # Show which pages were mapped to which sections
    for page_num, sections in sorted(page_sections.items()):
        if sections:
            print(f"  Page {page_num}: {', '.join(sections)}")

    extracted_fields = []
    for field_def in FIELDS:
        result = extract_one_field(field_def, pages, pdf_path, page_sections)
        if result:
            result["unit"] = unit
            extracted_fields.append(result)
            print(f"  ✓ {result['field_key']}: {result['value']} {unit}")
            print(f"    page {result['page']}, matched: '{result['label_matched']}'")
        else:
            print(f"  ✗ {field_def['field_key']}: NOT FOUND")

    return {
        "pdf": pdf_path,
        "siren": siren,
        "fiscal_year_end": None,
        "fields": extracted_fields,
    }


if __name__ == "__main__":
    # testing
    docs = [
        ("445070311", "63e2481c916269756a09542b", "2022-02-14"),
        ("445070311", "65a4095d5fd178b16b09b860", "2023-11-21"),
        ("445070311", "6860f28ca0138eae340c7453", "2025-05-15"),
    ]

    for siren, doc_id, date in docs:
        print(f"\n=== Extracting from {siren} ({date}) ===\n")
        result = process_document(siren=siren, doc_id=doc_id, deposit_date=date)
        print(f"\nFound {len(result['fields'])} / {len(FIELDS)} fields")
        print("-" * 60)
