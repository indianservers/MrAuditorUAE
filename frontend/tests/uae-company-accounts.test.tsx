import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { expect, it, vi } from "vitest";
import {
  UAECompanyAccounts,
  UAECompanyAccountsResult,
} from "@/features/uae-company-accounts";

const mutate = vi.hoisted(() =>
  vi
    .fn<(request: unknown) => Promise<{ id: string }>>()
    .mockResolvedValue({ id: "prepared-company-accounts" }),
);
vi.mock("@/hooks/use-api", () => ({
  useAction: () => ({ mutateAsync: mutate, isPending: false, error: null }),
}));
const evidence = [
  {
    id: "law",
    label: "Ministry-hosted unofficial English original",
    sha256: "b08a904a9af7102804e96e70c77a975876f3f2705190ecb6bea4f39d533435af",
    scan_status: "CLEAN",
  },
  {
    id: "amendment",
    label: "Original Arabic amendment",
    sha256: "7e035b6c3616255ffe8f1c4326080bec3f270f165aa63eeb06ab4c1f481e7163",
    scan_status: "CLEAN",
  },
  {
    id: "adoption",
    label: "SYNTHETIC independent legal adoption",
    sha256: "a".repeat(64),
    scan_status: "CLEAN",
  },
  {
    id: "facts",
    label: "SYNTHETIC independently assessed company facts",
    sha256: "b".repeat(64),
    scan_status: "CLEAN",
  },
  {
    id: "quarantined",
    label: "SYNTHETIC unavailable facts",
    sha256: "c".repeat(64),
    scan_status: "QUARANTINED",
  },
];

it("binds four distinct retained roles and preserves unknown publication and legal applicability", async () => {
  mutate.mockClear();
  const created = vi.fn();
  render(
    <UAECompanyAccounts eid="E" evidence={evidence} onCreated={created} />,
  );
  fireEvent.click(
    screen.getByText(
      "Assess UAE company-law accounts and written-request duties",
    ),
  );
  expect(
    screen.getByRole("button", {
      name: "Prepare company-law accounts assessment",
    }),
  ).toBeDisabled();
  for (const [label, value] of [
    ["Company accounts assessment title", "SYNTHETIC completed year"],
    ["Company registration reference", "SYN-CCL"],
    ["Company fiscal year start", "2025-01-01"],
    ["Company fiscal year end", "2025-12-31"],
    ["Company assessed on", "2026-10-01"],
    ["Company rule adopted from", "2025-01-01"],
    ["Company rule adopted through", "2026-12-31"],
    [
      "Company operative source-chain assessment",
      "SYNTHETIC source chain is still awaiting independently verified publication",
    ],
    [
      "Company-law applicability and exclusions assessment",
      "SYNTHETIC applicability remains independently unassessed",
    ],
    [
      "Company and request evidence assessment",
      "SYNTHETIC facts remain independently assessed as unknown",
    ],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  const originals = screen.getByRole("combobox", {
    name: "Original Ministry-hosted unofficial English law PDF",
  });
  expect(within(originals).getAllByRole("option")).toHaveLength(2);
  for (const [label, value] of [
    ["Original Ministry-hosted unofficial English law PDF", "law"],
    ["Original Arabic company-law amendment PDF", "amendment"],
    ["Separate company-law operative adoption evidence", "adoption"],
    ["Separate company and request facts", "facts"],
  ])
    fireEvent.change(screen.getByRole("combobox", { name: label }), {
      target: { value },
    });
  expect(
    screen.queryByRole("option", { name: "SYNTHETIC unavailable facts" }),
  ).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", {
      name: "Prepare company-law accounts assessment",
    }),
  );
  await waitFor(() =>
    expect(created).toHaveBeenCalledWith("prepared-company-accounts"),
  );
  const request = mutate.mock.calls[0][0] as unknown as {
    path: string;
    body: Record<string, unknown>;
  };
  expect(request.path).toBe(
    "intelligence/engagements/E/uae-company-accounts-duty",
  );
  expect(request.body).toMatchObject({
    amendment_publication_date: null,
    request_received_on: null,
    responded_on: null,
    rule_chain_status: "unresolved",
    other_rule_changes: "unresolved",
    law_scope: "unresolved",
    legal_form: "unassessed",
    request_population: "unassessed",
    holding_company: "unassessed",
    law_evidence_version_id: "law",
    amendment_evidence_version_id: "amendment",
    adoption_evidence_version_id: "adoption",
    adoption_sha256: "a".repeat(64),
    fact_evidence_version_id: "facts",
    fact_sha256: "b".repeat(64),
  });
});

it("shows unknown current duties without implying a company-law exemption", () => {
  render(
    <UAECompanyAccountsResult
      row={{
        registration: "SYN-CCL",
        period_start: "2025-01-01",
        period_end: "2025-12-31",
        annual_accounts_required: null,
        annual_audit_required: null,
        response_deadline: null,
        response_complete: null,
        issues: ["AMENDMENT_PUBLICATION_NOT_ESTABLISHED"],
      }}
    />,
  );
  const summary = screen.getByRole("region", {
    name: "UAE company-law accounts summary",
  });
  expect(summary).toHaveTextContent("Annual auditUnresolved");
  expect(summary).toHaveTextContent("AMENDMENT PUBLICATION NOT ESTABLISHED");
  expect(summary).toHaveTextContent(
    "does not establish a general audit exemption",
  );
  expect(summary).toHaveTextContent("2025-01-01 to 2025-12-31");
});

it("keeps timely response separate from incomplete copies and an independently required annual audit", () => {
  render(
    <UAECompanyAccountsResult
      row={{
        annual_accounts_required: true,
        annual_audit_required: true,
        accounting_registers_required: true,
        minimum_register_retention_years: 5,
        response_required: true,
        response_deadline: "2026-09-30",
        response_timing: "RESPONDED_WITHIN_ASSESSED_PERIOD",
        response_complete: false,
        group_accounts_copy_required: true,
      }}
    />,
  );
  const summary = screen.getByRole("region", {
    name: "UAE company-law accounts summary",
  });
  expect(summary).toHaveTextContent("Annual auditRequired");
  expect(summary).toHaveTextContent(
    "Required response copies completeNot complete",
  );
  expect(summary).toHaveTextContent("RESPONDED WITHIN ASSESSED PERIOD");
  expect(summary).toHaveTextContent(
    "additional retention rules need separate assessment",
  );
});
