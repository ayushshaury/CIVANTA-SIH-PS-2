import random
from datetime import datetime, timedelta

import pandas as pd

MONSOON_CSV_PATH = "road_risk_data_monsoon.csv"
OUTPUT_PATH = "incidents_simulated.csv"

NUM_INCIDENTS = 60
SIM_START = datetime(2026, 7, 15, 0, 0, 0)
SIM_WINDOW_DAYS = 10
RANDOM_SEED = 7

INCIDENT_TYPES = ["landslide", "waterlogging", "road_blockage", "accident", "vehicle_breakdown"]
SEVERITIES = ["low", "medium", "high"]

DESCRIPTION_TEMPLATES = {
    "landslide": [
        "Debris and mud across the carriageway after heavy rainfall, partial blockage.",
        "Slope failure on the uphill side, one lane obstructed by fallen rock and soil.",
        "Small landslide reported near the road shoulder, minor debris on the surface.",
    ],
    "waterlogging": [
        "Standing water on the road surface, reduced visibility of lane markings.",
        "Section flooded after continuous rain, vehicles slowing to cross.",
        "Water pooling near a low-lying stretch, minor delays reported.",
    ],
    "road_blockage": [
        "Fallen tree branch blocking part of the carriageway.",
        "Temporary obstruction from a stalled vehicle, traffic backing up.",
        "Construction debris left on the shoulder narrowing the usable road width.",
    ],
    "accident": [
        "Minor collision between two vehicles, one lane affected.",
        "Vehicle skidded off the road on a wet curve, no major injuries reported.",
        "Rear-end collision reported near a junction, traffic slowed.",
    ],
    "vehicle_breakdown": [
        "Truck broken down on the shoulder, partially obstructing traffic.",
        "Bus stalled mid-road, drivers navigating around it.",
        "Private vehicle breakdown reported, minor congestion behind it.",
    ],
}


def risk_weight(row):
    
    score = 1.0
    score += row["historical_landslide_count"] * 2.0
    score += max(0, 5 - row["nearest_landslide_distance_km"]) * 0.5
    score += row["slope_deg"] * 0.3
    score += row["rainfall_7d_mm"] / 50.0
    return max(score, 0.1)


def pick_incident_type(rng, row):
    """Roads with landslide history/steep slope skew toward landslide incidents,
    otherwise it's close to a flat random draw across the other types."""
    weights = {t: 1.0 for t in INCIDENT_TYPES}
    if row["historical_landslide_count"] > 0 or row["slope_deg"] > 5:
        weights["landslide"] *= 3.0
    if row["rainfall_7d_mm"] > 80:
        weights["waterlogging"] *= 2.0
    types = list(weights.keys())
    probs = list(weights.values())
    return rng.choices(types, weights=probs, k=1)[0]


def pick_severity(rng, incident_type, row):
    base = {"low": 1.0, "medium": 1.0, "high": 1.0}
    if incident_type == "landslide" and row["historical_landslide_count"] >= 5:
        base["high"] *= 2.5
        base["medium"] *= 1.5
    if incident_type == "waterlogging" and row["rainfall_24h_mm"] > 30:
        base["high"] *= 1.8
    levels = list(base.keys())
    probs = list(base.values())
    return rng.choices(levels, weights=probs, k=1)[0]


def main():
    rng = random.Random(RANDOM_SEED)

    df = pd.read_csv(MONSOON_CSV_PATH)
    df.columns = [c.replace("records__", "") for c in df.columns]
    df = df[["road_id", "historical_landslide_count", "nearest_landslide_distance_km",
             "slope_deg", "rainfall_24h_mm", "rainfall_7d_mm"]].copy()

    weights = df.apply(risk_weight, axis=1).tolist()
    sampled_rows = rng.choices(df.to_dict("records"), weights=weights, k=NUM_INCIDENTS)

    incidents = []
    for i, row in enumerate(sampled_rows):
        incident_type = pick_incident_type(rng, row)
        severity = pick_severity(rng, incident_type, row)
        description = rng.choice(DESCRIPTION_TEMPLATES[incident_type])

        offset_seconds = rng.randint(0, SIM_WINDOW_DAYS * 24 * 3600)
        timestamp = SIM_START + timedelta(seconds=offset_seconds)

        incidents.append({
            "incident_id": f"SIMI-{i+1:04d}",
            "road_id": row["road_id"],
            "timestamp": timestamp.isoformat(),
            "incident_type": incident_type,
            "severity": severity,
            "description": description,
            "source": "simulated",
        })

    out_df = pd.DataFrame(incidents).sort_values("timestamp").reset_index(drop=True)
    out_df.to_csv(OUTPUT_PATH, index=False)

    print("Incident pipeline complete")
    print(f"Total incidents generated: {len(out_df)}")
    print(f"Distinct roads with an incident: {out_df['road_id'].nunique()}")
    print()
    print("Columns:", list(out_df.columns))
    print()
    print("Incident type counts:")
    print(out_df["incident_type"].value_counts())
    print()
    print("Severity counts:")
    print(out_df["severity"].value_counts())
    print()
    print("Sample rows:")
    print(out_df.head(8).to_string(index=False))


if __name__ == "__main__":
    main()
