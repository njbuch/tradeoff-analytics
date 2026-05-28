# Tradeoff Analytics

A local, open-source prototype inspired by IBM Watson Tradeoff Analytics for exploring car choices across competing objectives.

The app uses Django for the backend web/API engine, a plain Python decision engine for normalization, Pareto analysis, recommendations, and anchored polygon projection, plus a minimal React/D3 frontend served by Django.

## Setup

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
cd frontend
npm.cmd install --cache ..\.npm-cache
```

If `minisom` source installation stalls in build isolation on Windows, install the backend packages with:

```powershell
.\.venv\Scripts\python -m pip install wheel==0.43.0 numpy==1.26.4
.\.venv\Scripts\python -m pip install --no-build-isolation minisom==2.3.2
.\.venv\Scripts\python -m pip install Django==5.0.7
```

## Run

Start the local app in the foreground:

```powershell
.\.venv\Scripts\python scripts\dev_server.py run
```

Open http://127.0.0.1:8000.

In a normal local terminal, you can also start it detached, then check or stop it:

```powershell
.\.venv\Scripts\python scripts\dev_server.py start
.\.venv\Scripts\python scripts\dev_server.py status
.\.venv\Scripts\python scripts\dev_server.py stop
```

The frontend is served by Django from `frontend/static`, using the local React and D3 browser bundles installed under `frontend/node_modules`.

## Layout Modes

`Polygon` is the default deterministic layout. Objective anchors are placed around a regular polygon, and each car is positioned by a weighted average of its normalized objective scores.

`SOM` uses `minisom` to group cars with similar normalized objective profiles. It uses a fixed random seed, deterministic jitter for overlapping winners, and a semantic orientation pass so the SOM is aligned toward the same objective anchors as the polygon view. The displayed anchors stay the same in both modes.

SOM is approximate: it is useful for exploration and neighborhood discovery, but Pareto status, dominance, recommendations, and gain/loss explanations are computed directly from objective scores and remain authoritative. If there are fewer than 10 feasible cars, fewer than 2 active objectives, or SOM training fails, the API falls back to polygon layout and returns a warning.

The backend computes decisions before layouts:

```text
raw cars -> filters -> normalized scores -> Pareto/dominance -> recommendations -> layout coordinates
```

Changing `layoutMode` may change `x`, `y`, anchors, warnings, and layout diagnostics. It must not change feasible cars, normalized scores, Pareto status, dominance explanations, selected-car details, or recommendations.

## Tests

```powershell
.\.venv\Scripts\python manage.py test
cd frontend
npm.cmd run check
```

## API

- `GET /api/catalog/` returns objective metadata, filter metadata, and the source car catalog.
- `POST /api/evaluate/` accepts active objectives, hard filters, and an optional selected car id, then returns normalized scores, Pareto flags, dominated-by explanations, map positions, and recommendations.
- `POST /api/evaluate/` also accepts `layoutMode: "polygon" | "som"` and returns layout diagnostics under `layout`.

## Known Limitations

- SOM maps can rotate or flip without orientation; this prototype applies a deterministic semantic orientation transform, but anchor direction remains approximate.
- SOM distances are approximate neighborhood cues, not proof of dominance or recommendation quality.
- The authoritative decision logic is the normalized objective scoring, Pareto frontier, and gain/loss recommendation engine.
