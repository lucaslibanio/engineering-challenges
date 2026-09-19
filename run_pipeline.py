import json
import time
from extract_fields import process_document, FIELDS

ALL_DOCUMENTS = [
    ("820561470", "6493e4372f502414800f8164", "2023-06-05"),
    ("820561470", "6543d3fd08093cdace058668", "2023-06-13"),
    ("820561470", "67458f18cea78a70070fa226", "2024-01-15"),

    ("328024377", "63e8ebbb54febda17c19ee7c", "2020-12-24"),
    ("328024377", "63e8ebbb54febda17c19ee7d", "2021-12-17"),
    ("328024377", "63e8ebbb54febda17c19ee7e", "2022-12-13"),

    ("445070311", "63e2481c916269756a09542b", "2022-02-14"),
    ("445070311", "65a4095d5fd178b16b09b860", "2023-11-21"),
    ("445070311", "6860f28ca0138eae340c7453", "2025-05-15"),

    ("504304205", "63e13943526e1f30cd100db5", "2017-05-31"),
    ("504304205", "63e13943526e1f30cd100db6", "2018-10-24"),
    ("504304205", "66cd893cedec9b09d50191e8", "2024-08-06"),

    ("401009741", "63e881158be6eb9f9d1ff975", "2022-11-30"),
    ("401009741", "65784e5da67d84faf4042736", "2023-11-20"),
    ("401009741", "68f0a715f28d8aaf48046416", "2025-10-03"),
]


def run_all():
    all_results = []
    total_pages = 0
    total_time = 0
    total_fields_found = 0
    total_fields_possible = 0

    for siren, doc_id, deposit_date in ALL_DOCUMENTS:
        print(f"\n{'='*60}")
        print(f"  SIREN {siren} — {deposit_date}")
        print(f"{'='*60}\n")

        start = time.time()
        result = process_document(siren, doc_id, deposit_date)
        elapsed = time.time() - start

        from bilan_core import load_ocr_pages
        pages = load_ocr_pages(f"data/{siren}/bilans/ocr/{doc_id}")
        n_pages = len(pages)

        total_pages += n_pages
        total_time += elapsed
        total_fields_found += len(result["fields"])
        total_fields_possible += len(FIELDS)

        result["run"] = {
            "seconds": round(elapsed, 2),
            "pages": n_pages,
            "seconds_per_page": round(elapsed / max(n_pages, 1), 3),
        }

        all_results.append(result)

        print(f"\n  Found {len(result['fields'])} / {len(FIELDS)} fields")
        print(f"  Time: {elapsed:.2f}s ({n_pages} pages, {elapsed/max(n_pages,1):.3f}s/page)")

    return all_results, total_pages, total_time, total_fields_found, total_fields_possible


def build_results_json(all_results: list) -> dict:
    documents = []
    for result in all_results:
        doc_entry = {
            "pdf": result["pdf"],
            "siren": result["siren"],
            "fiscal_year_end": result.get("fiscal_year_end"),
            "fields": [],
            "run": result.get("run", {}),
        }

        for field in result["fields"]:
            field_entry = {
                "field_key": field["field_key"],
                "value": field["value"],
                "unit": field.get("unit", "EUR"),
                "page": field["page"],
                "bbox": field["bbox"],
            }
            # Optional fields
            if "snippet" in field:
                field_entry["snippet"] = field["snippet"]
            if "label_matched" in field:
                field_entry["label_matched"] = field["label_matched"]

            doc_entry["fields"].append(field_entry)

        documents.append(doc_entry)

    return {"documents": documents}


if __name__ == "__main__":
    print("=" * 60)
    print("  BILAN EXTRACTION PIPELINE")
    print(f"  {len(ALL_DOCUMENTS)} documents, {len(FIELDS)} fields each")
    print("=" * 60)

    all_results, total_pages, total_time, found, possible = run_all()

    results_json = build_results_json(all_results)

    results_json["run"] = {
        "total_seconds": round(total_time, 2),
        "total_pages": total_pages,
        "seconds_per_page": round(total_time / max(total_pages, 1), 3),
        "cost_eur_per_page": 0,  # still didnt implement it
        "model": "none — rule-based extraction on provided OCR",
        "notes": "No external API keys needed. Uses provided OCR + rule-based matching.",
    }

    with open("results.json", "w", encoding="utf-8") as f:
        json.dump(results_json, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"  Documents processed: {len(ALL_DOCUMENTS)}")
    print(f"  Total pages:         {total_pages}")
    print(f"  Total time:          {total_time:.2f}s")
    print(f"  Avg time/page:       {total_time/max(total_pages,1):.3f}s")
    print(f"  Fields found:        {found} / {possible} ({100*found/max(possible,1):.0f}%)")
    print(f"  Cost per page:       €0.00 (no API calls)")
    print(f"\n  results.json saved to ./results.json")
    print("=" * 60)
