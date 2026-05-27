Build a prototype inspired by IBM Watson Tradeoff Analytics.

Reference demo:
https://www.youtube.com/watch?v=3tthszOKxDQ

Goal:
Create an open-source, local implementation of a multi-objective decision-support UI for choosing cars, without IBM Watson or any proprietary backend.

Core behavior:
- Load a catalog of cars with numeric and categorical attributes.
- Let users choose active objectives and set whether each objective should be minimized or maximized.
- Let users apply hard filters, e.g. max price, min MPG, min safety rating.
- Normalize active objectives to [0, 1], where higher is always better.
- Compute the Pareto frontier / non-dominated options after every interaction.
- Hide or de-emphasize dominated options, but allow users to inspect why they were dominated.
- Show options in an objective-anchored polygon/triangle map.
- For 3 active objectives, the map should be triangular.
- For N active objectives, place objective anchors on a regular polygon.
- Position each option using a weighted/barycentric projection from its normalized objective scores.
- Each option should have a small radial/pie/radar glyph showing objective satisfaction.
- Selecting an option should show:
  - raw attributes
  - normalized scores
  - why it is on/off the Pareto frontier
  - alternatives with gain/loss explanations
  - “consider this alternative” recommendations.

Technical approach:
- Use ordinary libraries only.
- Suggested stack:
  - Python FastAPI backend
  - pandas or Polars for data
  - numpy for normalization and Pareto computation
  - React + TypeScript frontend
  - D3 for polygon map and glyphs
  - optional DuckDB for local data querying
- Do not use Watson, IBM APIs, LLM APIs, or cloud services.

Implementation details:
1. Data model
   - cars.json with fields:
     id, name, make, model, price, mpg, safety, horsepower, acceleration, cargo_volume, reliability, emissions, etc.
   - objectives metadata:
     key, label, type, goal=min|max|target, weight, min, max, formatter.

2. Normalize objectives
   - For max objective:
     score = (x - min_x) / (max_x - min_x)
   - For min objective:
     score = (max_x - x) / (max_x - min_x)
   - For target objective:
     score = 1 - abs(x - target) / max_distance
   - Clip to [0, 1].
   - Missing values should be handled gracefully.

3. Pareto frontier
   - Option A dominates B if A is >= B on all active normalized objective scores and > B on at least one.
   - Compute boolean pareto flag for every feasible option.
   - Return dominated_by candidates for each dominated option.

4. Alternative recommendations
   - For selected option s and candidate x:
     gain = sum(max(0, x_j - s_j) * weight_j)
     loss = sum(max(0, s_j - x_j) * weight_j)
     ratio = gain / (loss + epsilon)
   - Recommend high-gain, low-loss candidates.
   - Explain in plain language:
     “Car X gives +12% safety and +8% MPG for -4% horsepower and +3% price.”

5. Objective-anchored map
   - For m active objectives, place anchors around a unit circle:
     angle_j = 2*pi*j/m
     anchor_j = (cos(angle_j), sin(angle_j))
   - For each option:
     weights = normalized_scores / sum(normalized_scores)
     position = weights @ anchors
   - Pareto options should be visually prominent.
   - Dominated options should be muted or toggleable.

6. UI
   - Left panel: filters, objective toggles, goal direction, weights.
   - Center: polygon map with objective anchors and option glyphs.
   - Right panel: selected option details, explanations, alternatives.
   - Add reset button and sample scenarios.

7. Deliverables
   - Working app
   - README with setup instructions
   - Unit tests for normalization, Pareto dominance, and recommendations
   - Seed car dataset
   - Clear separation between backend decision logic and frontend rendering.

Research context:
- IBM Watson Tradeoff Analytics was a decision-support service for conflicting objectives.
- It used Pareto analysis, computational geometry, graph/optimization ideas, and objective-space visualization.
- Related research: semantically enhanced self-organizing maps for multi-objective Pareto frontiers.
- First implementation should use deterministic anchored polygon projection rather than SOM.
- SOM/UMAP can be added later as an optional layout mode.
- 