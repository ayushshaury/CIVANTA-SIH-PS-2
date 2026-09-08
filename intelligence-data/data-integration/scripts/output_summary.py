

import pandas as pd

MONSOON_CSV_PATH = "road_risk_data_monsoon.csv"
GPS_CSV_PATH = "gps_simulated.csv"
INCIDENTS_CSV_PATH = "incidents_simulated.csv"


def section(title):
    print()
    print(f"=== {title} ===")


def main():
    monsoon = pd.read_csv(MONSOON_CSV_PATH)
    monsoon.columns = [c.replace("records__", "") for c in monsoon.columns]
    gps = pd.read_csv(GPS_CSV_PATH)
    incidents = pd.read_csv(INCIDENTS_CSV_PATH)

    all_road_ids = set(monsoon["road_id"])
    gps_road_ids = set(gps["road_id"])
    incident_road_ids = set(incidents["road_id"])

    section("Original dataset")
    print(f"road_risk_data_monsoon.csv: {len(monsoon)} rows, {monsoon['road_id'].nunique()} unique road_id")

    section("GPS simulation (gps_simulated.csv)")
    print(f"Rows: {len(gps)}")
    print(f"Roads covered: {len(gps_road_ids)} / {len(all_road_ids)}")
    print(f"Columns: {list(gps.columns)}")
    print("Sample rows:")
    print(gps.head(3).to_string(index=False))

    section("Incident pipeline (incidents_simulated.csv)")
    print(f"Rows: {len(incidents)}")
    print(f"Roads with at least one incident: {len(incident_road_ids)} / {len(all_road_ids)}")
    print(f"Columns: {list(incidents.columns)}")
    print("Sample rows:")
    print(incidents.head(3).to_string(index=False))

    section("Join key check")
    unmatched_gps = gps_road_ids - all_road_ids
    unmatched_incidents = incident_road_ids - all_road_ids
    print(f"GPS road_ids not found in original dataset: {len(unmatched_gps)}")
    print(f"Incident road_ids not found in original dataset: {len(unmatched_incidents)}")
    print("(both should be 0 - every simulated road_id must already exist in road_risk_data_monsoon.csv)")

    section("Handoff notes")
    print("- Both files are clearly labeled source=simulated, not real telemetry/reports.")
    print("- Join key for both files is road_id, matching road_risk_data_monsoon.csv / roads_with_terrain.csv.")
    print("- No backend/API/database code included - these are flat CSVs for a backend dev to load.")


if __name__ == "__main__":
    main()
