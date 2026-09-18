import json 
import pathlib
import pymupdf
import difflib
import re

def detect_unit_ker(pages: list[dict]) -> str:
    keur_patterns = [
        "montants sont indiqués en k",     
        "montants sont indiques en k",      # OCR drops accent
        "montants exprimés en milliers",
        "montants exprimes en milliers",    # OCR drops accent
        "montants en milliers",
        "exprimés en milliers",
        "exprimes en milliers",             # OCR drops accent
        "indiqués en milliers",
        "indiques en milliers",             # OCR drops accent
        "exprimés en k€",
        "exprimes en k€",                   # OCR drops accent
        "indiqués en k€",
        "indiques en k€",                   # OCR drops accent
        "réalisé en kilo",                 
        "realise en kilo",                  # OCR drops accent
        "en milliers d'euros",
        "en milliers d euros",
    ]

    for page_data in pages:
        for line in page_data.get("ocr", []):
            text_lower = line["text"].lower()
            for pattern in keur_patterns:
                if pattern in text_lower:
                    return "kEUR"
    
    return "EUR"

def parse_number(text: str):
    text = text.strip()

    # kinda slop but I found only these examples of "nothing"
    if not text or text.lower() in ("néant", "neant", "-", ""):
        return None

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        # removes first and last char
        text = text[1:-1].strip()
    if text.startswith("-"):
        negative = True
        # removes only first char
        text = text[1:].strip()

    text = text.replace(" ", "").replace(".", "")
    # decimal pattern point
    text = text.replace(",", ".")

    # ai made: removes every char that is not a digit or a ".", really a safeguard
    text = re.sub(r"[^\d.]", "", text)

    if not text:
        return None

    try:
        value = float(text)
        return -value if negative else value
    except ValueError:
        return None

def merge_horizontal_lines(ocr_lines: list[dict], max_x_gap: float = 35.0) -> list[dict]:
    if not ocr_lines:
        return []

    def get_geom(line):
        xs = [p[0] for p in line["polygon"]]
        ys = [p[1] for p in line["polygon"]]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        y_center = (y0 + y1) / 2.0
        height = max(y1 - y0, 1.0)
        return x0, x1, y0, y1, y_center, height

    sorted_lines = sorted(ocr_lines, key=lambda l: (get_geom(l)[4], get_geom(l)[0]))

    merged: list[dict] = []

    for line in sorted_lines:
        if not merged:
            merged.append(dict(line))
            continue

        prev = merged[-1]
        px0, px1, py0, py1, py_center, pheight = get_geom(prev)
        cx0, cx1, cy0, cy1, cy_center, cheight = get_geom(line)

        y_tol = max(pheight, cheight, 15.0) * 0.7
        same_line = abs(py_center - cy_center) <= y_tol

        x_gap = cx0 - px1

        if same_line and (-10 <= x_gap <= max_x_gap):
            merged_text = f"{prev['text']} {line['text']}"
            new_x0 = min(px0, cx0)
            new_y0 = min(py0, cy0)
            new_x1 = max(px1, cx1)
            new_y1 = max(py1, cy1)

            merged[-1] = {
                "text": merged_text,
                "polygon": [
                    [new_x0, new_y0],
                    [new_x1, new_y0],
                    [new_x1, new_y1],
                    [new_x0, new_y1],
                ],
            }
        else:
            merged.append(dict(line))

    return merged

def extract_number_from_line(text: str):

    pattern = r"[\d][\d\s\u00a0.,]*[\d]"
    matches = re.findall(pattern, text)

    if not matches:
        single = re.findall(r"\d+", text)
        if single:
            matches = single

    # returning the last number here is just a quick decision, i guess i would have to analyse more PDFs to find a pattern of relevance
    for candidate in reversed(matches):
        value = parse_number(candidate)
        if value is not None:
            return value
    
    return None

def find_value_near_label(ocr_lines: list, label_line: dict, all_lines: list):
    # first try: number in the same bbox
    # value = extract_number_from_line(label_line["text"])
    # if value is not None:
    #    return {"value": value, "source_line": label_line}

    # second try: searching for different bboxes with the same (approximately) y
    label_ys = [p[1] for p in label_line["polygon"]]
    label_y_center = (min(label_ys) + max(label_ys)) / 2
    label_height = max(label_ys) - min(label_ys)
    
    # if the center is less than 1x the height of the label
    tolerance = max(label_height * 1.0, 20)  # minimum 20 pixels
    
    candidates = []
    for line in all_lines:
        if line is label_line:
            continue  # thats the label itself and not the number
        
        line_ys = [p[1] for p in line["polygon"]]
        line_y_center = (min(line_ys) + max(line_ys)) / 2
        
        if abs(line_y_center - label_y_center) <= tolerance:
            value = extract_number_from_line(line["text"])
            if value is not None:
                # just using x to sort after, to get the number in the left 
                line_x = max(p[0] for p in line["polygon"])
                candidates.append({
                    "value": value,
                    "source_line": line,
                    "x_right": line_x
                })
    
    if candidates:
        label_x_right = max(p[0] for p in label_line["polygon"])
        
        # only candidates to the RIGHT of the label
        right_candidates = [c for c in candidates if c["x_right"] > label_x_right]
        
        if right_candidates:
            # closest to the right, not the furthest
            best = min(right_candidates, key=lambda c: c["x_right"])
        else:
            best = min(candidates, key=lambda c: abs(c["x_right"] - label_x_right))
        
        return {"value": best["value"], "source_line": best["source_line"]}
    
    return None

def load_ocr_pages(ocr_dir: str) -> list[dict]:
    ocr_path = pathlib.Path(ocr_dir)
    pages = []

    for json_file in sorted(ocr_path.glob("page_*.json")):
        with open(json_file, "r", encoding="utf-8") as f:
            page_data = json.load(f)
            
            if "ocr" in page_data:
                page_data["ocr"] = merge_horizontal_lines(page_data["ocr"])

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
    # ── Test detect_unit on all 328024377 documents ──
    print("\n=== detect_unit — SIREN 328024377 (kEUR company) ===")
    
    bernachon_docs = [
        ("63e8ebbb54febda17c19ee7c", "2020-12-24"),
        ("63e8ebbb54febda17c19ee7d", "2021-12-17"),
        ("63e8ebbb54febda17c19ee7e", "2022-12-13"),
    ]
    
    for doc_id, date in bernachon_docs:
        ocr_dir = f"data/328024377/bilans/ocr/{doc_id}"
        pages = load_ocr_pages(ocr_dir)
        unit = detect_unit_ker(pages)
        
        # Use the SAME strict patterns as the function
        strict_patterns = [
            "montants sont indiqués en k", "montants sont indiques en k",
            "montants exprimés en milliers", "montants exprimes en milliers",
            "montants en milliers", "exprimés en milliers", "exprimes en milliers",
            "indiqués en milliers", "indiques en milliers",
            "exprimés en k€", "exprimes en k€",
            "indiqués en k€", "indiques en k€",
            "réalisé en kilo", "realise en kilo",
            "en milliers d'euros", "en milliers d euros",
        ]
        
        found_line = None
        for page_data in pages:
            for line in page_data.get("ocr", []):
                text_lower = line["text"].lower()
                if any(p in text_lower for p in strict_patterns):
                    found_line = f"  Page {page_data['page']}: '{line['text']}'"
                    break
            if found_line:
                break
        
        status = "✓" if unit == "kEUR" else "✗"
        print(f"  {status} Doc {date} ({doc_id[:8]}...): {unit}")
        if found_line:
            print(found_line)
        else:
            print("    (no kEUR indicator found in OCR)")
