from datetime import datetime, timezone
import sys
import types

from science_rss.ai_summary import SummaryCache, SYSTEM_PROMPT, build_input, extract_article_text, summarize_articles
from science_rss.models import Article


def make_article():
    return Article("Active particles form a new phase", "https://example.com/paper", "x", "Test Source", datetime.now(timezone.utc), "A public abstract")


def test_prompt_contains_required_research_structure():
    for label in ("研究动机", "研究方法", "主要结论", "科学意义"):
        assert label in SYSTEM_PROMPT
    assert "300" in SYSTEM_PROMPT
    assert "不得使用" in SYSTEM_PROMPT


def test_input_marks_material_basis():
    value = build_input(make_article(), "full paper text", "fulltext")
    assert "网页正文" in value
    assert "full paper text" in value


def test_summary_cache_roundtrip(tmp_path):
    article = make_article()
    article.ai_summary = "<p>研究者从一个尚未解决的问题出发，通过实验寻找答案。</p>"
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
    text = "<p>已有研究难以解释该体系在非平衡条件下为何会出现集体演化，微观作用如何转化为宏观响应也一直缺少直接证据。为追踪这一过程，研究者把可控实验、定量成像和理论建模结合起来，系统改变关键参数，并比较不同条件下结构与动力学的变化。结果显示，局部相互作用能够触发稳定的协同行为，实验趋势与模型预测相符，团队由此找到了控制转变的主要因素。这项工作把长期分离的微观机制与宏观现象连接起来，不仅为理解非平衡物质提供了更清晰的物理图景，也为设计性质可调的功能材料带来了新的思路。</p>"

    class Response:
        output_text = text

    class Responses:
        def create(self, **kwargs):
            assert "instructions" in kwargs
            return Response()

    received_options = {}

    class Client:
        def __init__(self, **kwargs):
            received_options.update(kwargs)
            self.responses = Responses()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=Client))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://relay.example/v1/")
    monkeypatch.setattr("science_rss.ai_summary.extract_article_text", lambda article: ("paper text", "fulltext"))
    article = make_article()
    status = summarize_articles([article], tmp_path)
    assert status["created"] == 1
    assert "研究动机：" not in article.ai_summary
    assert "已有研究难以解释" in article.ai_summary
    assert SummaryCache(tmp_path).load(make_article())
    assert received_options["base_url"] == "https://relay.example/v1"


def test_official_api_omits_custom_base_url(tmp_path, monkeypatch):
    received_options = {}

    class Responses:
        def create(self, **kwargs):
            return types.SimpleNamespace(output_text="<p>一个尚未解决的问题促使研究者开展实验。他们比较不同条件，发现了新的规律，并为后续研究提供了线索。</p>")

    class Client:
        def __init__(self, **kwargs):
            received_options.update(kwargs)
            self.responses = Responses()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=Client))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setattr("science_rss.ai_summary.extract_article_text", lambda article: ("paper text", "fulltext"))
    summarize_articles([make_article()], tmp_path)
    assert "base_url" not in received_options


def test_relay_502_stops_after_first_article(tmp_path, monkeypatch):
    calls = []

    class RelayError(Exception):
        status_code = 502

    class Responses:
        def create(self, **kwargs):
            calls.append(kwargs)
            raise RelayError("origin bad gateway")

    class Client:
        def __init__(self, **kwargs):
            self.responses = Responses()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=Client))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("science_rss.ai_summary.extract_article_text", lambda article: ("paper text", "fulltext"))
    articles = [make_article() for _ in range(5)]
    for index, article in enumerate(articles):
        article.link = f"https://example.com/paper-{index}"
    status = summarize_articles(articles, tmp_path, max_new=3)
    assert len(calls) == 1
    assert status["attempted"] == 1
    assert status["failed"] == 1
    assert "origin bad gateway" in status["errors"][0]["error"]


def test_extracts_article_body_from_jsonld(monkeypatch):
    body = "这是一段正文。" * 100
    html = f'<html><script type="application/ld+json">{{"@type":"NewsArticle","articleBody":"{body}"}}</script></html>'

    class Response:
        text = html

        def raise_for_status(self):
            return None

    monkeypatch.setattr("science_rss.ai_summary.requests.get", lambda *args, **kwargs: Response())
    text, basis = extract_article_text(make_article())
    assert basis == "fulltext"
    assert text.startswith("这是一段正文")
