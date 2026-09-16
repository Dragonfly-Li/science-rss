import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .classifier import articles_for_topic, score_article
from .ai_summary import summarize_articles
from .config import load_sources, load_topics
from .fetchers import fetch_source
from .output import deduplicate, write_feed, write_health, write_index
from .storage import StateStore


def run(output_dir: Path, state_dir: Path, base_url: str):
    output_dir.mkdir(parents=True, exist_ok=True)
    state = StateStore(state_dir)
    sources = load_sources()
    topic_config = load_topics()
    health = []
    all_articles = []
    feed_cards = []

    def collect(source):
        started = time.monotonic()
        status, error = "ok", ""
        try:
            articles = fetch_source(source)
            if not articles:
                raise RuntimeError("source returned zero items")
            state.save(source["id"], articles)
        except Exception as exc:
            articles = state.load(source["id"])
            status, error = "cached", str(exc)[:300]
        return source, articles, status, error, round((time.monotonic() - started) * 1000)

    results = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(collect, source): source["id"] for source in sources}
        for future in as_completed(futures):
            source, articles, status, error, duration_ms = future.result()
            results[source["id"]] = (source, articles, status, error, duration_ms)

    for source in sources:
        source, articles, status, error, duration_ms = results[source["id"]]
        articles = [score_article(a, topic_config) for a in articles]
        all_articles.extend(articles)
        filename = f'{source["id"]}.xml'
        write_feed(output_dir / filename, source["name"], f'{source["name"]} 自定义 RSS', source["url"], articles)
        health.append({"id": source["id"], "name": source["name"], "status": status, "items": len(articles), "duration_ms": duration_ms, "error": error})
        feed_cards.append({"name": source["name"], "description": "单一来源订阅", "file": filename})

    settings = topic_config["settings"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(settings.get("max_age_days", 120)))
    all_articles = deduplicate([a for a in all_articles if a.published >= cutoff])
    write_feed(output_dir / "all.xml", "我的科研资讯", "全部科学资讯聚合", base_url, all_articles, int(settings["max_items_per_feed"]))
    featured = [{"name": "全部科研资讯", "description": "15 个来源合并并按时间排序", "file": "all.xml"}]
    topic_articles = {}
    for topic_id, topic in topic_config["topics"].items():
        selected = articles_for_topic(all_articles, topic_id, int(settings["minimum_score"]))
        topic_articles[topic_id] = selected
        filename = f"{topic_id}.xml"
        write_feed(output_dir / filename, topic["name"], topic["description"], base_url, selected, int(settings["max_items_per_feed"]))
        featured.append({"name": topic["name"], "description": f'{topic["description"]}（当前 {len(selected)} 条）', "file": filename})

    candidates = deduplicate([article for values in topic_articles.values() for article in values])
    max_new = int(os.getenv("AI_MAX_NEW_SUMMARIES", "20") or "20")
    ai_status = summarize_articles(candidates, state_dir.parent / "ai_summaries", max_new=max_new)
    summarized_all = [article for article in candidates if article.ai_summary]
    write_feed(output_dir / "all_ai.xml", "AI 科研摘要", "精选科研资讯的约300字中文结构化摘要", base_url, summarized_all, int(settings["max_items_per_feed"]))
    ai_cards = [{"name": "AI 科研摘要总订阅", "description": f"动机、方法、结论与意义（当前 {len(summarized_all)} 条）", "file": "all_ai.xml"}]
    for topic_id, topic in topic_config["topics"].items():
        selected = [article for article in topic_articles[topic_id] if article.ai_summary]
        filename = f"{topic_id}_ai.xml"
        write_feed(output_dir / filename, f'{topic["name"]} · AI摘要', f'{topic["description"]}；约300字中文摘要', base_url, selected, int(settings["max_items_per_feed"]))
        ai_cards.append({"name": f'{topic["name"]} · AI摘要', "description": f"先总结后推送（当前 {len(selected)} 条）", "file": filename})

    write_health(output_dir / "health.json", health, ai_status)
    write_index(output_dir / "index.html", ai_cards + featured + feed_cards, health, ai_status)
    print(f"generated {len(featured) + len(feed_cards) + len(ai_cards)} feeds from {len(all_articles)} unique articles; AI {ai_status}")


def cli():
    parser = argparse.ArgumentParser(description="Build personal science RSS feeds")
    parser.add_argument("--output", default="docs")
    parser.add_argument("--state", default=".cache/state")
    parser.add_argument("--base-url", default="https://example.github.io/science-rss/")
    args = parser.parse_args()
    run(Path(args.output), Path(args.state), args.base_url.rstrip("/") + "/")


if __name__ == "__main__":
    cli()
