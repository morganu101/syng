from .source import Source, available_sources
from .youtube import YoutubeSource
from .s3 import S3Source


def configure_sources(configs: dict) -> dict[str, Source]:
    configured_sources = {}
    for source, config in configs.items():
        if source in available_sources:
            configured_sources[source] = available_sources[source](config)
    return configured_sources
