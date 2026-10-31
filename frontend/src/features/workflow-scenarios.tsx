"use client";

import { useState } from "react";

export type ReferenceScenario = {
  id: string;
  title: string;
  workflow: string;
  country: string;
  expected: Record<string, unknown>;
};

function countryName(country: string) {
  return (
    ({ AE: "UAE", IN: "India" } as Record<string, string>)[country] || country
  );
}

export function WorkflowScenarios({
  scenarios,
  country,
  workflow,
  workflowTitles,
}: {
  scenarios: ReferenceScenario[];
  country: string;
  workflow: string;
  workflowTitles: Record<string, string>;
}) {
  const [query, setQuery] = useState("");
  const [countries, setCountries] = useState("engagement");
  const [workflows, setWorkflows] = useState("selected");
  const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const visible = scenarios.filter((scenario) => {
    const searchable = [
      scenario.id,
      scenario.title,
      scenario.workflow,
      workflowTitles[scenario.workflow] || "",
      scenario.country,
      countryName(scenario.country),
    ]
      .join(" ")
      .toLocaleLowerCase();
    return (
      (countries === "all" || scenario.country === country) &&
      (workflows === "all" || scenario.workflow === workflow) &&
      terms.every((term) => searchable.includes(term))
    );
  });

  return (
    <details style={{ margin: "16px 0" }}>
      <summary>
        {scenarios.length} synthetic reference scenarios across country
        workflows
      </summary>
      <p>
        These scenarios test source comparisons and evidence controls. They do
        not establish complete statutory coverage or live registry integrations.
        Browsing another country does not change this engagement or its rules.
      </p>
      <div
        className="grid"
        style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}
      >
        <label>
          Search reference scenarios
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label>
          Reference scenario countries
          <select
            aria-label="Reference scenario countries"
            value={countries}
            onChange={(event) => setCountries(event.target.value)}
          >
            <option value="engagement">
              Engagement country — {countryName(country)}
            </option>
            <option value="all">All countries</option>
          </select>
        </label>
        <label>
          Reference scenario workflows
          <select
            aria-label="Reference scenario workflows"
            value={workflows}
            onChange={(event) => setWorkflows(event.target.value)}
          >
            <option value="selected">Selected workflow</option>
            <option value="all">All workflows</option>
          </select>
        </label>
      </div>
      <p role="status">
        {visible.length} of {scenarios.length} reference scenarios shown
      </p>
      {visible.length === 0 ? (
        <p>
          No reference scenarios match these filters. This does not establish a
          nil business population.
        </p>
      ) : (
        <ul aria-label="Reference scenarios">
          {visible.map((scenario) => (
            <li key={scenario.id}>
              <strong>
                {scenario.id} · {scenario.title}
              </strong>
              <p>
                {countryName(scenario.country)} ·{" "}
                {workflowTitles[scenario.workflow] || scenario.workflow}
              </p>
              <details>
                <summary>Expected synthetic outcome for {scenario.id}</summary>
                <pre
                  style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
                >
                  {JSON.stringify(scenario.expected, null, 2)}
                </pre>
              </details>
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}
