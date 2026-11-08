from __future__ import annotations

import argparse
import json
from pathlib import Path


STATE_FEATURE_ID = "FI_AU_ADMINISTRATIVEUNIT_COUNTRY_FI"
SOURCE_URL = (
    "https://inspire-wfs.maanmittauslaitos.fi/inspire-wfs/au/wfs?service=WFS&version=2.0.0"
    "&request=GetFeature&typeNames=au%3AAdministrativeUnit&outputFormat=application%2Fjson"
    "&srsName=EPSG%3A4326&resourceId=FI_AU_ADMINISTRATIVEUNIT_COUNTRY_FI"
)
TERRITORIAL_SEA_SOURCE_URL = (
    "https://julkinen.traficom.fi/inspirepalvelu/avoin/wfs?service=WFS&version=2.0.0"
    "&request=GetFeature&typeNames=avoin%3ATerritorialSeaArea_L"
    "&outputFormat=application%2Fjson&srsName=EPSG%3A4326"
)


def _deduplicate_ring(ring: list[list[float]]) -> list[list[float]]:
    cleaned: list[list[float]] = []
    for position in ring:
        point = [float(position[0]), float(position[1])]
        if not cleaned or point != cleaned[-1]:
            cleaned.append(point)
    if cleaned[0] != cleaned[-1]:
        cleaned.append(cleaned[0])
    return cleaned


def _arc(ring: list[list[float]], start: int, end: int) -> list[list[float]]:
    open_ring = ring[:-1] if ring[0] == ring[-1] else ring
    if start <= end:
        return open_ring[start:end + 1]
    return open_ring[start:] + open_ring[:end + 1]


def _nearest_index(ring: list[list[float]], point: list[float]) -> int:
    return min(
        range(len(ring) - 1),
        key=lambda index: (ring[index][0] - point[0]) ** 2 + (ring[index][1] - point[1]) ** 2,
    )


def normalize(source: Path, territorial_sea_source: Path, destination: Path) -> dict:
    document = json.loads(source.read_text(encoding="utf-8"))
    territorial_sea = json.loads(territorial_sea_source.read_text(encoding="utf-8"))
    feature = next((item for item in document["features"] if item.get("id") == STATE_FEATURE_ID), None)
    if feature is None:
        raise ValueError(f"NLS response does not contain {STATE_FEATURE_ID}")
    if feature["geometry"]["type"] != "MultiPolygon":
        raise ValueError("Expected the Finland state feature to be a MultiPolygon")

    polygons = feature["geometry"]["coordinates"]
    cleaned = [[_deduplicate_ring(ring) for ring in polygon] for polygon in polygons]
    if len(cleaned) != 1 or len(cleaned[0]) != 1:
        raise ValueError("Expected the Finland state feature to contain one outer ring")

    sea_lines = [item["geometry"]["coordinates"] for item in territorial_sea["features"]]
    if not sea_lines or any(item["geometry"]["type"] != "LineString" for item in territorial_sea["features"]):
        raise ValueError("Expected Traficom territorial-sea features to be LineStrings")
    sea_points = [point for line in sea_lines for point in line]
    north_junction = max(sea_points, key=lambda point: point[1])
    east_junction = max(sea_points, key=lambda point: point[0])
    ring = cleaned[0][0]
    north_index = _nearest_index(ring, north_junction)
    east_index = _nearest_index(ring, east_junction)
    first_arc = _arc(ring, north_index, east_index)
    second_arc = _arc(ring, east_index, north_index)
    land_line = second_arc if min(point[1] for point in first_arc) < min(point[1] for point in second_arc) else first_arc
    output = {
        "type": "FeatureCollection",
        "metadata": {
            "title": "Finland land border and territorial-sea outer limit",
            "sources": [
                {
                    "provider": "National Land Survey of Finland",
                    "source_url": SOURCE_URL,
                    "source_feature_id": STATE_FEATURE_ID,
                    "role": "land_border",
                },
                {
                    "provider": "Finnish Transport and Communications Agency Traficom",
                    "source_url": TERRITORIAL_SEA_SOURCE_URL,
                    "source_layer": "avoin:TerritorialSeaArea_L",
                    "role": "territorial_sea_outer_limit",
                },
            ],
            "source_crs": "EPSG:4326",
            "retrieved": "2026-11-07",
            "license": "CC BY 4.0",
            "coverage": "Finnish land borders and the outer limit of Finland's territorial sea",
            "normalization": (
                "Consecutive duplicate NLS positions removed; NLS maritime arc replaced by the "
                "Traficom TerritorialSeaArea_L outer-limit lines."
            ),
        },
        "features": [
            {
                "type": "Feature",
                "id": "finland_land_border",
                "properties": {"kind": "land_border", "path_zone": "Land"},
                "geometry": {"type": "LineString", "coordinates": land_line},
            },
            {
                "type": "Feature",
                "id": "finland_territorial_sea_outer_limit",
                "properties": {"kind": "territorial_sea_outer_limit", "path_zone": "Cold"},
                "geometry": {"type": "MultiLineString", "coordinates": sea_lines},
            },
        ],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, separators=(",", ":")) + "\n", encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("territorial_sea_source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    output = normalize(args.source, args.territorial_sea_source, args.destination)
    land_points = len(output["features"][0]["geometry"]["coordinates"])
    sea_lines = output["features"][1]["geometry"]["coordinates"]
    print(
        f"Wrote {args.destination}: {land_points} land-border positions, "
        f"{sum(len(line) for line in sea_lines)} territorial-sea positions"
    )


if __name__ == "__main__":
    main()
