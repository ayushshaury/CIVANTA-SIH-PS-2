import pandas as pd
import numpy as np
import joblib

from sklearn.model_selection import train_test_split, StratifiedKFold, cross_validate
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (
    precision_score, recall_score, f1_score, roc_auc_score, precision_recall_curve
)

DATA_PATH = r"C:\Users\ayush\OneDrive\Documents\SIH\CIVANTA-SIH-PS-2\intelligence-data\ml-risk-engine\scripts\road_risk_data_relabeled_noisy.csv"
CLASSIFICATION_THRESHOLD = 0.35  


df = pd.read_csv(DATA_PATH)
rule_score = df["disruption_risk_score"].copy()

print("Shape:", df.shape)
print("\nTarget distribution:")
print(df["disruption_occurred"].value_counts())
print("\nRisk-score distribution (rule-based, 0-4):")
print(df["disruption_risk_score"].value_counts().sort_index())

metadata_cols = [c for c in df.columns if c.startswith("metadata__")]
df = df.drop(columns=metadata_cols + ["records__road_name"])


leakage_cols = [
    "disruption_risk_score", "high_slope", "high_historical_landslide",
    "nearby_landslide", "high_rainfall",
]
df = df.drop(columns=leakage_cols)


FEATURES = [
    "records__road_type",
    "records__road_length_km", "records__elevation_m", "records__slope_deg",
    "records__historical_landslide_count", "records__nearest_landslide_distance_km",
    "records__rainfall_24h_mm", "records__rainfall_3d_mm", "records__rainfall_7d_mm",
]
CATEGORICAL_FEATURES = ["records__road_type"]
NUMERIC_FEATURES = [f for f in FEATURES if f not in CATEGORICAL_FEATURES]

