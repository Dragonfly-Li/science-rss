import html as html_lib
import re
from datetime import datetime, timezone
from typing import List
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from .models import Article


HEADERS = {
    "User-Agent": "science-rss/2.0 (+personal academic feed; respectful hourly fetch)",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _date(value) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        result = date_parser.parse(str(value))
        return result.replace(tzinfo=result.tzinfo or timezone.utc).astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return datetime.now(timezone.utc)


def _clean(value: str) -> str:
    value = value or ""
    if "<" not in value:
        return re.sub(r"\s+", " ", html_lib.unescape(value)).strip()
    soup = BeautifulSoup(value, "lxml")
    return re.sub(r"\s+", " ", html_lib.unescape(soup.get_text(" ", strip=True))).strip()


def _get(url: str, timeout: int = 15) -> requests.Response:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response


def fetch_rss(source: dict) -> List[Article]:
    response = _get(source["url"])
    parsed = feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"invalid feed: {parsed.bozo_exception}")
    articles = []
    for entry in parsed.entries[:100]:
        title = _clean(entry.get("title", ""))
        link = urljoin(source["url"], entry.get("link", ""))
        if not title or not link:
            continue
        articles.append(Article(
            title=title,
            link=link,
            source_id=source["id"],
            source_name=source["name"],
            published=_date(entry.get("published") or entry.get("updated")),
            summary=_clean(entry.get("summary") or entry.get("description") or ""),
        ))
    return articles


def _node_text(node, selector: str) -> str:
    if not node or not selector:
        return ""
    match = node.select_one(selector)
    return _clean(match.get_text(" ", strip=True)) if match else ""


def fetch_html(source: dict, html_text: str = "") -> List[Article]:
    if not html_text:
        response = _get(source["url"])
        html_text = response.text
    soup = BeautifulSoup(html_text, "lxml")
    selectors = source.get("selectors", {})
    nodes = soup.select(selectors.get("item", "article, li"))
    articles = []
    seen = set()
    for node in nodes:
        anchor = node.select_one(selectors.get("link", "a[href]"))
        if not anchor or not anchor.get("href"):
            continue
        title = _node_text(node, selectors.get("title", "h2, h3, a")) or _clean(anchor.get_text(" ", strip=True))
        link = urljoin(source["url"], anchor["href"])
        if len(title) < 6 or link in seen or link.startswith(("javascript:", "mailto:")):
            continue
        date_text = _node_text(node, selectors.get("date", "time, .date"))
        summary = _node_text(node, selectors.get("summary", "p, .summary, .excerpt"))
        seen.add(link)
        articles.append(Article(title, link, source["id"], source["name"], _date(date_text), summary))
        if len(articles) >= 60:
            break
    # Generic anchor fallback for sites that changed wrappers/classes but still
    # expose server-rendered article links. It intentionally rejects navigation,
    # category and account links to keep the feed useful after minor redesigns.
    if not articles:
        base_host = urlparse(source["url"]).netloc.removeprefix("www.")
        blocked = ("login", "register", "about", "contact", "privacy", "tag/", "category/", "author/", "search")
        for anchor in soup.select("a[href]"):
            title = _clean(anchor.get_text(" ", strip=True))
            link = urljoin(source["url"], anchor.get("href", ""))
            parsed = urlparse(link)
            path = parsed.path.strip("/")
            if len(title) < 8 or not path or link in seen:
                continue
            if parsed.netloc.removeprefix("www.") != base_host or any(word in link.casefold() for word in blocked):
                continue
            if len(path.split("/")) < 2 and not re.search(r"\d{4,}", path):
                continue
            parent = anchor.find_parent(["article", "li", "div"])
            summary = _node_text(parent, "p, .summary, .excerpt") if parent else ""
            date_text = _node_text(parent, "time, .date") if parent else ""
            seen.add(link)
            articles.append(Article(title, link, source["id"], source["name"], _date(date_text), summary))
            if len(articles) >= 60:
                break
    if not articles:
        raise RuntimeError("no article nodes matched")
    return articles


def fetch_source(source: dict) -> List[Article]:
    if source["type"] == "rss":
        try:
            return fetch_rss(source)
        except Exception:
            if source.get("fallback_url"):
                fallback = dict(source, url=source["fallback_url"], type="html")
                fallback["selectors"] = {"item": "article, .post, .news-item", "title": "h2, h3, .title", "link": "a", "date": "time, .date"}
                return fetch_html(fallback)
            raise
    try:
        return fetch_html(source)
    except Exception:
        if not source.get("browser_fallback"):
            raise
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"], locale="zh-CN")
            page.goto(source["url"], wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2500)
            content = page.content()
            browser.close()
        return fetch_html(source, html_text=content)
