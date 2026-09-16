import re
from typing import Dict, List, Tuple

from .models import Article


def _contains(text: str, keyword: str) -> bool:
    text = text.casefold()
    keyword = keyword.casefold()
    if re.search(r"[\u3400-\u9fff]", keyword):
        return keyword in text
    return re.search(r"(?<![\w-])" + re.escape(keyword) + r"(?![\w-])", text) is not None


def score_article(article: Article, config: dict) -> Article:
    settings = config["settings"]
    title = article.title.strip()
    summary = article.summary.strip()
    combined = f"{title} {summary}"

    if any(_contains(combined, word) for word in config.get("global_exclude", [])):
        return article

    for topic_id, topic in config["topics"].items():
        if any(_contains(combined, word) for word in topic.get("exclude", [])):
            continue
        score = int(topic.get("source_boost", {}).get(article.source_id, 0))
        matches: List[str] = []
        if score:
            matches.append(f"source:{article.source_id}")
        for keyword, weight in topic.get("include", {}).items():
            title_hit = _contains(title, keyword)
            summary_hit = _contains(summary, keyword)
            if title_hit:
                score += int(weight) * int(settings.get("title_multiplier", 3))
            elif summary_hit:
                score += int(weight) * int(settings.get("summary_multiplier", 1))
            if title_hit or summary_hit:
                matches.append(keyword)
        if score:
            article.topic_scores[topic_id] = score
            article.matched_keywords[topic_id] = matches
    return article


def articles_for_topic(articles: List[Article], topic_id: str, minimum: int) -> List[Article]:
    selected = [a for a in articles if a.topic_scores.get(topic_id, 0) >= minimum]
    return sorted(selected, key=lambda a: (a.topic_scores[topic_id], a.published), reverse=True)
