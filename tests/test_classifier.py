from datetime import datetime, timezone

from science_rss.classifier import articles_for_topic, score_article
from science_rss.models import Article


CONFIG = {
    "settings": {"minimum_score": 2, "title_multiplier": 3, "summary_multiplier": 1},
    "global_exclude": ["娱乐"],
    "topics": {
        "softmatter": {
            "include": {"soft matter": 5, "胶体": 4},
            "exclude": ["software"],
            "source_boost": {"trusted_soft": 6},
        }
    },
}


def article(title, summary=""):
    return Article(title, "https://example.com/a", "x", "X", datetime.now(timezone.utc), summary)


def test_title_has_higher_weight():
    result = score_article(article("New soft matter physics"), CONFIG)
    assert result.topic_scores["softmatter"] == 15


def test_summary_match_and_chinese_match():
    result = score_article(article("A new material", "胶体体系中的相变"), CONFIG)
    assert result.topic_scores["softmatter"] == 4


def test_exclusion_blocks_false_positive():
    assert score_article(article("Software for soft matter"), CONFIG).topic_scores == {}
    assert score_article(article("娱乐中的胶体"), CONFIG).topic_scores == {}


def test_topic_sorting():
    a = score_article(article("soft matter"), CONFIG)
    b = score_article(article("sample", "soft matter"), CONFIG)
    assert articles_for_topic([b, a], "softmatter", 2) == [a, b]


def test_source_boost_includes_relevant_category_feed():
    value = article("An otherwise generic research headline")
    value.source_id = "trusted_soft"
    result = score_article(value, CONFIG)
    assert result.topic_scores["softmatter"] == 6
