import hashlib
import json
import os
import re
from pathlib import Path
from typing import Iterable, List, Tuple

import requests
from bs4 import BeautifulSoup

from .fetchers import HEADERS
from .models import Article


SYSTEM_PROMPT = """你是一名严谨的科学新闻编辑。请根据提供的标题、来源摘要和正文材料，用中文讲述这项研究。
要求：
1. 全文约300个汉字，建议控制在260—340字；
2. 写成连贯、自然的科研叙事：从研究者面对的困难、局限或知识空白切入，自然过渡到他们采用的思路和方法，再讲清发现、结论及其意义；
3. 不得使用“研究动机”“研究方法”“主要结论”“科学意义”等小标题、标签或分项罗列，也不要机械套用“首先、其次、最后”；
4. 面向具有一般科研背景的读者，准确、具体、少用空话，让各部分像一个完整故事般衔接；
5. 不得补充材料中没有的信息。材料没有披露的细节不要猜测，也不要生硬插入“公开材料未说明”；只写材料能够支持的内容；
6. 直接输出一至两个连贯的 HTML 段落（只使用 <p>），不要标题、前言、Markdown、项目符号或参考文献。"""

CACHE_VERSION = "research-summary-v2-narrative"


def _clean_text(node) -> str:
    if not node:
        return ""
    for bad in node.select("script, style, nav, header, footer, aside, form, noscript, .advertisement, .related"):
        bad.decompose()
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def _jsonld_article_bodies(soup: BeautifulSoup) -> List[str]:
    bodies = []

    def walk(value):
        if isinstance(value, dict):
            body = value.get("articleBody")
            if isinstance(body, str):
                bodies.append(re.sub(r"\s+", " ", BeautifulSoup(body, "lxml").get_text(" ", strip=True)).strip())
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for node in soup.select('script[type="application/ld+json"]'):
        try:
            walk(json.loads(node.string or node.get_text() or ""))
        except (TypeError, ValueError):
            continue
    return bodies


def extract_article_text(article: Article, timeout: int = 20) -> Tuple[str, str]:
    try:
        response = requests.get(article.link, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        candidates = []
        for selector in (
            '[itemprop="articleBody"]',
            ".article-body",
            ".article__body",
            ".news-article",
            ".article-main",
            ".article-content",
            ".entry-content",
            ".post-content",
            "article",
            "main",
            "#article",
            "#content",
        ):
            candidates.extend(soup.select(selector))
        texts = _jsonld_article_bodies(soup) + [_clean_text(node) for node in candidates]
        text = max(texts, key=len, default="")
        if len(text) >= 500:
            return text[:14000], "fulltext"
    except Exception:
        pass
    fallback = f"标题：{article.title}\n公开摘要：{article.summary or '无'}"
    return fallback[:6000], "abstract"


def build_input(article: Article, material: str, basis: str) -> str:
    return f"来源：{article.source_name}\n标题：{article.title}\n材料类型：{'网页正文' if basis == 'fulltext' else '标题与公开摘要'}\n材料：\n{material}"


def _normalize(text: str) -> str:
    text = text.strip().replace("```html", "").replace("```", "").strip()
    return re.sub(r"\n+", "", text)


def _has_section_labels(text: str) -> bool:
    plain = BeautifulSoup(text, "lxml").get_text(" ", strip=True)
    return any(re.search(rf"{label}\s*[：:]", plain) for label in ("研究动机", "研究方法", "主要结论", "科学意义"))


class SummaryCache:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, article: Article) -> Path:
        key = hashlib.sha256(f"{CACHE_VERSION}:{article.uid}".encode("utf-8")).hexdigest()
        return self.directory / f"{key}.json"

    def load(self, article: Article) -> bool:
        path = self._path(article)
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            article.ai_summary = data["summary"]
            article.summary_basis = data.get("basis", "abstract")
            return bool(article.ai_summary)
        except (ValueError, KeyError, TypeError):
            return False

    def save(self, article: Article):
        self._path(article).write_text(json.dumps({"url": article.link, "summary": article.ai_summary, "basis": article.summary_basis}, ensure_ascii=False, indent=2), encoding="utf-8")


def summarize_articles(articles: Iterable[Article], cache_dir: Path, max_new: int = 20) -> dict:
    unique = {article.uid: article for article in articles}
    cache = SummaryCache(cache_dir)
    cached = sum(cache.load(article) for article in unique.values())
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {"enabled": False, "cached": cached, "created": 0, "failed": 0}

    from openai import OpenAI
    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    client_options = {"api_key": api_key, "timeout": 60.0, "max_retries": 2}
    if base_url:
        client_options["base_url"] = base_url.rstrip("/")
    client_options["max_retries"] = 1
    client = OpenAI(**client_options)
    model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    created = failed = attempted = 0
    errors = []
    for article in unique.values():
        if article.ai_summary:
            continue
        if attempted >= max_new:
            break
        attempted += 1
        try:
            material, basis = extract_article_text(article)
            response = client.responses.create(
                model=model,
                instructions=SYSTEM_PROMPT,
                input=build_input(article, material, basis),
                max_output_tokens=700,
            )
            summary = _normalize(response.output_text)
            if not summary:
                raise ValueError("AI response was empty")
            plain_length = len(BeautifulSoup(summary, "lxml").get_text("", strip=True))
            if _has_section_labels(summary) or not 230 <= plain_length <= 380:
                revision = client.responses.create(
                    model=model,
                    instructions=SYSTEM_PROMPT,
                    input=f"请将下面这份摘要改写为260—340个汉字的连贯科研故事。融合动机、做法、发现和意义，不使用任何小标题或标签，保留事实且不得增加信息：\n{summary}",
                    max_output_tokens=700,
                )
                summary = _normalize(revision.output_text)
            if not summary or _has_section_labels(summary):
                raise ValueError("AI response did not follow narrative format")
            article.ai_summary = summary
            article.summary_basis = basis
            cache.save(article)
            created += 1
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            print(f"AI summary failed for {article.link}: {message}")
            if len(errors) < 3:
                errors.append({"url": article.link, "error": message[:1000]})
            failed += 1
            # Relay 5xx errors usually affect the whole upstream group. Stop
            # immediately instead of sending the same doomed request for every
            # article; the next hourly run can retry after the provider recovers.
            if getattr(exc, "status_code", None) in {500, 502, 503, 504}:
                break
    return {"enabled": True, "cached": cached, "attempted": attempted, "created": created, "failed": failed, "errors": errors}
