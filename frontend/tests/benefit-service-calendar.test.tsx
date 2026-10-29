import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { expect, it } from "vitest";
import {
  BenefitServiceCalendarDetails,
  BenefitServiceControls,
  serviceControlPayload,
} from "@/features/benefit-service-calendar";

it.each([
  { employees: "", days: "0" },
  { employees: "1", days: "" },
  { employees: "0", days: "0" },
  { employees: "1", days: "-1" },
  { employees: "1", days: "1.5" },
])("does not invent missing or fractional calendar controls %j", (value) => {
  expect(() => serviceControlPayload(value)).toThrow();
});

it("keeps employee counts separate from an explicitly assessed zero day total", () => {
  function Example() {
    const [value, setValue] = useState({ employees: "", days: "" });
    return <BenefitServiceControls value={value} onChange={setValue} />;
  }
  render(<Example />);
  expect(
    screen.getByLabelText("Independent excluded service days"),
  ).toHaveValue("");
  fireEvent.change(
    screen.getByLabelText("Independent service employee count"),
    { target: { value: "2" } },
  );
  fireEvent.change(screen.getByLabelText("Independent excluded service days"), {
    target: { value: "0" },
  });
  expect(
    screen.getByLabelText("Independent excluded service days"),
  ).toHaveValue("0");
  expect(serviceControlPayload({ employees: "2", days: "0" })).toEqual({
    employee_count: 2,
    excluded_days: 0,
  });
});

it("distinguishes a missing calendar from an explicitly recorded zero and preserves evidence references", () => {
  render(
    <BenefitServiceCalendarDetails
      rows={[
        {
          id: "E1",
          declared_excluded_service_days: 0,
          calendar_excluded_service_days: 0,
          service_calendar_state: "MATCHED",
          service_calendar_records: [
            {
              id: "ZERO",
              kind: "NO_EXCLUDED_DAYS_ASSESSED",
              days: 0,
              evidence_reference: "SYNTHETIC-ASSESSED-HR",
            },
          ],
        },
        {
          id: "E2",
          declared_excluded_service_days: 0,
          calendar_excluded_service_days: null,
          service_calendar_state: "SERVICE_CALENDAR_MISSING",
          service_calendar_records: [],
        },
      ]}
    />,
  );
  const section = screen.getByRole("region", {
    name: "Dated benefit service calendars",
  });
  expect(
    within(section).getByText("E1 · declared 0 days · dated 0 days · MATCHED"),
  ).toBeVisible();
  expect(
    within(section).getByText(
      "E2 · declared 0 days · dated Unknown days · SERVICE CALENDAR MISSING",
    ),
  ).toBeVisible();
  fireEvent.click(
    within(section).getByText("E1 · declared 0 days · dated 0 days · MATCHED"),
  );
  expect(within(section).getByText("SYNTHETIC-ASSESSED-HR")).toBeVisible();
  expect(within(section).getAllByText("No excluded interval")).toHaveLength(2);
});
