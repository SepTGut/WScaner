import re
from datetime import datetime

INDONESIAN_MONTHS = [
    'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
    'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember',
    'January', 'February', 'March', 'May', 'June', 'July',
    'August', 'October', 'December'
]

def is_noise_line(t: str) -> bool:
    """Detects page numbers, isolated symbols, and layout artifacts."""
    clean = re.sub(r'[^\w]', '', t)
    # 1-2 character isolated noise
    if len(clean) <= 2 and not clean.isalpha():
        return True
    if len(clean) == 1 and clean in ['i', 'l', '1', '|', '-']:
        return True
    # Standalone page numbers or pagination formats, e.g. '16-15', '2108', 's 11', 'L 32', '1ST'
    if re.match(r'^(?:hal\.?|hlm\.?)?\s*\d+(?:[-\s/]\d+)?$', t, re.I):
        return True
    if re.match(r'^[^\w]*\d+(?:[-\s/]\d+)?[^\w]*$', t):
        return True
    if re.match(r'^[^\w]*[A-Za-z]{1,2}\s*\d+[^\w]*$', t):
        return True
    if t.lower() in ['soesi', 'ang', '1st', 'l 32', 's 11']:
        return True
    return False


def clean_title(title: str) -> str:
    """Cleans OCR artifacts, fixes known font misreadings, and normalizes typography."""
    t = title.strip()
    
    # 1. Normalize stylized quotes and accented letters
    t = t.replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
    t = t.replace('ö', 'o').replace('Ö', 'O').replace('ü', 'u').replace('Ü', 'U')
    t = t.replace('ë', 'e').replace('ï', 'i').replace('é', 'e').replace('è', 'e')

    # 2. Known Indonesian / Islamic OCR font corrections
    t = re.sub(r'\bFreudisrne\b', 'Freudisme', t, flags=re.I)
    t = re.sub(r'\bAkhiratp\b', 'Akhirat:', t, flags=re.I)
    t = re.sub(r'\bPortofo\'?lio\b', 'Portofolio', t, flags=re.I)
    t = re.sub(r'\bPortofoliö\b', 'Portofolio', t, flags=re.I)

    # 3. Clean spacing around colons and punctuation
    t = re.sub(r'\s+:', ':', t)
    t = re.sub(r':\s*', ': ', t)
    t = re.sub(r'\s{2,}', ' ', t)

    # 4. Remove leading/trailing stray non-word characters (except quotes/parentheses)
    t = re.sub(r'^[^\w"\'(]+', '', t)
    t = re.sub(r'[^\w"\').!?]+$', '', t)
    
    return t.strip()


def extract_surah(title: str):
    """Extracts Surah if present in parentheses, e.g. (Hikmah Surah Al-Hasyr Ayat 9)."""
    m = re.search(r'\((?:(?:Hikmah|Tafsir|Kajian|Renungan)\s+)?(Surah?\s+[^)]+)\)', title, re.I)
    if m:
        surah = m.group(1).strip()
        clean_t = re.sub(r'\s*\((?:(?:Hikmah|Tafsir|Kajian|Renungan)\s+)?(Surah?\s+[^)]+)\)', '', title, flags=re.I).strip()
        return clean_title(clean_t), surah
    return clean_title(title), "-"


def clean_author_name(author: str) -> str:
    """Cleans OCR artifacts and fixes common italic font glitches in author names."""
    a = author.strip()
    # Strip leading prefixes like "Oleh:", "Penulis:", "By:"
    a = re.sub(r'^(?:Oleh|Penulis|By)\s*[:\-]?\s*', '', a, flags=re.I)
    # Strip leading quotes/apostrophes from italic font detection
    a = re.sub(r'^[\'"`\s]+', '', a)

    lower_a = a.lower()
    if lower_a in ['rus mina', 'ku emina', 'kusmina']:
        return 'Kusmina'
    if lower_a in ['susan ti', 'susanti']:
        return 'Susanti'
    if lower_a in ['m.a. risandy', 'ma risandy', 'm a risandy']:
        return 'M.A. Risandy'

    # Fix author spacing and trailing artifacts
    a = re.sub(r'\s{2,}', ' ', a)
    if not a.endswith('.'):
        a = re.sub(r'[^\w.\s&]+$', '', a)

    return a.strip()


