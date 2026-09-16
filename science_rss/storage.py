import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from dateutil import parser as date_parser

from .models import Article


def article_to_dict(article: Article) -> dict:
    return {
        "title": article.title,
        "link": article.link,
        "source_id": article.source_id,
        "source_name": article.source_name,
        "published": article.published.isoformat(),
        "summary": article.summary,
        "topic_scores": article.topic_scores,
        "matched_keywords": article.matched_keywords,
    }


def article_from_dict(value: dict) -> Article:
    value = dict(value)
    value["published"] = date_parser.parse(value["published"])
    return Article(**value)


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.mkdir(parents=True, exist_ok=True)

    def load(self, source_id: str) -> List[Article]:
        file = self.path / f"{source_id}.json"
        if not file.exists():
            return []
        try:
            return [article_from_dict(x) for x in json.loads(file.read_text(encoding="utf-8"))]
        except (ValueError, TypeError, KeyError):
            return []

    def save(self, source_id: str, articles: List[Article]):
        file = self.path / f"{source_id}.json"
        file.write_text(json.dumps([article_to_dict(x) for x in articles], ensure_ascii=False, indent=2), encoding="utf-8")

