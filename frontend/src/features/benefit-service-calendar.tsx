"use client";

export type ServiceControls = { employees: string; days: string };

export function serviceControlPayload(value: ServiceControls) {
  if (
    !/^\d+$/.test(value.employees) ||
    !/^\d+$/.test(value.days) ||
    Number(value.employees) < 1 ||
    Number(value.employees) > 5000 ||
    Number(value.days) > 182500000
  ) {
    throw new Error(
      "Enter the independent employee count and excluded calendar-day total, including an explicit zero where assessed.",
    );
  }
  return {
    employee_count: Number(value.employees),
    excluded_days: Number(value.days),
  };
}

export function BenefitServiceControls({
  value,
  onChange,
}: {
  value: ServiceControls;
  onChange: (value: ServiceControls) => void;
}) {
  return (
    <fieldset style={{ gridColumn: "1 / -1" }}>
      <legend>Independent service-calendar controls</legend>
      <label>
        Independent service employee count
        <input
          aria-label="Independent service employee count"
          inputMode="numeric"
          value={value.employees}
          onChange={(event) =>
            onChange({ ...value, employees: event.target.value })
          }
        />
      </label>
      <label>
        Independent excluded service days
        <input
          aria-label="Independent excluded service days"
          inputMode="numeric"
          value={value.days}
          onChange={(event) => onChange({ ...value, days: event.target.value })}
        />
      </label>
      <p>
        Provide dated exclusions or an explicit NO_EXCLUDED_DAYS_ASSESSED record
        for each selected employee. Dates use inclusive calendar days; leave
        eligibility remains an assessed input. Pension and other benefit schemes
        need their own treatment.
      </p>
    </fieldset>
  );
}

export function BenefitServiceCalendarDetails({
  rows,
}: {
  rows: Record<string, unknown>[];
}) {
  return (
    <section aria-label="Dated benefit service calendars">
      <h3>Dated service-day checks</h3>
      <p>
        These checks compare the employee declaration with the selected calendar
        source. Full individual records remain in the XLSX Benefit service
        exclusions sheet.
      </p>
      {rows.map((row) => {
        const records = Array.isArray(row.service_calendar_records)
          ? (row.service_calendar_records as Record<string, unknown>[])
          : [];
        return (
          <details key={String(row.id)}>
            <summary>
              {String(row.id)} · declared{" "}
              {String(row.declared_excluded_service_days ?? "Unknown")} days ·
              dated {String(row.calendar_excluded_service_days ?? "Unknown")}{" "}
              days · {String(row.service_calendar_state).replaceAll("_", " ")}
            </summary>
            <p>
              {records.length} retained records
              {records.length > 20 ? "; showing the first 20 here" : ""}.
            </p>
            {records.length > 0 && (
              <table>
                <thead>
                  <tr>
                    <th>Source row</th>
                    <th>Assessment</th>
                    <th>Start</th>
                    <th>End</th>
                    <th>Days</th>
                    <th>Evidence reference</th>
                  </tr>
                </thead>
                <tbody>
                  {records.slice(0, 20).map((record) => (
                    <tr key={String(record.id)}>
                      <td>{String(record.id)}</td>
                      <td>{String(record.kind).replaceAll("_", " ")}</td>
                      <td>
                        {String(
                          record.exclusion_start ?? "No excluded interval",
                        )}
                      </td>
                      <td>
                        {String(record.exclusion_end ?? "No excluded interval")}
                      </td>
                      <td>{String(record.days)}</td>
                      <td>{String(record.evidence_reference)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </details>
        );
      })}
    </section>
  );
}