def parse_metadata(lines):
    """
    Extracts Edition number and Date from detected lines.
    Supports single or multi-line metadata across full page or cropped footer.
    """
    edition = ""
    date_val = ""
    raw_text = ""

    # Priority 1: Check lines containing 'Edisi', 'Tahun', 'Bulan', or 'No'
    for item in lines:
        t = item['text'].strip()
        t_low = t.lower()
        if any(k in t_low for k in ['edisi', 'tahun', 'bulan', 'no.', 'nomor']):
            raw_text += " " + t
            
            if not edition:
                # Matches: Edisi 50, Edisi: 50, Edisi : 50, Ed. 50, Edisi ke-50, Edisi/50, No. 50, Nomor 50
                edisi_match = re.search(r'(?:Edisi|Ed\.?|Nomor|No\.?)\s*[:.\-/#]?\s*(?:ke-?)?\s*(\d+)', t, re.I)
                if edisi_match:
                    edition = edisi_match.group(1)

            if not date_val:
                month_pattern = '|'.join(INDONESIAN_MONTHS)
                date_match = re.search(rf'(?:Bulan\s*[:.\-/#]?\s*)?({month_pattern})\s*[,.\-/#]?\s*(\d{{4}})', t, re.I)
                if date_match:
                    month_name = date_match.group(1).capitalize()
                    year_val = date_match.group(2)
                    date_val = f"{month_name} {year_val}"

    # Priority 2: Fallback searches across all lines
    if not edition:
        for item in reversed(lines):
            edisi_match = re.search(r'(?:Edisi|Ed\.?|Nomor|No\.?)\s*[:.\-/#]?\s*(?:ke-?)?\s*(\d+)', item['text'], re.I)
            if edisi_match:
                edition = edisi_match.group(1)
                break

    if not date_val:
        for item in reversed(lines):
            month_pattern = '|'.join(INDONESIAN_MONTHS)
            date_match = re.search(rf'({month_pattern})\s*[,.\-/#]?\s*(\d{{4}})', item['text'], re.I)
            if date_match:
                date_val = f"{date_match.group(1).capitalize()} {date_match.group(2)}"
                break

    return edition, date_val, raw_text.strip()


def parse_articles(sidebar_lines):
    """
    Partitions sidebar lines into exactly 3 articles using vertical gap analysis.
    Filters noise, strips pagination tags, cleans titles and author names.
    """
    valid_lines = []
    for item in sidebar_lines:
        t = item['text'].strip()
        if not t:
            continue
        t_low = t.lower()
        # Skip header/footer tags and metadata lines
        if t_low in ['artikel', 'edisi ini', 'artikel edisi ini']:
            continue
        if re.search(r'\b(tahun|edisi)\b', t_low):
            continue
        # Skip stray page numbers and isolated noise
        if is_noise_line(t):
            continue
        valid_lines.append((item['y'], item['h'], t))

    articles = []

    if len(valid_lines) >= 3:
        # Calculate vertical gaps between consecutive lines
        gaps = []
        for i in range(len(valid_lines) - 1):
            y_curr = valid_lines[i][0]
            h_curr = valid_lines[i][1]
            y_next = valid_lines[i+1][0]
            gaps.append((y_next - (y_curr + h_curr), i))

        # The 2 biggest vertical gaps represent the article boundaries
        sorted_gaps = sorted(gaps, key=lambda x: x[0], reverse=True)[:2]
        split_indices = sorted([x[1] for x in sorted_gaps])

        chunks = [
            valid_lines[:split_indices[0] + 1],
            valid_lines[split_indices[0] + 1:split_indices[1] + 1],
            valid_lines[split_indices[1] + 1:]
        ]

        for chunk in chunks:
            lines = [x[2] for x in chunk if not is_noise_line(x[2])]
            if not lines:
                continue

            if len(lines) == 1:
                title, surah = extract_surah(lines[0])
                articles.append({"title": title, "author": "", "surah": surah})
            else:
                # Check for two-line or joint authors with '&'
                if len(lines) >= 3 and '&' in lines[-2]:
                    raw_author = lines[-2] + " " + lines[-1]
                    raw_title = " ".join(lines[:-2])
                else:
                    raw_author = lines[-1]
                    raw_title = " ".join(lines[:-1])

                author = clean_author_name(raw_author)
                title, surah = extract_surah(raw_title)
                articles.append({
                    "title": title,
                    "author": author,
                    "surah": surah
                })
    else:
        for v in valid_lines:
            title, surah = extract_surah(v[2])
            articles.append({"title": title, "author": "", "surah": surah})

    return articles

