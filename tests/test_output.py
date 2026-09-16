from datetime import datetime, timezone
from xml.etree import ElementTree

from science_rss.models import Article
from science_rss.output import deduplicate, write_feed


def make(title, link):
    return Article(title, link, "source", "Source", datetime.now(timezone.utc), "summary")


def test_deduplicate_by_canonical_link():
    assert len(deduplicate([make("A", "https://x.test/a"), make("A2", "https://x.test/a/")])) == 1


def test_generated_feed_is_valid_xml(tmp_path):
    target = tmp_path / "feed.xml"
    write_feed(target, "Test", "Description", "https://x.test", [make("Article", "https://x.test/a")])
    root = ElementTree.parse(target).getroot()
    assert root.tag == "rss"
    assert root.find("./channel/item/title").text == "Article"

