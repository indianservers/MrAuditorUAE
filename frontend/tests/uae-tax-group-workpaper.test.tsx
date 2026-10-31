import { useState } from "react";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  UAETaxGroupWorkpaper,
  UAETaxGroupResult,
} from "@/features/uae-tax-group-workpaper";
import {
  RetainedEvidenceSelect,
  type EvidenceChoice,
} from "@/features/retained-evidence-select";

const hooks = vi.hoisted(() => ({ query: vi.fn(), mutate: vi.fn() }));
vi.mock("@/hooks/use-api", () => ({
  useAPI: (path: string) => hooks.query(path),
  useAction: () => ({
    mutateAsync: hooks.mutate,
    isPending: false,
    error: null,
  }),
}));
const evidence = ["rule", "clarification", "adoption", "mapping"].map(
  (id, index) => ({
    id,
    label: `SYNTHETIC ${id}`,
    sha256: String(index + 1).repeat(64),
  }),
);
const response = (data: unknown) => ({
  data,
  error: null,
  isLoading: false,
  isFetching: false,
});

beforeEach(() => {
  hooks.mutate.mockReset().mockResolvedValue({ id: "saved-workpaper" });
  hooks.query
    .mockReset()
    .mockImplementation(() => response({ items: evidence, total: 4 }));
});

