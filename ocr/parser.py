import re

def extract_surah(title: str):
    """Extracts Surah if present in parentheses, e.g. (Hikmah Surah Al-Hasyr Ayat 9)."""
    m = re.search(r'\((?:Hikmah\s+)?(Surah?\s+[^)]+)\)', title, re.I)
    if m:
        surah = m.group(1).strip()
        clean_title = re.sub(r'\s*\((?:Hikmah\s+)?(Surah?\s+[^)]+)\)', '', title).strip()
        return clean_title, surah
    return title.strip(), "-"


def clean_author_name(author: str):
    """Cleans OCR artifacts and fixes common italic font glitches."""
    a = author.strip()
    if a.lower() in ['rus mina', 'ku emina', 'kusmina']:
        return 'Kusmina'
    if a.lower() in ['susan ti', "'susan ti", 'susanti']:
        return 'Susanti'
    if a.endswith('.'):
        return a
    return re.sub(r'[^\w.\s&]+$', '', a)


def parse_metadata(lines):
    """Extracts Edition number and Date from full-page lines."""
    bottom_text = ""
    for item in lines:
        t = item['text']
        if 'Tahun' in t or 'Edisi' in t:
            bottom_text = t
            break

    edisi_match = re.search(r'Edisi\s*(\d+)', bottom_text, re.I)
    edition = edisi_match.group(1) if edisi_match else ""

    date_match = re.search(r'(?:Bulan\s+)?([A-Za-z]+\s+\d{4})', bottom_text)
    date_val = date_match.group(1) if date_match else "April 2026"

    return edition, date_val, bottom_text


def parse_articles(sidebar_lines):
    """
    Partitions sidebar lines into exactly 3 articles using vertical gap analysis.
    """
    valid_lines = []
    for item in sidebar_lines:
        t = item['text'].strip()
        if not t or t in ['Artikel', 'edisi ini'] or 'Tahun' in t or 'Edisi' in t:
            continue
        valid_lines.append((item['y'], item['h'], t))

    articles = []

    if len(valid_lines) >= 3:
        # Calculate gaps between consecutive lines
        gaps = []
        for i in range(len(valid_lines) - 1):
            y_curr = valid_lines[i][0]
            h_curr = valid_lines[i][1]
            y_next = valid_lines[i+1][0]
            gaps.append((y_next - (y_curr + h_curr), i))

        # The 2 biggest gaps are the boundaries between the 3 articles
        sorted_gaps = sorted(gaps, key=lambda x: x[0], reverse=True)[:2]
        split_indices = sorted([x[1] for x in sorted_gaps])

        chunks = [
            valid_lines[:split_indices[0] + 1],
            valid_lines[split_indices[0] + 1:split_indices[1] + 1],
            valid_lines[split_indices[1] + 1:]
        ]

        for chunk in chunks:
            lines = [x[2] for x in chunk]
            if not lines:
                continue
            if len(lines) == 1:
                title, surah = extract_surah(lines[0])
                articles.append({"title": title, "author": "", "surah": surah})
            else:
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
