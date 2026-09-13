import csv
from pathlib import Path

from .database import SessionLocal
from .models import RiskScore


CSV_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "intelligence-data"
    / "ml-risk-engine"
    / "outputs"
    / "road_risk_scores.csv"
)


def import_risk_data():
    db = SessionLocal()

    try:
        with open(CSV_PATH, "r", newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)

            count = 0

            for row in reader:
                road_id = row["road_id"].strip()

                existing = (
                    db.query(RiskScore)
                    .filter(RiskScore.road_id == road_id)
                    .first()
                )

                if existing:
                    existing.risk_score = float(row["risk_score"])
                    existing.predicted_disruption = int(
                        row["predicted_disruption"]
                    )
                else:
                    risk = RiskScore(
                        road_id=road_id,
                        risk_score=float(row["risk_score"]),
                        predicted_disruption=int(row["predicted_disruption"]),
                    )

                    db.add(risk)

                count += 1

            db.commit()

            print(f"Imported {count} risk records successfully.")

    finally:
        db.close()


if __name__ == "__main__":
    import_risk_data()
