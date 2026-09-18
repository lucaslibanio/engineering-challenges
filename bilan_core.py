import json 
import pathlib
import pymupdf
import difflib
import re


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
    value = extract_number_from_line(label_line["text"])
    if value is not None:
        return {"value": value, "source_line": label_line}

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
    # ── Test parse_number ──
    print("=== parse_number ===")
    parse_tests = [
        ("1 234 567", 1234567.0),
        ("1.234.567", 1234567.0),
        ("45 231,89", 45231.89),
        ("(45 231)", -45231.0),
        ("- 12 000", -12000.0),
        ("néant", None),
        ("", None),
    ]
    for text, expected in parse_tests:
        result = parse_number(text)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{text}' → {result} (expected: {expected})")

    # ── Test extract_number_from_line ──
    print("\n=== extract_number_from_line ===")
    extract_tests = [
        ("Montant net du chiffre d'affaires 1 234 567", 1234567.0),
        ("Total général (I + II) 45 231", 45231.0),
        ("Néant", None),
        ("FW 892 114", 892114.0),
        ("2052", 2052.0),  # page number — will match, thats expected
    ]
    for text, expected in extract_tests:
        result = extract_number_from_line(text)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{text}' → {result} (expected: {expected})")

    # ── Test find_value_near_label with fake OCR lines ──
    print("\n=== find_value_near_label ===")
    
    # Simulates a table row: label on the left, three numbers to the right
    # Like: "TOTAL DETTES"  |  213 687  |  214 974  |  160 421
    fake_lines = [
        {"polygon": [[100,500],[300,500],[300,520],[100,520]], "text": "TOTAL DETTES FOURNISSEURS", "score": 0.99},
        {"polygon": [[400,500],[480,500],[480,520],[400,520]], "text": "213 687", "score": 0.98},
        {"polygon": [[550,500],[630,500],[630,520],[550,520]], "text": "214 974", "score": 0.97},
        {"polygon": [[700,500],[780,500],[780,520],[700,520]], "text": "160 421", "score": 0.96},
        {"polygon": [[100,600],[300,600],[300,620],[100,620]], "text": "Something else", "score": 0.95},
    ]
    
    label = fake_lines[0]  # "TOTAL DETTES FOURNISSEURS"
    result = find_value_near_label(fake_lines, label, fake_lines)
    
    if result:
        expected_value = 213687.0  # should pick the CLOSEST to the right, not the furthest
        status = "✓" if result["value"] == expected_value else "✗"
        print(f"  {status} Label: '{label['text']}'")
        print(f"    Found: {result['value']} from '{result['source_line']['text']}'")
        print(f"    Expected: {expected_value}")
    else:
        print("  ✗ No value found (should have found 213687)")

    # Test: number inside the label text itself
    inline_lines = [
        {"polygon": [[100,300],[600,300],[600,320],[100,320]], "text": "Capital social 50 000", "score": 0.99},
    ]
    result2 = find_value_near_label(inline_lines, inline_lines[0], inline_lines)
    if result2:
        status = "✓" if result2["value"] == 50000.0 else "✗"
        print(f"  {status} Inline: '{inline_lines[0]['text']}' → {result2['value']} (expected: 50000.0)")



