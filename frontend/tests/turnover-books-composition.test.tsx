import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { TurnoverBooksComposition } from "@/features/turnover-books-composition";

const mutate = vi.hoisted(() => vi.fn().mockResolvedValue({ id: "combined" }));
vi.mock("@/hooks/use-api", () => ({
  useAction: () => ({ mutateAsync: mutate, isPending: false, error: null }),
}));
const source = (id: string, changes = {}) => ({
  id,
  label: id,
  kind: "workflow-source",
  table_type: "turnover-amounts",
  freshness: "CURRENT",
  review_status: "REVIEWED",
  ...changes,
});

describe("Reviewed turnover books", () => {
  it.each([
    ["AE", "AED"],
    ["IN", "INR"],
  ])(
    "combines eligible %s schedules only against explicit controls",
    async (country, currency) => {
      mutate.mockClear();
      const created = vi.fn();
      render(
        <TurnoverBooksComposition
          eid="eng"
          country={country}
          onCreated={created}
          sources={[
            source("one"),
            source("two", { allowed_source_roles: ["books"] }),
            source("stale", { freshness: "STALE" }),
            source("pending", { review_status: "UNVERIFIED" }),
            source("filed", { allowed_source_roles: ["return"] }),
            source("composed", {
              parser_version: "turnover-books-composition/1",
            }),
          ]}
        />,
      );
      fireEvent.click(
        screen.getByText("Combine reviewed turnover book schedules"),
      );
      const sources = screen.getByLabelText(
        "Reviewed turnover book components",
      ) as HTMLSelectElement;
      expect(sources.options).toHaveLength(2);
      Array.from(sources.options).forEach((o) => {
        o.selected = true;
      });
      fireEvent.change(sources);
      for (const [name, value] of [
        [`Independent combined signed turnover (${currency})`, "-5.00000001"],
        [
          "Combined books scope and disjointness assessment",
          "Distinct registration schedules with signed controls",
        ],
        ["Combined turnover books title", "SYNTHETIC combined books"],
      ])
        fireEvent.change(screen.getByLabelText(name), { target: { value } });
      const button = screen.getByRole("button", {
        name: "Prepare combined turnover books",
      });
      expect(button).toBeDisabled();
      fireEvent.change(
        screen.getByLabelText("Independent combined book row count"),
        { target: { value: "2" } },
      );
      fireEvent.click(button);
      await waitFor(() => expect(created).toHaveBeenCalledWith("combined"));
      expect(mutate.mock.calls[0][0]).toMatchObject({
        path: "intelligence/engagements/eng/turnover-books-composition",
        body: {
          source_ids: ["one", "two"],
          expected_rows: 2,
          currency,
          expected_amount: "-5.00000001",
        },
      });
    },
  );
});