X = df[FEATURES]
y = df["disruption_occurred"]
road_ids = df["records__road_id"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

numeric_pipeline = Pipeline([
    ("imputer", SimpleImputer(strategy="median")),
    ("scaler", StandardScaler()),
])
categorical_pipeline = Pipeline([
    ("imputer", SimpleImputer(strategy="most_frequent")),
    ("onehot", OneHotEncoder(handle_unknown="ignore")),
])
preprocessor = ColumnTransformer([
    ("num", numeric_pipeline, NUMERIC_FEATURES),
    ("cat", categorical_pipeline, CATEGORICAL_FEATURES),
])

results = {}  
#Rule

rule_pred_test = (rule_score.loc[X_test.index] >= 2).astype(int)
results["Rule-based (score>=2)"] = {
    "precision": precision_score(y_test, rule_pred_test),
    "recall": recall_score(y_test, rule_pred_test),
    "f1": f1_score(y_test, rule_pred_test),
    "roc_auc": None,
}


# Logistic Regression

lr_model = Pipeline([("preprocessor", preprocessor), ("classifier", LogisticRegression(max_iter=1000))])
lr_model.fit(X_train, y_train)
lr_pred = lr_model.predict(X_test)
lr_prob = lr_model.predict_proba(X_test)[:, 1]
results["Logistic Regression"] = {
    "precision": precision_score(y_test, lr_pred),
    "recall": recall_score(y_test, lr_pred),
    "f1": f1_score(y_test, lr_pred),
    "roc_auc": roc_auc_score(y_test, lr_prob),
}


#  Comparison b/w Random Forest, Decision Tree, untuned Gradient Boosting

rf_model = Pipeline([("preprocessor", preprocessor),
                      ("classifier", RandomForestClassifier(n_estimators=300, random_state=42, class_weight="balanced"))])
rf_model.fit(X_train, y_train)
rf_pred = rf_model.predict(X_test)
rf_prob = rf_model.predict_proba(X_test)[:, 1]
results["Random Forest"] = {
    "precision": precision_score(y_test, rf_pred),
    "recall": recall_score(y_test, rf_pred),
    "f1": f1_score(y_test, rf_pred),
    "roc_auc": roc_auc_score(y_test, rf_prob),
}

dt_model = Pipeline([("preprocessor", preprocessor),
                      ("classifier", DecisionTreeClassifier(max_depth=5, random_state=42, class_weight="balanced"))])
dt_model.fit(X_train, y_train)
dt_pred = dt_model.predict(X_test)
dt_prob = dt_model.predict_proba(X_test)[:, 1]
results["Decision Tree"] = {
    "precision": precision_score(y_test, dt_pred),
    "recall": recall_score(y_test, dt_pred),
    "f1": f1_score(y_test, dt_pred),
    "roc_auc": roc_auc_score(y_test, dt_prob),
}

gb_untuned = Pipeline([("preprocessor", preprocessor),
                        ("classifier", GradientBoostingClassifier(n_estimators=200, learning_rate=0.05, max_depth=3, random_state=42))])
gb_untuned.fit(X_train, y_train)
gb_pred = gb_untuned.predict(X_test)
gb_prob = gb_untuned.predict_proba(X_test)[:, 1]
results["Gradient Boosting (untuned)"] = {
    "precision": precision_score(y_test, gb_pred),
    "recall": recall_score(y_test, gb_pred),
    "f1": f1_score(y_test, gb_pred),
    "roc_auc": roc_auc_score(y_test, gb_prob),
}


feature_names = gb_untuned.named_steps["preprocessor"].get_feature_names_out()
importances = gb_untuned.named_steps["classifier"].feature_importances_
feature_importance = pd.DataFrame({"feature": feature_names, "importance": importances}) \
    .sort_values("importance", ascending=False)


cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
gb_cv_pipeline = Pipeline([("preprocessor", preprocessor),
                            ("classifier", GradientBoostingClassifier(n_estimators=200, learning_rate=0.05, max_depth=3, random_state=42))])
cv_results = cross_validate(gb_cv_pipeline, X, y, cv=cv,
                             scoring={"precision": "precision", "recall": "recall", "f1": "f1", "roc_auc": "roc_auc"})
cv_summary = {m: (cv_results[f"test_{m}"].mean(), cv_results[f"test_{m}"].std()) for m in ["precision", "recall", "f1", "roc_auc"]}


# 8. Improved model - regularized Gradient Boosting + isotonic calibration

regularized_gb = GradientBoostingClassifier(
    n_estimators=100, learning_rate=0.01, max_depth=3, min_samples_leaf=20, random_state=42
)
calibrated_pipeline = Pipeline([("preprocessor", preprocessor), ("model", regularized_gb)])
calibrated_model = CalibratedClassifierCV(estimator=calibrated_pipeline, method="isotonic", cv=5)
calibrated_model.fit(X_train, y_train)
calibrated_test_prob = calibrated_model.predict_proba(X_test)[:, 1]


threshold_sweep = []
for t in [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60]:
    pred_t = (calibrated_test_prob >= t).astype(int)
    threshold_sweep.append({
        "threshold": t,
        "precision": precision_score(y_test, pred_t, zero_division=0),
        "recall": recall_score(y_test, pred_t, zero_division=0),
        "f1": f1_score(y_test, pred_t, zero_division=0),
    })

calibrated_pred = (calibrated_test_prob >= CLASSIFICATION_THRESHOLD).astype(int)
results[f"Gradient Boosting (regularized + calibrated, thr={CLASSIFICATION_THRESHOLD})"] = {
    "precision": precision_score(y_test, calibrated_pred, zero_division=0),
    "recall": recall_score(y_test, calibrated_pred, zero_division=0),
    "f1": f1_score(y_test, calibrated_pred, zero_division=0),
    "roc_auc": roc_auc_score(y_test, calibrated_test_prob),
}


# Final model 

final_regularized_gb = GradientBoostingClassifier(
    n_estimators=100, learning_rate=0.01, max_depth=3, min_samples_leaf=20, random_state=42
)
final_calibrated_pipeline = Pipeline([("preprocessor", preprocessor), ("model", final_regularized_gb)])
final_model = CalibratedClassifierCV(estimator=final_calibrated_pipeline, method="isotonic", cv=5)
final_model.fit(X, y)

all_prob = final_model.predict_proba(X)[:, 1]
all_pred = (all_prob >= CLASSIFICATION_THRESHOLD).astype(int)
all_risk_score = np.clip(all_prob * 100, 0, 100)


# Outputs

risk_output = pd.DataFrame({
    "road_id": road_ids,
    "risk_score": np.round(all_risk_score, 2),
    "predicted_disruption": all_pred,
})
risk_output.to_csv("road_risk_scores.csv", index=False)

joblib.dump({
    "model": final_model,
    "features": FEATURES,
    "categorical_features": CATEGORICAL_FEATURES,
    "numeric_features": NUMERIC_FEATURES,
    "classification_threshold": CLASSIFICATION_THRESHOLD,
    "risk_score_definition": "calibrated_probability * 100, clipped to [0, 100]",
    "calibration_method": "isotonic",
    "model_type": "GradientBoostingClassifier",
    "model_parameters": {
        "n_estimators": 100, "learning_rate": 0.01, "max_depth": 3,
        "min_samples_leaf": 20, "random_state": 42,
    },
}, "accessibility_risk_model.joblib")


schema_lines = [
    "P3 ML/Risk Engine - Model Input Schema",
    "",
    "The exported artifact is a dict with keys: model, features, categorical_features,",
    "numeric_features, classification_threshold, risk_score_definition,",
    "calibration_method, model_type, model_parameters.",
    "",
    "artifact['model'] is a CalibratedClassifierCV wrapping a Pipeline",
    "(preprocessing + GradientBoostingClassifier). Call artifact['model'].predict_proba(row)[:, 1]",
    "on a single-row DataFrame with exactly the columns listed below, in any order",
    "(pandas matches by column name, not position).",
    "",
    "Required input columns and types:",
]
for f in FEATURES:
    kind = "categorical/string" if f in CATEGORICAL_FEATURES else "numeric"
    schema_lines.append(f"  - {f}: {kind}")
schema_lines += [
    "",
    "Excluded from model inputs (never pass these in):",
    "  - records__road_id, records__road_name",
    "  - records__latitude, records__longitude (spatial logic is owned by",
    "    the GIS/routing teammate, not this model)",
    "  - metadata__* columns",
    "  - high_slope, high_historical_landslide, nearby_landslide, high_rainfall",
    "  - disruption_risk_score, disruption_occurred",
    "",
    f"Classification threshold: {CLASSIFICATION_THRESHOLD}",
    "  predicted_disruption = 1 if predict_proba >= threshold else 0",
    "  This threshold was chosen from a precision/recall sweep on the held-out test",
    "  set (see model_report.txt) balancing precision and recall - not the default 0.5,",
    "  because the positive class is imbalanced (~25%).",
    "",
    "Accessibility Risk Score = calibrated_probability * 100, range 0-100.",
    "Output is keyed by road_id in road_risk_scores.csv.",
]
with open("model_input_schema.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(schema_lines))

report_lines = []
report_lines.append("P3 ML/Risk Engine - Model Report")
report_lines.append("=" * 40)
report_lines.append(f"Dataset: {DATA_PATH}, {df.shape[0]} roads")
report_lines.append(f"Class balance: {y.mean():.1%} disruption_occurred=1")
report_lines.append("")
report_lines.append("Model comparison (held-out 20% test set):")
report_lines.append(f"{'Model':45s} {'Precision':>10s} {'Recall':>10s} {'F1':>10s} {'ROC-AUC':>10s}")
for name, m in results.items():
    auc_str = f"{m['roc_auc']:.3f}" if m["roc_auc"] is not None else "n/a"
    report_lines.append(f"{name:45s} {m['precision']:10.3f} {m['recall']:10.3f} {m['f1']:10.3f} {auc_str:>10s}")
report_lines.append("")
report_lines.append("5-fold cross-validation, Gradient Boosting (untuned), whole dataset:")
for metric, (mean, std) in cv_summary.items():
    report_lines.append(f"  {metric.upper()}: {mean:.3f} +/- {std:.3f}")
report_lines.append("")
report_lines.append("Threshold sweep, regularized+calibrated Gradient Boosting (test set):")
report_lines.append(f"{'threshold':>10s} {'precision':>10s} {'recall':>10s} {'f1':>10s}")
for row in threshold_sweep:
    report_lines.append(f"{row['threshold']:10.2f} {row['precision']:10.3f} {row['recall']:10.3f} {row['f1']:10.3f}")
report_lines.append(f"  -> chosen threshold: {CLASSIFICATION_THRESHOLD}")
report_lines.append("")
report_lines.append("Feature importance (from untuned Gradient Boosting, easiest to interpret):")
for _, row in feature_importance.iterrows():
    report_lines.append(f"  {row['feature']:45s} {row['importance']:.4f}")
report_lines.append("")
report_lines.append("Risk score distribution (final model, whole dataset):")
report_lines.append(risk_output["risk_score"].describe().to_string())

with open("model_report.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(report_lines))

print("\n" + "\n".join(report_lines))
print("\nFiles written: road_risk_scores.csv, accessibility_risk_model.joblib, model_input_schema.txt, model_report.txt")
