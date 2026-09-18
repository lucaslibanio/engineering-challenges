import json
import pathlib
import pymupdf
import difflib

def load_ocr_pages(ocr_dir: str) -> list[dict]:
    ocr_path = pathlib.Path(ocr_dir)
    pages = []

    for json_file in sorted(ocr_path.glob("page_*.json")):
        with open(json_file, "r", encoding="utf-8") as f:
            page_data = json.load(f)
            pages.append(page_data)


    # Here I noticed that the pages where in "alfabetical order", so page_0015 came before page_002, for example
    # This way I sort it by the JSON field
    pages.sort(key = lambda p: p.get("page", 0))
    return pages

def get_page_size_at_300dpi(pdf_path: str, page_num: int) -> tuple[float, float]:
    doc = pymupdf.open(pdf_path)
    page = doc[page_num - 1]
    rect = page.rect
    doc.close()

    width_px = rect.width * 300 / 72
    height_px = rect.height * 300 / 72
    return width_px, height_px

def polygon_to_bbox_normalized(polygon: list, page_width_px: float, page_height_px: float) -> list[float]:
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]

    x0 = min(xs) / page_width_px
    y0 = min(ys) / page_height_px
    x1 = max(xs) / page_width_px
    y1 = max(ys) / page_height_px
    
    # just a safeguard
    x0 = max(0.0, min(1.0, x0))
    y0 = max(0.0, min(1.0, y0))
    x1 = max(0.0, min(1.0, x1))
    y1 = max(0.0, min(1.0, y1))
    
    return [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)]

def search_text_exact(ocr_lines: list[dict], query: str) -> list[dict]:
    query_lower = query.lower()
    results = []
    for line in ocr_lines:
        if query_lower in line["text"].lower():
            results.append(line)

    return results

def search_text_fuzzy(ocr_lines: list[dict], query: str, threshold: float = 0.6) -> list[dict]:
    query_lower = query.lower()
    results = []
    for line in ocr_lines:
        text_lower = line["text"].lower()
        if len(text_lower) >= len(query_lower):
            for i in range(len(text_lower) - len(query_lower) + 1):
                window = text_lower[i:i + len(query_lower)]
                ratio = difflib.SequenceMatcher(None, query_lower, window).ratio()
                if ratio >= threshold:
                    results.append({"line": line, "score": ratio})
                    break  # it doesnt need to keep running if i found it in this line
    
    # best match first
    results.sort(key=lambda r: r["score"], reverse=True)
    return results

if __name__ == "__main__":
    # testing config, eventually will turn into args
    SIREN = "445070311"
    DOC_ID = "63e2481c916269756a09542b"
    PDF_PATH = f"data/{SIREN}/bilans/pdf/bilan_2022-02-14_{DOC_ID}.pdf"
    OCR_DIR = f"data/{SIREN}/bilans/ocr/{DOC_ID}"

    # load all ocr pages
    pages = load_ocr_pages(OCR_DIR)
    print(f"The document has {len(pages)} pages of OCR\n")

    #for each page, shows quantity of lines and searches a snippet of text
    QUERY = "chiffre d'affaires"

    print(f"Query used: {QUERY}\n")

    for page_data in pages:
        page_num = page_data["page"]
        ocr_lines = page_data.get("ocr", [])

        matches = search_text_exact(ocr_lines, QUERY)

        if matches:
            w_px, h_px = get_page_size_at_300dpi(PDF_PATH, page_num)

            for match in matches:
                bbox = polygon_to_bbox_normalized(match["polygon"], w_px, h_px)
                print("Exact match")
                print(f"  Page {page_num}:")
                print(f"  Text: {match['text']}")
                print(f"  Score OCR: {match['score']}")
                print(f"  BBox normalized: {bbox}\n")

    for page_data in pages:
        page_num = page_data["page"]
        ocr_lines = page_data.get("ocr", [])
        
        fuzzy_matches = search_text_fuzzy(ocr_lines, QUERY, threshold=0.7)
        
        if fuzzy_matches:
            w_px, h_px = get_page_size_at_300dpi(PDF_PATH, page_num)
            print("Fuzzy match")
            print(f"Page {page_num}:")
            for fm in fuzzy_matches[:3]:  # top 3
                line = fm["line"]
                bbox = polygon_to_bbox_normalized(line["polygon"], w_px, h_px)
                print(f"  [{fm['score']:.2f}] {line['text']}")
                print(f"         bbox: {bbox}")





