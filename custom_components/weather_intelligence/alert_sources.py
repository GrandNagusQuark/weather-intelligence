"""Short provenance labels for selectable official and derived alerts."""


def alert_source_note(event: str) -> str:
    if event == "radar_hail":
        return "Weather Intelligence · NOAA MRMS radar estimates"
    if event == "severe_weather_awareness":
        return "Weather Intelligence · NWS Storm Prediction Center outlooks and discussions"
    if event.startswith("avalanche "):
        return "Regional avalanche forecasters · distributed by NWS"
    if event == "air quality alert":
        return "Issuing air-quality agency · distributed by NWS"
    if event in {"earthquake warning", "volcano warning", "fire warning"}:
        return "Issuing public-safety agency · distributed by NWS"
    return "National Weather Service (NWS)"
