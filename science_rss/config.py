from pathlib import Path
import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(name: str):
    with (ROOT / "config" / name).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_sources():
    return load_yaml("sources.yml")["sources"]


def load_topics():
    return load_yaml("topics.yml")

