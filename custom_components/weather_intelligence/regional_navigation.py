"""Official USACE charted-channel polygons, for weather relevance, not routing."""

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from .regional_water import (
    MAX_RESPONSE_BYTES,
    RegionalWaterCache,
    _NoRedirect,
    cell_query,
    parse_public_polygons,
)

CHANNEL_URL = "https://spatial.usace.army.mil/opjarcgis/rest/services/ehydro/ChannelReach/FeatureServer/0/query"


def parse_channels(payload: Any) -> list[dict]:
    return parse_public_polygons(
        payload, id_field="channelreachidpk", name_field="sdsfeaturename", prefix="usace_ncf:"
    )


def fetch_navigation_cell(cell: tuple[int, int]) -> list[dict]:
    query = {
        **cell_query(cell),
        "where": "1=1",
        "resultRecordCount": "2000",
        "outFields": "channelreachidpk,sdsfeaturename",
    }
    url = CHANNEL_URL + "?" + urlencode(query)
    request = Request(
        url,
        headers={
            "Accept": "application/geo+json, application/json",
            "User-Agent": "WeatherIntelligence (charted channel weather heads-ups)",
        },
    )
    with build_opener(_NoRedirect).open(request, timeout=12) as response:
        if response.geturl() != url:
            raise ValueError("Unexpected channel response URL")
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("Regional navigation response exceeds budget")
    payload = json.loads(body)
    # This provider has a smaller advertised limit than USGS. Reject a capped
    # response even if it omits the transfer-limit marker.
    if isinstance(payload, dict) and len(payload.get("features", [])) >= 2000:
        raise ValueError("Incomplete regional navigation collection")
    return parse_channels(payload)


class RegionalNavigationCache(RegionalWaterCache):
    def __init__(self, store: Any) -> None:
        super().__init__(store)
        self.source_url = CHANNEL_URL
        self.fetcher = fetch_navigation_cell

    def parse_cached(self, bodies: list[dict]) -> list[dict]:
        if any(not body["id"].startswith("usace_ncf:") for body in bodies):
            raise ValueError("Unexpected cached channel identity")
        return parse_channels(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "properties": {
                            "channelreachidpk": body["id"].removeprefix("usace_ncf:"),
                            "sdsfeaturename": body.get("name"),
                        },
                        "geometry": body["geometry"],
                    }
                    for body in bodies
                ],
            }
        )
