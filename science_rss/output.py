import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from feedgen.feed import FeedGenerator

from .models import Article


def deduplicate(articles: List[Article]) -> List[Article]:
    selected = {}
    for article in articles:
        current = selected.get(article.uid)
        if not current or article.published > current.published:
            selected[article.uid] = article
    return sorted(selected.values(), key=lambda a: a.published, reverse=True)


def write_feed(path: Path, title: str, description: str, link: str, articles: List[Article], limit: int = 100):
    fg = FeedGenerator()
    fg.id(link)
    fg.title(title)
    fg.link(href=link, rel="alternate")
    fg.description(description)
    fg.language("zh-CN")
    for article in reversed(deduplicate(articles)[:limit]):
        entry = fg.add_entry(order="prepend")
        entry.id(article.link)
        entry.title(article.title)
        entry.link(href=article.link)
        entry.published(article.published)
        content = article.ai_summary or article.summary
        basis = ""
        if article.ai_summary and article.summary_basis == "abstract":
            basis = "<p><em>说明：未能提取完整正文，本摘要依据标题与公开摘要生成。</em></p>"
        meta = f"来源：{article.source_name}"
        if article.topic_scores:
            meta += "｜主题分数：" + ", ".join(f"{k}={v}" for k, v in article.topic_scores.items())
        entry.description(f"<div>{content}</div>{basis}<p>{meta}</p>")
    fg.rss_file(str(path), pretty=True)


def write_health(path: Path, records: List[dict], ai_status: dict = None):
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "sources": records, "ai_summary": ai_status or {"enabled": False}}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_index(path: Path, feeds: List[dict], health: List[dict], ai_status: dict = None):
    healthy = sum(1 for x in health if x["status"] == "ok")
    rows = "".join(
        f'<tr><td>{x["name"]}</td><td><span class="{x["status"]}">{"正常" if x["status"] == "ok" else "使用缓存"}</span></td><td>{x["items"]}</td><td>{x["duration_ms"]} ms</td></tr>'
        for x in health
    )
    cards = "".join(
        f'<a class="card" href="{x["file"]}"><strong>{x["name"]}</strong><span>{x["description"]}</span><code>{x["file"]}</code></a>'
        for x in feeds
    )
    ai_status = ai_status or {"enabled": False}
    ai_text = f"AI 摘要已启用：本轮新生成 {ai_status.get('created', 0)} 篇，缓存命中 {ai_status.get('cached', 0)} 篇。" if ai_status.get("enabled") else "AI 摘要尚未启用：请配置 OPENAI_API_KEY。"
    doc = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>科研 RSS</title>
<style>:root{{--bg:#f6f7fb;--ink:#18202b;--muted:#677386;--brand:#3157d5;--ok:#08783f;--warn:#a65b00}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);font:15px/1.6 system-ui,sans-serif;color:var(--ink)}}main{{max-width:1050px;margin:auto;padding:42px 22px}}h1{{font-size:34px;margin-bottom:4px}}.lead{{color:var(--muted);margin-top:0}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px;margin:26px 0}}.card{{background:white;padding:18px;border-radius:14px;text-decoration:none;color:inherit;box-shadow:0 4px 18px #1f294012;display:flex;flex-direction:column;gap:7px}}.card:hover{{outline:2px solid #3157d533}}.card span{{color:var(--muted)}}code{{color:var(--brand)}}.panel{{background:white;border-radius:14px;padding:18px;overflow:auto}}table{{border-collapse:collapse;width:100%}}th,td{{padding:10px;border-bottom:1px solid #e8ebf1;text-align:left}}.ok{{color:var(--ok)}}.cached{{color:var(--warn)}}small{{color:var(--muted)}}</style></head>
<body><main><h1>科研 RSS</h1><p class="lead">15 个科学资讯源 · AI 科研摘要 · 自动分类 · 失败回退 · 每小时更新</p><div class="panel"><strong>{ai_text}</strong></div><div class="grid">{cards}</div><section class="panel"><h2>抓取状态</h2><p>{healthy}/{len(health)} 个来源本次抓取正常；失败来源自动保留上次成功内容。</p><table><thead><tr><th>来源</th><th>状态</th><th>条目</th><th>耗时</th></tr></thead><tbody>{rows}</tbody></table><p><small>机器可读报告：<a href="health.json">health.json</a></small></p></section></main></body></html>'''
    path.write_text(doc, encoding="utf-8")
