import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { expect, it, vi } from "vitest";
import {
  IndiaCompanyScope,
  IndiaCompanyScopeResult,
} from "@/features/india-company-scope";

const mutate = vi.hoisted(() =>
  vi
    .fn<(request: unknown) => Promise<{ id: string }>>()
    .mockResolvedValue({ id: "scope" }),
);
vi.mock("@/hooks/use-api", () => ({
  useAction: () => ({ mutateAsync: mutate, isPending: false, error: null }),
}));

it("retains all eight roles and submits unknown facts as null and exact INR text", async () => {
  const created = vi.fn();
  render(
    <IndiaCompanyScope
      eid="E"
      evidence={Array.from({ length: 8 }, (_, i) => ({
        id: `S${i}`,
        label: `SYNTHETIC retained source ${i}`,
        sha256: String(i).repeat(64),
        scan_status: "CLEAN",
      })).concat([
        {
          id: "Q",
          label: "Quarantined",
          sha256: "a".repeat(64),
          scan_status: "QUARANTINED",
        },
      ])}
      onCreated={created}
    />,
  );
  fireEvent.click(
    screen.getByText(
      "Assess India company audit, CARO and IFC reporting scope",
    ),
  );
  const button = screen.getByRole("button", {
    name: "Prepare India reporting scope assessment",
  });
  expect(button).toBeDisabled();
  for (const [label, value] of [
    ["India scope assessment title", "SYNTHETIC company scope"],
    ["India company registration reference", "SYN-IN"],
    ["India financial period start", "2025-04-01"],
    ["India financial period end", "2026-03-31"],
    ["India report assessment date", "2026-06-30"],
    ["India rules adopted from", "2025-04-01"],
    ["India rules adopted through", "2026-06-30"],
    ["India company facts assessment", "SYNTHETIC unassessed company facts"],
    [
      "India legal source-chain adoption assessment",
      "SYNTHETIC unresolved source chain",
    ],
    ["Paid-up capital at balance sheet date (INR)", "100000000.01"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  const labels = [
    "Companies Act original PDF",
    "Small-company definition original PDF",
    "CARO 2020 original order PDF",
    "SO 4588(E) CARO commencement original PDF",
    "GSR 583(E) IFC original PDF",
    "SO 2218(E) IFC corrigendum original PDF",
    "Separate India legal adoption evidence",
    "Separate India company facts evidence",
  ];
  labels.forEach((label, i) =>
    fireEvent.change(screen.getByLabelText(label), {
      target: { value: `S${i}` },
    }),
  );
  expect(
    screen.queryByRole("option", { name: "Quarantined" }),
  ).not.toBeInTheDocument();
  expect(
    within(screen.getByLabelText(labels[0])).getAllByRole("option"),
  ).toHaveLength(2);
  expect(button).toBeEnabled();
  fireEvent.click(button);
  await waitFor(() => expect(created).toHaveBeenCalledWith("scope"));
  const request = mutate.mock.calls[0][0] as {
    body: {
      facts: Record<string, unknown>;
      documents: unknown[];
      source_chain_status: string;
    };
  };
  expect(request.body.documents).toHaveLength(8);
  expect(request.body.source_chain_status).toBe("unresolved");
  expect(request.body.facts).toMatchObject({
    country: "IN",
    is_indian_company: null,
    is_private_company: null,
    small_paid_up_capital: "100000000.01",
    preceding_financial_year_turnover: null,
    financial_statements_filing_default: null,
  });
});

it("displays independent duty answers and unresolved values without declaring audit completion", () => {
  render(
    <IndiaCompanyScopeResult
      row={{
        entity_reference: "SYN-IN",
        period_start: "2025-04-01",
        period_end: "2026-03-31",
        small_company: true,
        companies_act_section139_audit: true,
        caro2020_applies: false,
        section143_3_i_ifc_reporting: null,
        basis: {
          small_company_prescribed_limits_source:
            "G.S.R.700(E), 15 September 2022",
          small_company_capital_limit_inr: "40000000",
          small_company_preceding_year_turnover_limit_inr: "400000000",
        },
      }}
    />,
  );
  const region = screen.getByRole("region", {
    name: "India company reporting scope summary",
  });
  expect(region).toHaveTextContent("G.S.R.700(E), 15 September 2022");
  expect(region).toHaveTextContent("Capital limit (INR): 40000000");
  expect(
    within(region).getByText("Companies Act section 139 audit")
      .nextElementSibling,
  ).toHaveTextContent("Yes, within assessed scope");
  expect(
    within(region).getByText("CARO 2020 applies").nextElementSibling,
  ).toHaveTextContent("No, within assessed scope");
  expect(
    within(region).getByText("Section 143(3)(i) IFC reporting")
      .nextElementSibling,
  ).toHaveTextContent("Unresolved");
});
