from PIL import Image, ImageOps

# Detect Windows Native OCR vs Linux Tesseract for Docker
HAS_WINOCR = False
try:
    import winocr
    HAS_WINOCR = True
except Exception:
    HAS_WINOCR = False

try:
    import pytesseract
except ImportError:
    pytesseract = None


def get_ocr_engine_name():
    return "Windows Native OCR" if HAS_WINOCR else "Tesseract OCR (Linux/Docker)"


async def extract_lines_with_boxes(img: Image.Image):
    """
    Extracts text lines and bounding boxes from a PIL image.
    Returns: list of dicts [{'text': str, 'x': float, 'y': float, 'h': float}]
    """
    lines = []

    # 1. Windows Native OCR (Super fast, native on Windows)
    if HAS_WINOCR:
        try:
            res = await winocr.recognize_pil(img, lang='en-US')
            for line in res.lines:
                t = line.text.strip()
                if not t:
                    continue
                ys = [w.bounding_rect.y for w in line.words]
                hs = [w.bounding_rect.height for w in line.words]
                xs = [w.bounding_rect.x for w in line.words]
                if ys and hs:
                    lines.append({
                        'text': t,
                        'y': min(ys),
                        'h': max(hs),
                        'x': min(xs) if xs else 0
                    })
            return lines
        except Exception:
            pass

    # 2. Tesseract OCR (Cross-platform, default inside Linux Docker container)
    if pytesseract:
        gray = img.convert('L')
        enhanced = ImageOps.autocontrast(gray, cutoff=2)

        try:
            installed_langs = pytesseract.get_languages()
            lang = 'ind+eng' if 'ind' in installed_langs else 'eng'
        except Exception:
            lang = 'eng'

        data = pytesseract.image_to_data(enhanced, lang=lang, output_type=pytesseract.Output.DICT)

        grouped = {}
        for i in range(len(data['text'])):
            word = data['text'][i].strip()
            if not word:
                continue
            key = (data['block_num'][i], data['line_num'][i])
            if key not in grouped:
                grouped[key] = {
                    'words': [],
                    'ys': [],
                    'hs': [],
                    'xs': []
                }
            grouped[key]['words'].append(word)
            grouped[key]['ys'].append(data['top'][i])
            grouped[key]['hs'].append(data['height'][i])
            grouped[key]['xs'].append(data['left'][i])

        for key in sorted(grouped.keys(), key=lambda k: min(grouped[k]['ys'])):
            g = grouped[key]
            text = " ".join(g['words']).strip()
            if text:
                lines.append({
                    'text': text,
                    'y': min(g['ys']),
                    'h': max(g['hs']),
                    'x': min(g['xs'])
                })

    return lines
