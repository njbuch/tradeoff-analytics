(function () {
  const h = React.createElement;
  const { useEffect, useMemo, useState } = React;
  const glyphLine = d3
    .line()
    .x((point) => point[0])
    .y((point) => point[1]);

  const scenarios = [
    {
      name: "Balanced",
      objectives: ["price", "MPGCombined", "averageRating"],
      filters: { price: { max: 60000 }, MPGCombined: { min: 24 } }
    },
    {
      name: "Performance",
      objectives: ["price", "power", "engineSize"],
      filters: { price: { max: 90000 } }
    },
    {
      name: "Efficient",
      objectives: ["price", "MPGCombined", "averageRating"],
      filters: { MPGCombined: { min: 30 }, price: { max: 50000 } }
    }
  ];

  function App() {
    const [catalogObjectives, setCatalogObjectives] = useState([]);
    const [filterFields, setFilterFields] = useState([]);
    const [objectives, setObjectives] = useState([]);
    const [filters, setFilters] = useState({});
    const [evaluation, setEvaluation] = useState(null);
    const [selectedId, setSelectedId] = useState(null);
    const [showDominated, setShowDominated] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
      fetch("/api/catalog/")
        .then((response) => response.json())
        .then((payload) => {
          setCatalogObjectives(payload.objectives);
          setFilterFields(payload.filters);
          setObjectives(
            payload.objectives.map((objective) => ({
              key: objective.key,
              label: objective.label,
              active: objective.activeDefault,
              goal: objective.goal,
              weight: objective.weight
            }))
          );
        })
        .catch(() => setError("Could not load the car catalog."));
    }, []);

    const activeObjectives = useMemo(
      () => objectives.filter((objective) => objective.active).slice(0, 6),
      [objectives]
    );

    useEffect(() => {
      if (activeObjectives.length === 0) {
        return;
      }
      const controller = new AbortController();
      fetch("/api/evaluate/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          objectives: activeObjectives.map(({ key, goal, weight }) => ({ key, goal, weight })),
          filters,
          selectedId
        }),
        signal: controller.signal
      })
        .then((response) => {
          if (!response.ok) {
            throw new Error("Evaluation failed.");
          }
          return response.json();
        })
        .then((payload) => {
          setEvaluation(payload);
          setError(null);
          if (!payload.selected && payload.options.length > 0) {
            setSelectedId(payload.options[0].id);
          }
        })
        .catch((requestError) => {
          if (requestError.name !== "AbortError") {
            setError("Could not evaluate the current tradeoffs.");
          }
        });
      return () => controller.abort();
    }, [activeObjectives, filters, selectedId]);

    function reset() {
      setFilters({});
      setSelectedId(null);
      setObjectives(
        catalogObjectives.map((objective) => ({
          key: objective.key,
          label: objective.label,
          active: objective.activeDefault,
          goal: objective.goal,
          weight: 1
        }))
      );
    }

    function applyScenario(scenario) {
      setSelectedId(null);
      setFilters(scenario.filters);
      setObjectives((current) =>
        current.map((objective) => ({
          ...objective,
          active: scenario.objectives.includes(objective.key),
          goal: objective.key === "price" ? "min" : objective.goal
        }))
      );
    }

    return h(
      "div",
      { className: "app-shell" },
      h(
        "aside",
        { className: "panel controls-panel" },
        h(
          "div",
          { className: "panel-heading" },
          h("div", null, h("p", { className: "eyebrow" }, "Cars"), h("h1", null, "Tradeoff Analytics")),
          h("button", { className: "icon-button", onClick: reset, title: "Reset" }, "Reset")
        ),
        h(
          "div",
          { className: "scenario-row" },
          scenarios.map((scenario) =>
            h("button", { key: scenario.name, onClick: () => applyScenario(scenario) }, scenario.name)
          )
        ),
        h(
          "section",
          null,
          h("h2", null, "Objectives"),
          h(
            "div",
            { className: "objective-list" },
            objectives.map((objective) =>
              h(ObjectiveControl, {
                key: objective.key,
                objective,
                onChange: (next) =>
                  setObjectives((current) =>
                    current.map((item) => (item.key === objective.key ? { ...item, ...next } : item))
                  )
              })
            )
          )
        ),
        h(
          "section",
          null,
          h("h2", null, "Filters"),
          h(
            "div",
            { className: "filter-grid" },
            filterFields.map((field) =>
              h(FilterControl, {
                key: field.key,
                field,
                value: filters[field.key] || {},
                onChange: (value) => setFilters((current) => ({ ...current, [field.key]: value }))
              })
            )
          )
        )
      ),
      h(
        "main",
        { className: "map-panel" },
        h(
          "div",
          { className: "map-toolbar" },
          h(
            "div",
            null,
            h(
              "p",
              { className: "eyebrow" },
              `Feasible ${evaluation ? evaluation.summary.feasible : 0} of ${evaluation ? evaluation.summary.total : 0}`
            ),
            h("h2", null, `${evaluation ? evaluation.summary.pareto : 0} Pareto options`)
          ),
          h(
            "button",
            { className: "toggle-button", onClick: () => setShowDominated((value) => !value) },
            showDominated ? "Hide dominated" : "Show dominated"
          )
        ),
        error ? h("div", { className: "empty-state" }, error) : null,
        evaluation
          ? h(TradeoffMap, {
              evaluation,
              selectedId: evaluation.selected ? evaluation.selected.id : selectedId,
              showDominated,
              onSelect: setSelectedId
            })
          : h("div", { className: "empty-state" }, "Loading decision map...")
      ),
      h(
        "aside",
        { className: "panel detail-panel" },
        evaluation && evaluation.selected
          ? h(SelectedDetails, { selected: evaluation.selected, objectives: evaluation.objectives })
          : h("div", { className: "empty-state" }, "Select a car to inspect its tradeoffs.")
      )
    );
  }

  function ObjectiveControl({ objective, onChange }) {
    return h(
      "div",
      { className: "objective-control" },
      h(
        "label",
        { className: "check-row" },
        h("input", {
          type: "checkbox",
          checked: objective.active,
          onChange: (event) => onChange({ active: event.target.checked })
        }),
        h("span", null, objective.label)
      ),
      h(
        "div",
        { className: "inline-controls" },
        h(
          "select",
          { value: objective.goal, onChange: (event) => onChange({ goal: event.target.value }) },
          h("option", { value: "max" }, "Max"),
          h("option", { value: "min" }, "Min")
        ),
        h(
          "label",
          { className: "weight-control" },
          h("span", null, objective.weight.toFixed(1)),
          h("input", {
            type: "range",
            min: "0.25",
            max: "3",
            step: "0.25",
            value: objective.weight,
            onChange: (event) => onChange({ weight: Number(event.target.value) })
          })
        )
      )
    );
  }

  function FilterControl({ field, value, onChange }) {
    return h(
      "div",
      { className: "filter-control" },
      h("span", null, field.label),
      h(
        "div",
        { className: "range-inputs" },
        h("input", {
          type: "number",
          placeholder: field.min === null ? "Min" : String(Math.floor(field.min)),
          value: value.min || "",
          onChange: (event) => onChange({ ...value, min: parseOptionalNumber(event.target.value) })
        }),
        h("input", {
          type: "number",
          placeholder: field.max === null ? "Max" : String(Math.ceil(field.max)),
          value: value.max || "",
          onChange: (event) => onChange({ ...value, max: parseOptionalNumber(event.target.value) })
        })
      )
    );
  }

  function TradeoffMap({ evaluation, selectedId, showDominated, onSelect }) {
    const size = 720;
    const center = size / 2;
    const radius = 260;
    const anchorEntries = Object.entries(evaluation.anchors);
    const polygonPoints = anchorEntries
      .map(([, anchor]) => `${center + anchor.x * radius},${center + anchor.y * radius}`)
      .join(" ");
    const visibleOptions = evaluation.options.filter((option) => showDominated || option.pareto);

    return h(
      "svg",
      { className: "tradeoff-map", viewBox: `0 0 ${size} ${size}`, role: "img" },
      h("circle", { cx: center, cy: center, r: radius, className: "map-ring" }),
      h("polygon", { points: polygonPoints, className: "objective-polygon" }),
      anchorEntries.map(([key, anchor]) => {
        const objective = evaluation.objectives.find((item) => item.key === key);
        const x = center + anchor.x * radius;
        const y = center + anchor.y * radius;
        return h(
          "g",
          { key },
          h("line", { x1: center, y1: center, x2: x, y2: y, className: "anchor-line" }),
          h("circle", { cx: x, cy: y, r: 5, className: "anchor-dot" }),
          h(
            "text",
            {
              x,
              y,
              dx: anchor.x * 24,
              dy: anchor.y * 16,
              className: "anchor-label",
              textAnchor: "middle",
              dominantBaseline: "middle"
            },
            objective ? objective.label : key
          )
        );
      }),
      visibleOptions.map((option) => {
        const x = center + option.position.x * radius;
        const y = center + option.position.y * radius;
        const selected = selectedId === option.id;
        return h(
          "g",
          {
            key: option.id,
            className: `option-node ${option.pareto ? "pareto" : "dominated"} ${selected ? "selected" : ""}`,
            transform: `translate(${x}, ${y})`,
            onClick: () => onSelect(option.id)
          },
          h("circle", { r: selected ? 16 : option.pareto ? 12 : 8 }),
          h("path", { d: glyphPath(option, evaluation), className: "glyph" }),
          h("title", null, `${option.name}: ${option.pareto ? "Pareto" : "Dominated"}`)
        );
      })
    );
  }

  function glyphPath(option, evaluation) {
    const points = evaluation.objectives.map((objective) => {
      const anchor = evaluation.anchors[objective.key];
      const score = option.scores[objective.key] || 0;
      return [anchor.x * score * 12, anchor.y * score * 12];
    });
    if (points.length > 2) {
      points.push(points[0]);
    }
    return glyphLine(points) || "";
  }

  function SelectedDetails({ selected, objectives }) {
    return h(
      "div",
      null,
      h("p", { className: "eyebrow" }, selected.pareto ? "Pareto frontier" : "Dominated"),
      h("h2", null, selected.name),
      h("p", { className: "description" }, selected.description),
      h("p", { className: "reason" }, selected.reason),
      h(
        "section",
        null,
        h("h3", null, "Objective Scores"),
        h(
          "div",
          { className: "score-list" },
          objectives.map((objective) =>
            h(
              "div",
              { key: objective.key, className: "score-row" },
              h("span", null, objective.label),
              h("meter", { min: 0, max: 1, value: selected.scores[objective.key] || 0 }),
              h("strong", null, `${Math.round((selected.scores[objective.key] || 0) * 100)}%`)
            )
          )
        )
      ),
      h(
        "section",
        null,
        h("h3", null, "Attributes"),
        h(
          "dl",
          { className: "attribute-grid" },
          Object.entries(selected.values).map(([key, value]) =>
            h("div", { key }, h("dt", null, key), h("dd", null, value === null ? "Missing" : String(value)))
          )
        )
      ),
      h(
        "section",
        null,
        h("h3", null, "Alternatives"),
        h(
          "div",
          { className: "alternative-list" },
          selected.alternatives.length === 0
            ? h("p", { className: "description" }, "No higher-gain alternatives under the current objectives.")
            : selected.alternatives.map((alternative) =>
                h(
                  "article",
                  { key: alternative.id },
                  h("strong", null, alternative.name),
                  h("p", null, alternative.explanation)
                )
              )
        )
      )
    );
  }

  function parseOptionalNumber(value) {
    if (value.trim() === "") {
      return undefined;
    }
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }

  ReactDOM.createRoot(document.getElementById("root")).render(h(App));
})();
