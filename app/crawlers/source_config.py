from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DEFAULT_SOURCE_CONFIG = Path("configs/disaster_sources.yaml")


@dataclass(frozen=True)
class DisasterSource:
    source_id: str
    source_name: str
    level: str
    disaster_types: list[str]
    url: str
    enabled: bool
    fetch_interval_minutes: int
    parser_type: str
    priority: int = 100
    notes: str = ""
    urls: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DisasterSource":
        known = {
            "source_id",
            "source_name",
            "level",
            "disaster_types",
            "url",
            "urls",
            "enabled",
            "fetch_interval_minutes",
            "parser_type",
            "priority",
            "notes",
        }
        url_list = list(data.get("urls") or [])
        # If single url is provided and not already in urls, prepend it.
        single_url = str(data.get("url") or "")
        if single_url and single_url not in url_list:
            url_list.insert(0, single_url)
        return cls(
            source_id=str(data["source_id"]),
            source_name=str(data["source_name"]),
            level=str(data.get("level") or "unknown"),
            disaster_types=list(data.get("disaster_types") or []),
            url=str(data.get("url") or ""),
            enabled=bool(data.get("enabled", False)),
            fetch_interval_minutes=int(data.get("fetch_interval_minutes") or 60),
            parser_type=str(data.get("parser_type") or "generic_html"),
            priority=int(data.get("priority") or 100),
            notes=str(data.get("notes") or ""),
            urls=url_list,
            extra={key: value for key, value in data.items() if key not in known},
        )


def load_sources(path: Path | str = DEFAULT_SOURCE_CONFIG, enabled_only: bool = False) -> list[DisasterSource]:
    config_path = Path(path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    sources = [DisasterSource.from_dict(item) for item in data.get("sources", [])]
    if enabled_only:
        sources = [source for source in sources if source.enabled]
    return sorted(sources, key=lambda item: item.priority)


def get_source(source_id: str, path: Path | str = DEFAULT_SOURCE_CONFIG) -> DisasterSource:
    for source in load_sources(path):
        if source.source_id == source_id:
            return source
    raise KeyError(f"未找到数据源: {source_id}")
