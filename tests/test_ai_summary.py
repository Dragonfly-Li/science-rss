from datetime import datetime, timezone
import sys
import types

from science_rss.ai_summary import SummaryCache, SYSTEM_PROMPT, build_input, summarize_articles
from science_rss.models import Article


def make_article():
    return Article("Active particles form a new phase", "https://example.com/paper", "x", "Test Source", datetime.now(timezone.utc), "A public abstract")


def test_prompt_contains_required_research_structure():
    for label in ("研究动机", "研究方法", "主要结论", "科学意义"):
        assert label in SYSTEM_PROMPT
    assert "300" in SYSTEM_PROMPT


def test_input_marks_material_basis():
    value = build_input(make_article(), "full paper text", "fulltext")
    assert "网页正文" in value
    assert "full paper text" in value


def test_summary_cache_roundtrip(tmp_path):
    article = make_article()
    article.ai_summary = "<b>研究动机：</b>测试"
    article.summary_basis = "abstract"
    cache = SummaryCache(tmp_path)
    cache.save(article)
    copy = make_article()
    assert cache.load(copy)
    assert copy.ai_summary == article.ai_summary
    assert copy.summary_basis == "abstract"


def test_without_api_key_uses_cache_only(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    status = summarize_articles([make_article()], tmp_path)
    assert status == {"enabled": False, "cached": 0, "created": 0, "failed": 0}


def test_api_result_is_saved_and_attached(tmp_path, monkeypatch):
    text = "".join([
        "<b>研究动机：</b>已有研究难以解释该体系在非平衡条件下的集体演化规律，关键机制和适用范围仍缺少直接证据。",
        "<b>研究方法：</b>研究者结合可控实验、定量成像与理论建模，系统改变关键参数，并比较不同条件下的结构和动力学响应。",
        "<b>主要结论：</b>结果显示局部相互作用会触发稳定的协同行为，实验趋势与模型预测一致，并确定了发生转变的主要控制因素。",
        "<b>科学意义：</b>该工作填补了微观机制与宏观现象之间的联系，为理解非平衡物质及设计可调控功能材料提供了新思路。",
    ])

    class Response:
        output_text = text

    class Responses:
        def create(self, **kwargs):
            assert "instructions" in kwargs
            return Response()

    class Client:
        def __init__(self, **kwargs):
            self.responses = Responses()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=Client))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("science_rss.ai_summary.extract_article_text", lambda article: ("paper text", "fulltext"))
    article = make_article()
    status = summarize_articles([article], tmp_path)
    assert status["created"] == 1
    assert "研究动机" in article.ai_summary
    assert SummaryCache(tmp_path).load(make_article())
