"""
Persistent LRU Scan History Manager for deduplication.
Stores past scanned editions and signatures to prevent duplicate entries.
"""

import os
import sys
import json
from datetime import datetime


class ScanHistoryManager:
    """Manages persistent LRU deduplication history of past scans."""

    def __init__(self, history_file: str, max_items: int = 20):
        self.history_file = history_file
        self.max_items = max_items
        self.history = self._load()

    def _load(self) -> list:
        if os.path.exists(self.history_file):
            try:
                if os.path.getsize(self.history_file) == 0:
                    return []
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data[-self.max_items:]
            except Exception as e:
                print(f"[WARN] Gagal membaca riwayat pindaian: {e}", file=sys.stderr)
        return []

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[WARN] Gagal menyimpan riwayat pindaian: {e}", file=sys.stderr)

    def clear(self):
        self.history = []
        self.save()

    def generate_signature(self, record: dict) -> dict:
        ed = str(record.get("edition") or "").strip().lower()
        yr = str(record.get("year_roman") or "").strip().lower()
        dt = str(record.get("date") or "").strip().lower()
        raw_articles = record.get("articles") or []
        articles = []
        for a in raw_articles:
            title = ""
            if isinstance(a, dict):
                title = a.get("title") or ""
            elif isinstance(a, str):
                title = a
            title = str(title).strip().lower()
            if len(title) > 3:
                articles.append(title)

        return {
            "edition": ed,
            "year_roman": yr,
            "date": dt,
            "articles": articles[:5]
        }

    def is_duplicate(self, record: dict) -> tuple[bool, dict | None]:
        """
        Checks if a scan matches any record in the recent history.
        Matches by edition & date, or significant article title overlap.
        """
        sig = self.generate_signature(record)
        if not sig["edition"] and not sig["articles"]:
            return False, None

        for item in reversed(self.history):
            item_ed = str(item.get("edition") or "").strip().lower()
            item_dt = str(item.get("date") or "").strip().lower()

            # Check 1: Edition Match
            if sig["edition"] and item_ed and sig["edition"] == item_ed:
                if not sig["date"] or not item_dt or sig["date"] == item_dt:
                    return True, item

            # Check 2: Article title overlap
            item_articles = set(str(a).strip().lower() for a in item.get("articles", []))
            if item_articles and sig["articles"]:
                common = item_articles.intersection(set(sig["articles"]))
                if len(common) >= 2 or (len(common) == 1 and len(sig["articles"]) <= 2):
                    return True, item

        return False, None

    def add(self, record: dict):
        sig = self.generate_signature(record)
        entry = {
            "edition": record.get("edition") or "-",
            "year_roman": record.get("year_roman") or "-",
            "date": record.get("date") or "-",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "articles_count": len(record.get("articles") or []),
            "articles": sig["articles"],
            "summary": f"Edisi {record.get('edition') or '?'} ({record.get('date') or '?'})"
        }
        self.history.append(entry)
        if len(self.history) > self.max_items:
            self.history = self.history[-self.max_items:]
        self.save()
