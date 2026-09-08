# Field App + GPS — Person 6 (Harsh)

**Status: Not started yet.**

## Planned scope (from team roster)

- Framework: Flutter + Dart
- GPS-based location capture
- Camera integration for geo-tagged incident photos
- Local storage via SQLite/Drift
- Field incident reporting form (offline-first)
- Offline data storage with sync-on-reconnect
- Vehicle GPS simulation (for demo purposes until real GPS trackers are integrated)

## Integration notes for when work begins

- Incident reports should follow the same shape as
  `intelligence-data/data-integration/outputs/incidents_simulated.csv`
  (join key: `road_id`) so the backend can ingest real field reports the
  same way it currently ingests simulated ones.
- GPS traces should follow the same shape as
  `intelligence-data/data-integration/outputs/gps_simulated.csv` for the
  same reason.
- Once `backend-core`  exposes ingestion APIs, this app should
  POST to those endpoints instead of writing to local CSV/SQLite only.