describe("UAE Tax Group workpaper", () => {
  it("shows a blocking source/reconciliation issue before review", () => {
    render(
      <UAETaxGroupResult
        prefix="intelligence/engagements/eng"
        selected="saved"
        body={{ blocked: true, tax_group_totals: [] }}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "before independent workpaper approval",
    );
  });
  it("only enables original downloads when the retained evidence receipt identifies its record", () => {
    hooks.query.mockImplementation((path: string) =>
      response({
        items: path.includes("collection_name=documents")
          ? [{ role: "fta7", version_id: "original", sha256: "a".repeat(64) }]
          : [],
        total: path.includes("collection_name=documents") ? 1 : 0,
      }),
    );
    const { rerender } = render(
      <UAETaxGroupResult
        prefix="intelligence/engagements/eng"
        selected="saved"
        body={{ tax_group_totals: [] }}
        access={{ eid: "eng", tenant: "tenant", dependencies: [] }}
      />,
    );
    fireEvent.click(
      screen.getByText("Tax Group retained documents", { selector: "summary" }),
    );
    fireEvent.click(
      screen.getByText("Original files on this page (1)", {
        selector: "summary",
      }),
    );
    expect(
      screen.getByRole("button", { name: "Download Tax Group evidence 1" }),
    ).toBeDisabled();
    rerender(
      <UAETaxGroupResult
        prefix="intelligence/engagements/eng"
        selected="saved"
        body={{ tax_group_totals: [] }}
        access={{
          eid: "eng",
          tenant: "tenant",
          dependencies: [
            { type: "evidence", id: "original", record_id: "retained-record" },
          ],
        }}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Download Tax Group evidence 1" }),
    ).toBeEnabled();
  });
  it("prepares only from four explicit retained roles and never reenters statement amounts", async () => {
    const created = vi.fn();
    render(<UAETaxGroupWorkpaper eid="eng" onCreated={created} />);
    fireEvent.click(
      screen.getByText("Prepare UAE Tax Group statement workpaper"),
    );
    const button = screen.getByRole("button", {
      name: "Prepare Tax Group workpaper",
    });
    expect(button).toBeDisabled();
    for (const [label, value] of [
      ["Tax Group workpaper title", "SYNTHETIC group workpaper"],
      ["Tax Group assessed on", "2026-10-01"],
      ["Tax Group adopted from", "2025-01-01"],
      ["Tax Group adopted through", "2026-12-31"],
      [
        "Tax Group source adoption assessment",
        "SYNTHETIC independent legal source assessment",
      ],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    for (const [label, value] of [
      ["Tax Group original FTA7 PDF", "rule"],
      ["Tax Group original CTP007 PDF", "clarification"],
      ["Tax Group legal adoption evidence", "adoption"],
      ["Tax Group retained statement mapping", "mapping"],
    ])
      fireEvent.change(screen.getByRole("combobox", { name: label }), {
        target: { value },
      });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    await waitFor(() =>
      expect(created).toHaveBeenCalledWith("saved-workpaper"),
    );
    const payload = hooks.mutate.mock.calls[0][0];
    expect(payload.path).toBe(
      "intelligence/engagements/eng/uae-tax-group-statements",
    );
    expect(payload.body).toMatchObject({
      profile: "uae-tax-group-retained-workpaper/1",
      operative_changes: "unresolved",
      mapping_evidence_version_id: "mapping",
      mapping_sha256: "4".repeat(64),
    });
    expect(payload.body).not.toHaveProperty("workpaper");
    fireEvent.change(
      screen.getByRole("combobox", {
        name: "Tax Group retained statement mapping",
      }),
      { target: { value: "adoption" } },
    );
    expect(button).toBeDisabled();
  });

  it("retains an explicitly selected original when paging beyond its choice page", () => {
    hooks.query.mockImplementation((path: string) => {
      const offset = Number(
        new URLSearchParams(path.split("?")[1]).get("offset"),
      );
      return response({
        items: offset
          ? [{ id: "later", label: "Later original", sha256: "a".repeat(64) }]
          : [
              {
                id: "earlier",
                label: "Earlier original",
                sha256: "b".repeat(64),
              },
            ],
        total: 26,
      });
    });
    function Harness() {
      const [value, setValue] = useState<EvidenceChoice | null>(null);
      return (
        <RetainedEvidenceSelect
          eid="eng"
          label="Retained source"
          value={value}
          onChange={setValue}
        />
      );
    }
    render(<Harness />);
    fireEvent.change(
      screen.getByRole("combobox", { name: "Retained source" }),
      { target: { value: "earlier" } },
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Next retained source" }),
    );
    expect(
      screen.getByRole("combobox", { name: "Retained source" }),
    ).toHaveValue("earlier");
    expect(
      screen.getByRole("option", { name: "Earlier original · earlier" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Later original · later" }),
    ).toBeInTheDocument();
  });

  it("pages each statement independently and retains exact group amounts and explicit boundaries", () => {
    hooks.query.mockImplementation((path: string) => {
      const query = new URLSearchParams(path.split("?")[1]);
      if (query.get("collection_name") !== "statements")
        return response({ items: [], total: 0 });
      const offset = Number(query.get("offset"));
      return response({
        items: Array.from({ length: offset ? 1 : 25 }, (_, i) => ({
          code: `${query.get("statement")}-${offset + i}`,
          amount: "100000000000000000019.12345678",
        })),
        total: 26,
      });
    });
    render(
      <UAETaxGroupResult
        prefix="intelligence/engagements/eng"
        selected="saved"
        body={{
          tax_group_totals: [
            {
              period: "current",
              assets: "220",
              profit_before_uae_corporate_tax: null,
            },
            {
              period: "comparative",
              assets: "150",
              profit_before_uae_corporate_tax: "70",
            },
          ],
        }}
      />,
    );
    const region = screen.getByRole("region", {
      name: "UAE Tax Group statement workpaper",
    });
    expect(region).toHaveTextContent("Not established");
    expect(region).toHaveTextContent("does not establish statutory readiness");
    const position = within(region).getByRole("region", {
      name: "current position statement",
    });
    expect(position).toHaveTextContent("Records 1–25 of 26");
    fireEvent.click(
      within(position).getByRole("button", {
        name: "Next current position statement",
      }),
    );
    expect(position).toHaveTextContent("Records 26–26 of 26");
    expect(position).toHaveTextContent("100000000000000000019.12345678");
    const profit = within(region).getByRole("region", {
      name: "current profit loss statement",
    });
    expect(profit).toHaveTextContent("Records 1–25 of 26");
    expect(profit).toHaveTextContent("profit_loss-0");
    expect(
      within(region).getByRole("region", {
        name: "comparative position statement",
      }),
    ).toHaveTextContent("Records 1–25 of 26");
  });
});
