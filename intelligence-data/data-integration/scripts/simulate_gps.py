
import json
import math
import random
from datetime import datetime, timedelta

import pandas as pd

GEOJSON_PATH = "roads_with_terrain.geojson"
OUTPUT_PATH = "gps_simulated.csv"

SAMPLE_INTERVAL_SEC = 10          
SIM_START = datetime(2026, 7, 15, 6, 0, 0) 
RANDOM_SEED = 42


BASE_SPEED_KMPH = {
    "trunk": 45,
    "trunk_link": 35,
    "primary": 40,
    "primary_link": 30,
    "secondary": 30,
    "secondary_link": 25,
    "tertiary": 20,
    "tertiary_link": 15,
}
DEFAULT_SPEED_KMPH = 20


def haversine_km(lon1, lat1, lon2, lat2):
    """Great-circle distance between two lon/lat points, in km."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def build_cumulative_distances(coords):
    """coords is a list of [lon, lat]. Returns list of cumulative km from the start."""
    cum = [0.0]
    for i in range(1, len(coords)):
        lon1, lat1 = coords[i - 1]
        lon2, lat2 = coords[i]
        cum.append(cum[-1] + haversine_km(lon1, lat1, lon2, lat2))
    return cum


def interpolate_point(coords, cum_dist, target_dist):
    """Find the lon/lat at target_dist km along the path defined by coords/cum_dist."""
    total = cum_dist[-1]
    if total == 0:
        lon, lat = coords[0]
        return lon, lat
    target_dist = min(max(target_dist, 0.0), total)

    for i in range(1, len(cum_dist)):
        if cum_dist[i] >= target_dist:
            seg_start_dist = cum_dist[i - 1]
            seg_len = cum_dist[i] - seg_start_dist
            frac = 0.0 if seg_len == 0 else (target_dist - seg_start_dist) / seg_len
            lon1, lat1 = coords[i - 1]
            lon2, lat2 = coords[i]
            lon = lon1 + frac * (lon2 - lon1)
            lat = lat1 + frac * (lat2 - lat1)
            return lon, lat

    return coords[-1][0], coords[-1][1]


def simulate_road_trace(road_id, road_type, coords, sim_start_time):
    """Simulate one vehicle pass along a single road's geometry."""
    cum_dist = build_cumulative_distances(coords)
    total_km = cum_dist[-1]

    base_speed = BASE_SPEED_KMPH.get(road_type, DEFAULT_SPEED_KMPH)
    speed_kmph = max(5.0, base_speed * random.uniform(0.85, 1.15))

    if total_km == 0:
       
        lon, lat = coords[0]
        return [{
            "road_id": road_id,
            "vehicle_id": f"SIMV-{road_id.split('/')[-1]}",
            "point_seq": 0,
            "timestamp": sim_start_time.isoformat(),
            "latitude": lat,
            "longitude": lon,
            "speed_kmph": round(speed_kmph, 2),
            "distance_along_road_km": 0.0,
            "source": "simulated",
        }]

    travel_time_sec = (total_km / speed_kmph) * 3600
    num_points = max(2, int(travel_time_sec // SAMPLE_INTERVAL_SEC) + 1)

    rows = []
    for i in range(num_points):
        t_sec = i * SAMPLE_INTERVAL_SEC
        t_sec = min(t_sec, travel_time_sec)
        dist_km = (t_sec / 3600) * speed_kmph
        lon, lat = interpolate_point(coords, cum_dist, dist_km)
        rows.append({
            "road_id": road_id,
            "vehicle_id": f"SIMV-{road_id.split('/')[-1]}",
            "point_seq": i,
            "timestamp": (sim_start_time + timedelta(seconds=t_sec)).isoformat(),
            "latitude": lat,
            "longitude": lon,
            "speed_kmph": round(speed_kmph, 2),
            "distance_along_road_km": round(dist_km, 4),
            "source": "simulated",
        })
    return rows


def main():
    random.seed(RANDOM_SEED)

    with open(GEOJSON_PATH) as f:
        geojson = json.load(f)

    all_rows = []
    skipped = []

    for feature in geojson["features"]:
        props = feature["properties"]
        road_id = props["road_id"]
        road_type = props.get("highway") or "unclassified"
        geometry = feature["geometry"]

        if geometry["type"] != "LineString":
            skipped.append((road_id, geometry["type"]))
            continue

        coords = geometry["coordinates"]
        if len(coords) < 1:
            skipped.append((road_id, "empty_coords"))
            continue

        rows = simulate_road_trace(road_id, road_type, coords, SIM_START)
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    df.to_csv(OUTPUT_PATH, index=False)

    print("GPS simulation complete")
    print(f"Roads processed: {df['road_id'].nunique()}")
    print(f"Total GPS points generated: {len(df)}")
    print(f"Skipped features: {len(skipped)}")
    if skipped:
        print(f"  (first few: {skipped[:5]})")
    print()
    print("Columns:", list(df.columns))
    print()
    print("Sample rows:")
    print(df.head(8).to_string(index=False))
    print()
    print("Points per road (summary stats):")
    print(df.groupby("road_id").size().describe())


if __name__ == "__main__":
    main()
