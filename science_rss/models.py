from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List


@dataclass
class Article:
    title: str
    link: str
    source_id: str
    source_name: str
    published: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    summary: str = ""
    topic_scores: Dict[str, int] = field(default_factory=dict)
    matched_keywords: Dict[str, List[str]] = field(default_factory=dict)
    ai_summary: str = ""
    summary_basis: str = ""

    @property
    def uid(self) -> str:
        return self.link.rstrip("/").lower()
