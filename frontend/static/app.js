(function () {
  const h = React.createElement;
  const { useEffect, useMemo, useState } = React;
  const glyphLine = d3
    .line()
    .x((point) => point[0])
    .y((point) => point[1]);
  const objectiveColors = ["#2374ab", "#f59e0b", "#7c3aed", "#10b981", "#ef4444", "#475569"];

  function App() {
    const [datasetId, setDatasetId] = useState("cars");
    const [datasets, setDatasets] = useState([]);
    const [catalogInfo, setCatalogInfo] = useState({ subject: "Cars", description: "", source: "" });
    const [scenarios, setScenarios] = useState([]);
    const [catalogObjectives, setCatalogObjectives] = useState([]);
    const [filterFields, setFilterFields] = useState([]);
    const [objectives, setObjectives] = useState([]);
    const [filters, setFilters] = useState({});
    const [evaluation, setEvaluation] = useState(null);
    const [selectedId, setSelectedId] = useState(null);
    const [showDominated, setShowDominated] = useState(true);
    const [layoutMode, setLayoutMode] = useState("polygon");
    const [focusKey, setFocusKey] = useState(null);
    const [viewMode, setViewMode] = useState("map");
    const [comparisonIds, setComparisonIds] = useState([]);
    const [finalId, setFinalId] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
      setEvaluation(null);
      setSelectedId(null);
      setFilters({});
      setComparisonIds([]);
      setFinalId(null);
      setFocusKey(null);
      setError(null);
      fetch(`/api/catalog/?dataset=${encodeURIComponent(datasetId)}`)
        .then((response) => response.json())
        .then((payload) => {
          setDatasets(payload.datasets || []);
          setCatalogInfo({
            subject: payload.subject || "Dataset",
            description: payload.description || "",
            source: payload.source || ""
          });
          setScenarios(payload.scenarios || []);
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
        .catch(() => setError("Could not load the selected dataset."));
    }, [datasetId]);

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
          datasetId,
          filters,
          selectedId,
          layoutMode
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
            setSelectedId(bestCandidates(payload)[0]?.id || payload.options[0].id);
          }
          setComparisonIds((current) => current.filter((id) => payload.options.some((option) => option.id === id)));
        })
        .catch((requestError) => {
          if (requestError.name !== "AbortError") {
            setError("Could not evaluate the current tradeoffs.");
          }
        });
      return () => controller.abort();
    }, [activeObjectives, datasetId, filters, selectedId, layoutMode]);

    const labelMap = useMemo(() => {
      const labels = {};
      for (const objective of catalogObjectives) {
        labels[objective.key] = objective.label;
      }
      for (const field of filterFields) {
        labels[field.key] = field.label;
      }
      return labels;
    }, [catalogObjectives, filterFields]);

    const fieldMetaMap = useMemo(() => {
      const fields = {};
      for (const objective of catalogObjectives) {
        fields[objective.key] = {
          label: objective.label,
          formatter: objective.formatter
        };
      }
      for (const field of filterFields) {
        fields[field.key] = {
          label: field.label,
          formatter: field.formatter
        };
      }
      return fields;
    }, [catalogObjectives, filterFields]);

    const itemLabel = useMemo(() => singularSubject(catalogInfo.subject), [catalogInfo.subject]);

    function reset() {
      setFilters({});
      setSelectedId(null);
      setFocusKey(null);
      setLayoutMode("polygon");
      setViewMode("map");
      setComparisonIds([]);
      setFinalId(null);
      setObjectives(
        catalogObjectives.map((objective) => ({
          key: objective.key,
          label: objective.label,
          active: objective.activeDefault,
          goal: objective.goal,
          weight: objective.weight
        }))
      );
    }

    function helpMeDecide() {
      if (!evaluation) {
        return;
      }
      const first = bestCandidates(evaluation)[0];
      if (first) {
        setSelectedId(first.id);
      }
      setViewMode("map");
      setShowDominated(true);
    }

    function applyScenario(scenario) {
      setSelectedId(null);
      setFocusKey(null);
      setViewMode("map");
      setComparisonIds([]);
      setFinalId(null);
      setFilters(scenario.filters);
      setObjectives((current) =>
        current.map((objective) => ({
          ...objective,
          active: scenario.objectives.includes(objective.key),
          goal: scenario.goals && scenario.goals[objective.key] ? scenario.goals[objective.key] : objective.goal
        }))
      );
    }

    function addForComparison(id) {
      setComparisonIds((current) => {
        if (current.includes(id)) {
          return current;
        }
        return current.length >= 6 ? current : [...current, id];
      });
    }

    function removeComparison(id) {
      setComparisonIds((current) => current.filter((candidateId) => candidateId !== id));
    }

    const selected = evaluation ? evaluation.selected : null;
    const comparisonOptions = evaluation
      ? comparisonIds.map((id) => evaluation.options.find((option) => option.id === id)).filter(Boolean)
      : [];
    const activeColorByKey = activeObjectives.reduce((colors, objective, index) => {
      colors[objective.key] = objectiveColors[index % objectiveColors.length];
      return colors;
    }, {});

    return h(
      "div",
      { className: "app-shell" },
      h(
        "aside",
        { className: "panel controls-panel" },
        h(
          "div",
          { className: "panel-heading" },
          h("div", null, h("p", { className: "eyebrow" }, catalogInfo.subject), h("h1", null, "Tradeoff Analytics")),
          h("button", { className: "icon-button text-reset", onClick: reset, title: "Reset" }, "Reset")
        ),
        h(DatasetSwitcher, { datasets, value: datasetId, onChange: setDatasetId }),
        catalogInfo.description
          ? h(
              "p",
              { className: "dataset-description" },
              catalogInfo.description,
              catalogInfo.source ? ` Source: ${catalogInfo.source}.` : ""
            )
          : null,
        h(
          "div",
          { className: "scenario-row" },
          scenarios.map((scenario) =>
            h("button", { key: scenario.name, onClick: () => applyScenario(scenario) }, scenario.name)
          )
        ),
        h("button", { className: "primary-action", onClick: helpMeDecide }, "Help Me Decide"),
        h(
          "section",
          null,
          h("h2", null, "Criteria"),
          h(
            "div",
            { className: "objective-list" },
            objectives.map((objective, index) =>
              h(ObjectiveControl, {
                key: objective.key,
                objective,
                color: activeColorByKey[objective.key] || "#cbd5df",
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
          h("h2", null, "Refine By"),
          h(
            "div",
            { className: "filter-grid" },
            filterFields.map((field) =>
              h(FilterControl, {
                key: field.key,
                field,
                value: filters[field.key] || {},
                onChange: (value) => setFilters((current) => ({ ...current, [field.key]: cleanFilter(value) }))
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
            h("h2", null, `${evaluation ? evaluation.summary.pareto : 0} best candidates`)
          ),
          h(
            "div",
            { className: "toolbar-actions" },
            h(LayoutToggle, { value: layoutMode, onChange: setLayoutMode }),
            h(ViewTabs, { value: viewMode, onChange: setViewMode }),
            h(
              "button",
              { className: "toggle-button", onClick: () => setShowDominated((value) => !value) },
              showDominated ? "Hide dominated" : "Show dominated"
            )
          )
        ),
        focusKey && evaluation
          ? h(
              "div",
              { className: "focus-strip" },
              `Focused on ${objectiveLabel(focusKey, evaluation.objectives)}. Click the anchor square again to clear.`
            )
          : null,
        evaluation && evaluation.layout && evaluation.layout.mode === "som"
          ? h(
              "div",
              { className: "layout-note" },
              "SOM layout groups options by similar trade-off profiles; anchor direction is approximate."
            )
          : null,
        evaluation && evaluation.layout && evaluation.layout.fallback
          ? h(
              "div",
              { className: "layout-warning" },
              evaluation.layout.warnings && evaluation.layout.warnings.length
                ? evaluation.layout.warnings.join(" ")
                : "SOM layout fell back to polygon."
            )
          : null,
        error ? h("div", { className: "empty-state" }, error) : null,
        evaluation
          ? h(DecisionView, {
              viewMode,
              evaluation,
              selectedId: selected ? selected.id : selectedId,
              showDominated,
              focusKey,
              comparisonIds,
              onSelect: setSelectedId,
              onFocus: (key) => setFocusKey((current) => (current === key ? null : key)),
              onAddCompare: addForComparison,
              onViewMode: setViewMode,
              labelMap,
              fieldMetaMap,
              itemLabel
            })
          : h("div", { className: "empty-state" }, "Loading decision map...")
      ),
      h(
        "aside",
        { className: "panel detail-panel" },
        evaluation
          ? h(
              React.Fragment,
              null,
              h(BestCandidateList, {
                evaluation,
                selectedId: selected ? selected.id : selectedId,
                comparisonIds,
                onSelect: setSelectedId,
                onAddCompare: addForComparison
              }),
              selected
                ? h(SelectedDetails, {
                    selected,
                    objectives: evaluation.objectives,
                    labelMap,
                    layout: evaluation.layout,
                    comparisonFull: comparisonIds.length >= 6,
                    isCompared: comparisonIds.includes(selected.id),
                    isFinal: finalId === selected.id,
                    fieldMetaMap,
                    itemLabel,
                    onAddCompare: () => addForComparison(selected.id),
                    onSetFinal: () => setFinalId(selected.id)
                  })
                : h("div", { className: "empty-state" }, `Select a ${itemLabel.toLowerCase()} to inspect its tradeoffs.`),
              h(ComparisonTray, {
                options: comparisonOptions,
                finalId,
                itemLabel,
                onRemove: removeComparison,
                onCompare: () => setViewMode("compare")
              })
            )
          : h("div", { className: "empty-state" }, "Select criteria to begin.")
      )
    );
  }

  function DatasetSwitcher({ datasets, value, onChange }) {
    if (!datasets.length) {
      return null;
    }
    return h(
      "div",
      { className: "dataset-switcher", role: "group", "aria-label": "Dataset" },
      datasets.map((dataset) =>
        h(
          "button",
          {
            key: dataset.id,
            className: value === dataset.id ? "active" : "",
            onClick: () => onChange(dataset.id),
            title: dataset.description || dataset.label
          },
          h("span", null, dataset.label),
          dataset.source ? h("small", null, dataset.source) : null
        )
      )
    );
  }

  function ObjectiveControl({ objective, color, onChange }) {
    return h(
      "div",
      { className: `objective-control ${objective.active ? "active" : ""}` },
      h(
        "label",
        { className: "check-row" },
        h("input", {
          type: "checkbox",
          checked: objective.active,
          onChange: (event) => onChange({ active: event.target.checked })
        }),
        h("span", { className: "objective-swatch", style: { background: color } }),
        h("span", null, objective.label)
      ),
      h(
        "div",
        { className: "inline-controls" },
        h(
          "select",
          { value: objective.goal, onChange: (event) => onChange({ goal: event.target.value }) },
          h("option", { value: "max" }, "Maximize"),
          h("option", { value: "min" }, "Minimize")
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
    const hasRange = Number.isFinite(field.min) && Number.isFinite(field.max) && field.max > field.min;
    const minValue = value.min === undefined ? field.min : value.min;
    const maxValue = value.max === undefined ? field.max : value.max;
    const step = filterStep(field);
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
          value: value.min === undefined ? "" : value.min,
          onChange: (event) => onChange({ ...value, min: parseOptionalNumber(event.target.value) })
        }),
        h("input", {
          type: "number",
          placeholder: field.max === null ? "Max" : String(Math.ceil(field.max)),
          value: value.max === undefined ? "" : value.max,
          onChange: (event) => onChange({ ...value, max: parseOptionalNumber(event.target.value) })
        })
      ),
      hasRange
        ? h(
            "div",
            { className: "slider-stack" },
            h("input", {
              type: "range",
              min: field.min,
              max: field.max,
              step,
              value: minValue,
              onChange: (event) =>
                onChange({ ...value, min: Math.min(Number(event.target.value), maxValue) })
            }),
            h("input", {
              type: "range",
              min: field.min,
              max: field.max,
              step,
              value: maxValue,
              onChange: (event) =>
                onChange({ ...value, max: Math.max(Number(event.target.value), minValue) })
            })
          )
        : null
    );
  }

  function ViewTabs({ value, onChange }) {
    return h(
      "div",
      { className: "view-tabs" },
      ["map", "table", "compare"].map((mode) =>
        h(
          "button",
          {
            key: mode,
            className: value === mode ? "active" : "",
            onClick: () => onChange(mode)
          },
          mode[0].toUpperCase() + mode.slice(1)
        )
      )
    );
  }

  function LayoutToggle({ value, onChange }) {
    return h(
      "div",
      { className: "layout-toggle" },
      ["polygon", "som"].map((mode) =>
        h(
          "button",
          {
            key: mode,
            className: value === mode ? "active" : "",
            onClick: () => onChange(mode)
          },
          mode === "som" ? "SOM" : "Polygon"
        )
      )
    );
  }

  function DecisionView(props) {
    if (props.viewMode === "table") {
      return h(OptionTable, props);
    }
    if (props.viewMode === "compare") {
      return h(CompareView, props);
    }
    return h(TradeoffMap, props);
  }

  function TradeoffMap({
    evaluation,
    selectedId,
    showDominated,
    focusKey,
    comparisonIds,
    onSelect,
    onFocus,
    onAddCompare
  }) {
    const [hoveredId, setHoveredId] = useState(null);
    const size = 760;
    const center = size / 2;
    const radius = 270;
    const anchorEntries = Object.entries(evaluation.anchors);
    const polygonPoints = anchorEntries
      .map(([, anchor]) => `${center + anchor.x * radius},${center + anchor.y * radius}`)
      .join(" ");
    const visibleOptions = evaluation.options
      .filter((option) => showDominated || option.pareto)
      .sort((left, right) => Number(left.pareto) - Number(right.pareto));
    const calloutOption =
      evaluation.options.find((option) => option.id === hoveredId) ||
      evaluation.options.find((option) => option.id === selectedId);

    return h(
      "svg",
      { className: "tradeoff-map", viewBox: `0 0 ${size} ${size}`, role: "img" },
      h("circle", { cx: center, cy: center, r: radius, className: "map-ring" }),
      h("polygon", { points: polygonPoints, className: "objective-polygon" }),
      anchorEntries.map(([key, anchor], index) => {
        const objective = evaluation.objectives.find((item) => item.key === key);
        const x = center + anchor.x * radius;
        const y = center + anchor.y * radius;
        const active = focusKey === key;
        return h(
          "g",
          {
            key,
            className: `anchor-group ${active ? "active" : ""}`,
            onClick: () => onFocus(key)
          },
          h("line", { x1: center, y1: center, x2: x, y2: y, className: "anchor-line" }),
          h("rect", {
            x: x - 7,
            y: y - 7,
            width: 14,
            height: 14,
            rx: 2,
            className: "anchor-square",
            style: { fill: objectiveColors[index % objectiveColors.length] }
          }),
          h(
            "text",
            {
              x,
              y,
              dx: anchor.x * 34,
              dy: anchor.y * 24,
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
        const hovered = hoveredId === option.id;
        const compared = comparisonIds.includes(option.id);
        const focusScore = focusKey ? option.scores[focusKey] || 0 : 1;
        return h(PointGlyph, {
          key: option.id,
          option,
          evaluation,
          x,
          y,
          selected,
          hovered,
          compared,
          focusScore,
          onSelect,
          onAddCompare,
          onHover: setHoveredId
        });
      }),
      calloutOption
        ? h(MapCallout, {
            option: calloutOption,
            evaluation,
            center,
            radius,
            onAddCompare,
            comparisonFull: comparisonIds.length >= 6,
            isCompared: comparisonIds.includes(calloutOption.id)
          })
        : null
    );
  }

  function PointGlyph({
    option,
    evaluation,
    x,
    y,
    selected,
    hovered,
    compared,
    focusScore,
    onSelect,
    onHover
  }) {
    const count = evaluation.objectives.length;
    const outer = selected ? 18 : option.pareto ? 15 : 11;
    const trackArc = d3.arc().innerRadius(0).outerRadius(outer);
    const opacity = option.pareto ? 0.98 : 0.34;
    const focusOpacity = 0.25 + focusScore * 0.75;
    return h(
      "g",
      {
        className: `option-node ${option.pareto ? "pareto" : "dominated"} ${selected ? "selected" : ""} ${
          hovered ? "hovered" : ""
        } ${compared ? "compared" : ""}`,
        transform: `translate(${x}, ${y})`,
        style: { opacity: Math.min(opacity, focusOpacity) },
        onClick: () => onSelect(option.id),
        onMouseEnter: () => onHover(option.id),
        onMouseLeave: () => onHover(null)
      },
      compared ? h("circle", { r: outer + 5, className: "compare-halo" }) : null,
      option.pareto ? h("circle", { r: outer + 3, className: "pareto-halo" }) : null,
      h("circle", { r: outer + 1, className: "glyph-shell" }),
      evaluation.objectives.map((objective, index) => {
        const score = option.scores[objective.key] || 0;
        const startAngle = (index * 2 * Math.PI) / count;
        const endAngle = startAngle + (2 * Math.PI) / count;
        const fillRadius = outer * score;
        const scoreArc = d3
          .arc()
          .innerRadius(0)
          .outerRadius(fillRadius)
          .startAngle(startAngle)
          .endAngle(endAngle);
        const dividerAngle = startAngle - Math.PI / 2;
        return h(
          React.Fragment,
          { key: objective.key },
          h("path", {
            d: trackArc({ startAngle, endAngle }),
            className: "glyph-track"
          }),
          fillRadius > 0.3
            ? h("path", {
                d: scoreArc(),
                className: "glyph-score",
                style: { fill: objectiveColors[index % objectiveColors.length] }
              })
            : null,
          h("line", {
            x1: 0,
            y1: 0,
            x2: Math.cos(dividerAngle) * outer,
            y2: Math.sin(dividerAngle) * outer,
            className: "glyph-divider"
          })
        );
      }),
      h("circle", { r: outer + 0.6, className: "glyph-outline" }),
      selected || hovered ? h("circle", { r: outer + 3.4, className: "selection-ring" }) : null,
      h(
        "title",
        null,
        `${option.name}. ${option.pareto ? "Best candidate" : "Dominated"}. Utility ${Math.round(
          optionUtility(option, evaluation.objectives) * 100
        )}%.`
      )
    );
  }

  function MapCallout({ option, evaluation, center, radius, onAddCompare, comparisonFull, isCompared }) {
    const x = center + option.position.x * radius;
    const y = center + option.position.y * radius;
    const boxX = x > center ? -234 : 24;
    const boxY = y > center ? -116 : 18;
    const topScores = evaluation.objectives
      .map((objective) => ({ objective, score: option.scores[objective.key] || 0 }))
      .sort((left, right) => right.score - left.score)
      .slice(0, 3);
    return h(
      "g",
      { className: "map-callout", transform: `translate(${x}, ${y})` },
      h("rect", { x: boxX, y: boxY, width: 210, height: 104, rx: 7 }),
      h("text", { x: boxX + 12, y: boxY + 21, className: "callout-title" }, truncate(option.name, 24)),
      h(
        "text",
        { x: boxX + 12, y: boxY + 39, className: "callout-status" },
        option.pareto ? "Best candidate" : "Dominated option"
      ),
      topScores.map((item, index) =>
        h(
          "text",
          { key: item.objective.key, x: boxX + 12, y: boxY + 59 + index * 14, className: "callout-score" },
          `${item.objective.label}: ${Math.round(item.score * 100)}%`
        )
      ),
      h(
        "text",
        {
          x: boxX + 132,
          y: boxY + 91,
          className: `callout-action ${comparisonFull && !isCompared ? "disabled" : ""}`,
          onClick: (event) => {
            event.stopPropagation();
            if (!comparisonFull || isCompared) {
              onAddCompare(option.id);
            }
          }
        },
        isCompared ? "Added" : "Add"
      )
    );
  }

  function OptionTable({
    evaluation,
    selectedId,
    comparisonIds,
    onSelect,
    onAddCompare,
    fieldMetaMap,
    itemLabel
  }) {
    const rows = [...evaluation.options].sort((left, right) => {
      if (left.pareto !== right.pareto) {
        return left.pareto ? -1 : 1;
      }
      return optionUtility(right, evaluation.objectives) - optionUtility(left, evaluation.objectives);
    });
    return h(
      "div",
      { className: "table-shell" },
      h(
        "table",
        { className: "option-table" },
        h(
          "thead",
          null,
          h(
            "tr",
            null,
            h("th", null, ""),
            h("th", null, itemLabel),
            h("th", null, "Fit"),
            evaluation.objectives.map((objective) => h("th", { key: objective.key }, objective.label)),
            h("th", null, "Action")
          )
        ),
        h(
          "tbody",
          null,
          rows.map((option) =>
            h(
              "tr",
              { key: option.id, className: `${selectedId === option.id ? "selected" : ""}` },
              h(
                "td",
                null,
                h("button", { className: "small-button", onClick: () => onSelect(option.id) }, "i")
              ),
              h(
                "td",
                null,
                h("strong", null, option.name),
                h("span", null, option.pareto ? "Best candidate" : "Dominated")
              ),
              h("td", null, `${Math.round(optionUtility(option, evaluation.objectives) * 100)}%`),
              evaluation.objectives.map((objective) =>
                h(
                  "td",
                  { key: objective.key },
                  h("b", null, `${Math.round((option.scores[objective.key] || 0) * 100)}%`),
                  h("span", null, formatValue(objective.key, option.values[objective.key], fieldMetaMap))
                )
              ),
              h(
                "td",
                null,
                h(
                  "button",
                  {
                    className: "small-button",
                    disabled: comparisonIds.length >= 6 && !comparisonIds.includes(option.id),
                    onClick: () => onAddCompare(option.id)
                  },
                  comparisonIds.includes(option.id) ? "Added" : "Add"
                )
              )
            )
          )
        )
      )
    );
  }

  function CompareView({ evaluation, selectedId, comparisonIds, onAddCompare, onViewMode }) {
    const optionById = new Map(evaluation.options.map((option) => [option.id, option]));
    const ids = [...new Set([selectedId, ...comparisonIds].filter(Boolean))].slice(0, 6);
    const options = ids.map((id) => optionById.get(id)).filter(Boolean);
    if (options.length < 2) {
      const candidates = bestCandidates(evaluation).slice(0, 6);
      return h(
        "div",
        { className: "compare-empty" },
        h("h3", null, "Add candidates for comparison"),
        h(
          "div",
          { className: "candidate-grid" },
          candidates.map((option) =>
            h(
              "button",
              { key: option.id, onClick: () => onAddCompare(option.id) },
              h("strong", null, option.name),
              h("span", null, `${Math.round(optionUtility(option, evaluation.objectives) * 100)}% fit`)
            )
          )
        ),
        h("button", { className: "primary-action narrow", onClick: () => onViewMode("map") }, "Back to map")
      );
    }
    return h(
      "div",
      { className: "compare-view" },
      h(ParallelComparison, { options, objectives: evaluation.objectives }),
      h(
        "div",
        { className: "comparison-matrix" },
        options.map((option, index) =>
          h(
            "article",
            { key: option.id, style: { borderTopColor: objectiveColors[index % objectiveColors.length] } },
            h("h3", null, option.name),
            h("p", null, option.description),
            evaluation.objectives.map((objective) =>
              h(
                "div",
                { key: objective.key, className: "score-row compact" },
                h("span", null, objective.label),
                h("meter", { min: 0, max: 1, value: option.scores[objective.key] || 0 }),
                h("strong", null, `${Math.round((option.scores[objective.key] || 0) * 100)}%`)
              )
            )
          )
        )
      )
    );
  }

  function ParallelComparison({ options, objectives }) {
    const width = 760;
    const height = 300;
    const padX = 64;
    const padY = 34;
    const axisGap = objectives.length <= 1 ? 0 : (width - padX * 2) / (objectives.length - 1);
    const yFor = (score) => height - padY - score * (height - padY * 2);
    return h(
      "svg",
      { className: "parallel-compare", viewBox: `0 0 ${width} ${height}` },
      objectives.map((objective, index) => {
        const x = padX + axisGap * index;
        return h(
          "g",
          { key: objective.key },
          h("line", { x1: x, y1: padY, x2: x, y2: height - padY, className: "compare-axis" }),
          h("text", { x, y: height - 10, className: "compare-axis-label", textAnchor: "middle" }, objective.label)
        );
      }),
      options.map((option, optionIndex) => {
        const points = objectives.map((objective, index) => [
          padX + axisGap * index,
          yFor(option.scores[objective.key] || 0)
        ]);
        return h(
          "g",
          { key: option.id },
          h("path", {
            d: glyphLine(points),
            className: "compare-line",
            style: { stroke: objectiveColors[optionIndex % objectiveColors.length] }
          }),
          points.map((point, index) =>
            h("circle", {
              key: `${option.id}-${objectives[index].key}`,
              cx: point[0],
              cy: point[1],
              r: 4,
              className: "compare-point",
              style: { fill: objectiveColors[optionIndex % objectiveColors.length] }
            })
          )
        );
      })
    );
  }

  function BestCandidateList({ evaluation, selectedId, comparisonIds, onSelect, onAddCompare }) {
    const candidates = bestCandidates(evaluation).slice(0, 9);
    return h(
      "section",
      { className: "best-list-section" },
      h("p", { className: "eyebrow" }, "Overview + Add for Comparison"),
      h("h2", null, "Best Candidates"),
      h(
        "div",
        { className: "best-candidate-list" },
        candidates.map((option, index) =>
          h(
            "article",
            {
              key: option.id,
              className: selectedId === option.id ? "selected" : "",
              onClick: () => onSelect(option.id)
            },
            h("span", { className: "rank" }, index + 1),
            h(
              "div",
              null,
              h("strong", null, option.name),
              h("p", null, `${Math.round(optionUtility(option, evaluation.objectives) * 100)}% fit`)
            ),
            h(
              "button",
              {
                className: "small-button",
                disabled: comparisonIds.length >= 6 && !comparisonIds.includes(option.id),
                onClick: (event) => {
                  event.stopPropagation();
                  onAddCompare(option.id);
                }
              },
              comparisonIds.includes(option.id) ? "Added" : "+"
            )
          )
        )
      )
    );
  }

  function SelectedDetails({
    selected,
    objectives,
    labelMap,
    layout,
    comparisonFull,
    isCompared,
    isFinal,
    fieldMetaMap,
    onAddCompare,
    onSetFinal
  }) {
    return h(
      "section",
      { className: "selected-section" },
      h("p", { className: "eyebrow" }, selected.pareto ? "Best candidate" : "Dominated"),
      h("h2", null, selected.name),
      h("p", { className: "description" }, selected.description),
      h("p", { className: "reason" }, selected.reason),
      layout && layout.mode === "som"
        ? h(
            "div",
            { className: "som-explanation" },
            h(
              "p",
              null,
              "SOM layout groups options by similar normalized objective profiles. Pareto status and recommendations are computed from objective scores, not from map position."
            )
          )
        : null,
      h(
        "div",
        { className: "detail-actions" },
        h(
          "button",
          { onClick: onAddCompare, disabled: comparisonFull && !isCompared },
          isCompared ? "Added for comparison" : "Add for comparison"
        ),
        h("button", { onClick: onSetFinal, className: isFinal ? "final active" : "final" }, isFinal ? "Final" : "Set Final")
      ),
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
        h("h3", null, "Raw Attributes"),
        h(
          "dl",
          { className: "attribute-grid" },
          Object.entries(selected.values).map(([key, value]) =>
            h(
              "div",
              { key },
              h("dt", null, fieldMetaMap[key]?.label || labelMap[key] || key),
              h("dd", null, formatValue(key, value, fieldMetaMap))
            )
          )
        )
      ),
      h(
        "section",
        null,
        h("h3", null, "Consider This Alternative"),
        h(
          "div",
          { className: "alternative-list" },
          selected.alternatives.length === 0
            ? h("p", { className: "description" }, "No higher-gain alternatives under the current objectives.")
            : selected.alternatives.slice(0, 4).map((alternative) =>
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

  function ComparisonTray({ options, finalId, itemLabel, onRemove, onCompare }) {
    return h(
      "section",
      { className: "comparison-tray" },
      h("h3", null, `Candidates Added for Comparison (${options.length}/6)`),
      options.length === 0
        ? h("p", { className: "description" }, `Add ${itemLabel.toLowerCase()}s from the graph, table, or candidate list.`)
        : h(
            "div",
            { className: "comparison-chip-list" },
            options.map((option) =>
              h(
                "button",
                { key: option.id, className: option.id === finalId ? "finalized" : "" },
                h("span", null, option.name),
                h(
                  "b",
                  {
                    onClick: (event) => {
                      event.stopPropagation();
                      onRemove(option.id);
                    }
                  },
                  "x"
                )
              )
            )
          ),
      h("button", { className: "primary-action narrow", disabled: options.length < 2, onClick: onCompare }, "Compare")
    );
  }

  function radarPath(option, evaluation, radius) {
    const points = evaluation.objectives.map((objective) => {
      const anchor = evaluation.anchors[objective.key];
      const score = option.scores[objective.key] || 0;
      return [anchor.x * score * radius, anchor.y * score * radius];
    });
    if (points.length > 2) {
      points.push(points[0]);
    }
    return glyphLine(points) || "";
  }

  function bestCandidates(evaluation) {
    return [...evaluation.options]
      .filter((option) => option.pareto)
      .sort((left, right) => optionUtility(right, evaluation.objectives) - optionUtility(left, evaluation.objectives));
  }

  function optionUtility(option, objectives) {
    const totalWeight = objectives.reduce((sum, objective) => sum + Math.max(0, objective.weight || 1), 0) || 1;
    return (
      objectives.reduce(
        (sum, objective) => sum + (option.scores[objective.key] || 0) * Math.max(0, objective.weight || 1),
        0
      ) / totalWeight
    );
  }

  function objectiveLabel(key, objectives) {
    return objectives.find((objective) => objective.key === key)?.label || key;
  }

  function formatValue(key, value, fieldMetaMap = {}) {
    if (value === null || value === undefined || value === "") {
      return "Missing";
    }
    const number = Number(value);
    if (!Number.isFinite(number)) {
      return String(value);
    }
    const formatter = fieldMetaMap[key]?.formatter;
    if (formatter) {
      const formatted = applyFormatter(number, formatter);
      if (formatted) {
        return formatted;
      }
    }
    if (key === "price") {
      return `$${Math.round(number).toLocaleString()}`;
    }
    if (key === "MPGCombined") {
      return `${number.toLocaleString(undefined, { maximumFractionDigits: 1 })} MPG`;
    }
    if (key === "averageRating") {
      return `${number.toLocaleString(undefined, { maximumFractionDigits: 1 })} stars`;
    }
    if (key === "power") {
      return `${Math.round(number).toLocaleString()} hp`;
    }
    if (key === "engineSize") {
      return `${number.toLocaleString(undefined, { maximumFractionDigits: 1 })} L`;
    }
    return number.toLocaleString(undefined, { maximumFractionDigits: 1 });
  }

  function applyFormatter(number, formatter) {
    if (formatter === "year") {
      return String(Math.round(number));
    }
    if (formatter === "km") {
      return `${Math.round(number).toLocaleString()} km`;
    }
    if (formatter === "kWh/100km") {
      return `${number.toLocaleString(undefined, { maximumFractionDigits: 1 })} kWh/100 km`;
    }
    if (formatter === "kWh") {
      return `${number.toLocaleString(undefined, { maximumFractionDigits: 1 })} kWh`;
    }
    if (formatter === "kW") {
      return `${number.toLocaleString(undefined, { maximumFractionDigits: 1 })} kW`;
    }
    if (formatter === "V") {
      return `${Math.round(number).toLocaleString()} V`;
    }

    const decimals = formatter.match(/number:(\d+)/);
    const prefix = formatter.match(/taPrefix:'([^']+)'/);
    const suffix = formatter.match(/taSuffix:'([^']+)'/);
    if (decimals || prefix || suffix) {
      return `${prefix ? prefix[1] : ""}${number.toLocaleString(undefined, {
        minimumFractionDigits: 0,
        maximumFractionDigits: decimals ? Number(decimals[1]) : 1
      })}${suffix ? suffix[1] : ""}`;
    }
    return null;
  }

  function filterStep(field) {
    const formatter = field.formatter || "";
    if (formatter.includes("number:1") || ["kWh/100km", "kWh", "kW"].includes(formatter)) {
      return 0.1;
    }
    return 1;
  }

  function singularSubject(subject) {
    const normalized = String(subject || "Options").trim();
    if (/electric vehicles/i.test(normalized)) {
      return "Vehicle";
    }
    if (/cars/i.test(normalized)) {
      return "Car";
    }
    if (normalized.endsWith("ies")) {
      return `${normalized.slice(0, -3)}y`;
    }
    if (normalized.endsWith("s")) {
      return normalized.slice(0, -1);
    }
    return normalized || "Option";
  }

  function cleanFilter(value) {
    const cleaned = {};
    if (value.min !== undefined) {
      cleaned.min = value.min;
    }
    if (value.max !== undefined) {
      cleaned.max = value.max;
    }
    return cleaned;
  }

  function parseOptionalNumber(value) {
    if (value.trim() === "") {
      return undefined;
    }
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }

  function truncate(value, length) {
    return value.length <= length ? value : `${value.slice(0, length - 1)}...`;
  }

  ReactDOM.createRoot(document.getElementById("root")).render(h(App));
})();
