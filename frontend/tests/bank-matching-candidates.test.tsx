import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { BankMatchingCandidates } from "@/features/bank-matching-candidates";

vi.mock("@/hooks/use-api", () => ({
  useAPI: (path: string, enabled = true) => {
    const query = new URL(path, "http://synthetic.invalid").searchParams;
    const number = (value: number) => String(value).padStart(3, "0");
    if (!enabled) return { data: undefined, error: null, isFetching: false };
    if (path.includes("/bank-candidates?")) {
      const offset = Number(query.get("offset") || 0);
      return {
        data: {
          left: {
            id: query.get("left_id"),
            reference: "BOOK-REFERENCE",
            counterparty: "شركة ألف",
            date: "2026-06-01",
            amount: "1",
            currency: "AED",
          },
          items: Array.from({ length: Math.min(25, 121 - offset) }, (_, i) => ({
            id: `R${number(offset + i)}`,
            reference: `REF-${offset + i}`,
            machine_match:
              offset + i === 0
                ? {
                    left_ids: ["L-OTHER"],
                    rule: "REFERENCE",
                    auditor_status: "PROPOSED",
                  }
                : null,
            counterparty: "شركة ألف",
            date: "2026-06-01",
            amount: "99999999999999999999.12345678",
            currency: "AED",
          })),
          total: 121,
        },
        error: null,
        isFetching: false,
      };
    }
    const offset = Number(query.get("ambiguity_offset") || 0);
    return {
      data: {
        body: {
          ambiguous: Array.from(
            { length: Math.min(25, 121 - offset) },
            (_, i) => ({
              left_id: `L${number(offset + i)}`,
              candidate_count: 121,
            }),
          ),
        },
      },
      error: null,
      isFetching: false,
    };
  },
}));

it("pages every ambiguous book item and every candidate independently", () => {
  render(
    <BankMatchingCandidates
      prefix="/intelligence/E"
      selected="RESULT"
      initial={[{ left_id: "L000", candidate_count: 121 }]}
      total={121}
      contract="indexed-transaction-candidates/1"
    />,
  );
  for (let i = 0; i < 4; i++)
    fireEvent.click(
      screen.getByRole("button", { name: "Next ambiguous items" }),
    );
  expect(
    screen.getByText("Ambiguous items 101–121 of 121"),
  ).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "Inspect L120 · 121 candidates" }),
  );
  expect(screen.getByText(/Book item L120/)).toHaveTextContent(
    "BOOK-REFERENCE",
  );
  for (let i = 0; i < 4; i++)
    fireEvent.click(screen.getByRole("button", { name: "Next candidates" }));
  expect(screen.getByText("Candidates 101–121 of 121")).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "R120" })).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Next candidates" }),
  ).toBeDisabled();
});

it("retains exact source text and amounts and resets candidate paging for a new book item", () => {
  render(
    <BankMatchingCandidates
      prefix="/intelligence/E"
      selected="RESULT"
      initial={[{ left_id: "L000", candidate_count: 121 }]}
      total={121}
      contract="indexed-transaction-candidates/1"
    />,
  );
  expect(
    screen.getByRole("cell", { name: "L-OTHER · REFERENCE · PROPOSED" }),
  ).toBeInTheDocument();
  expect(
    screen.getAllByRole("cell", { name: "No machine proposal" }),
  ).toHaveLength(24);
  expect(
    screen.getAllByRole("cell", {
      name: "99999999999999999999.12345678",
    }),
  ).toHaveLength(25);
  expect(screen.getByText(/These are possible alternatives/)).toHaveTextContent(
    "does not select, match or approve",
  );
  fireEvent.click(screen.getByRole("button", { name: "Next candidates" }));
  fireEvent.click(
    screen.getByRole("button", { name: "Inspect L001 · 121 candidates" }),
  );
  expect(screen.getByText("Candidates 1–25 of 121")).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "R000" })).toBeInTheDocument();
});

it("requires historical incomplete candidates to be regenerated", () => {
  render(
    <BankMatchingCandidates
      prefix="/intelligence/E"
      selected="OLD"
      initial={[{ left_id: "L000", candidate_ids: ["R000"] }]}
      total={1}
    />,
  );
  expect(screen.getByRole("note")).toHaveTextContent(
    "Recalculate this historical matching result",
  );
  expect(
    screen.queryByRole("button", { name: /Inspect/ }),
  ).not.toBeInTheDocument();
});
