import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { GroupSourceLineage } from "@/features/group-source-lineage";

it("pages full current and comparative populations independently without dropping later source fields", () => {
  render(
    <GroupSourceLineage
      currency="AED"
      current={Array.from({ length: 201 }, (_, i) => ({
        engagement_id: `CURRENT-${i + 1}`,
        run_id: `RUN-${i + 1}`,
        source_amount: "12345678901234567890.12345678",
        rate: "1.2345678910",
        translated: "0",
        rate_source: "SYNTHETIC independently retained source",
        ...(i === 200 ? { later_field: "LAST-SOURCE-FIELD" } : {}),
      }))}
      comparative={Array.from({ length: 26 }, (_, i) => ({
        engagement_id: `PRIOR-${i + 1}`,
        rate: "2",
        translated: null,
      }))}
    />,
  );
  const current = screen.getByRole("region", {
    name: "Current source accounts",
  });
  const prior = screen.getByRole("region", {
    name: "Comparative source accounts",
  });
  expect(
    within(current).getByRole("columnheader", { name: "later field" }),
  ).toBeVisible();
  for (let i = 0; i < 8; i++)
    fireEvent.click(
      within(current).getByRole("button", {
        name: "Next current source accounts",
      }),
    );
  expect(current).toHaveTextContent("Records 201–201 of 201");
  expect(
    within(current).getByRole("cell", { name: "CURRENT-201" }),
  ).toBeVisible();
  expect(
    within(current).getByRole("cell", {
      name: "LAST-SOURCE-FIELD",
    }),
  ).toBeVisible();
  expect(
    within(current).getByRole("cell", {
      name: "12345678901234567890.12345678",
    }),
  ).toBeVisible();
  expect(within(current).getByRole("cell", { name: "0" })).toBeVisible();
  expect(
    within(current).getByRole("button", {
      name: "Next current source accounts",
    }),
  ).toBeDisabled();
  expect(within(prior).getByRole("cell", { name: "PRIOR-1" })).toBeVisible();
  fireEvent.click(
    within(prior).getByRole("button", {
      name: "Next comparative source accounts",
    }),
  );
  expect(within(prior).getByRole("cell", { name: "PRIOR-26" })).toBeVisible();
  expect(
    within(prior).getByRole("cell", { name: "Not supplied" }),
  ).toBeVisible();
  expect(
    within(current).getByRole("cell", { name: "CURRENT-201" }),
  ).toBeVisible();
});

it("reports unstructured rows and preserves valid rows instead of silently declaring a complete table", () => {
  render(
    <GroupSourceLineage
      currency="INR"
      current={[
        null,
        "SYNTHETIC-unstructured",
        { source_amount: "0", translated: "0", extra: false },
      ]}
      comparative={undefined}
    />,
  );
  const current = screen.getByRole("region", {
    name: "Current source accounts",
  });
  expect(within(current).getByRole("alert")).toHaveTextContent(
    "2 source records are not structured rows",
  );
  expect(
    within(current).getByRole("columnheader", {
      name: "Translated amount (INR)",
    }),
  ).toBeVisible();
  expect(within(current).getByRole("cell", { name: "false" })).toBeVisible();
  expect(
    screen.getByRole("region", { name: "Comparative source accounts" }),
  ).toHaveTextContent("No structured records retained");
});
