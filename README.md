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

## Tests

```powershell
.\.venv\Scripts\python manage.py test
cd frontend
npm.cmd run check
```

## API

- `GET /api/catalog/` returns objective metadata, filter metadata, and the source car catalog.
- `POST /api/evaluate/` accepts active objectives, hard filters, and an optional selected car id, then returns normalized scores, Pareto flags, dominated-by explanations, map positions, and recommendations.
