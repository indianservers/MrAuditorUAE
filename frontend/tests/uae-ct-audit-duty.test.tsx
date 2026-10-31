import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { UAECTAuditDuty } from "@/features/uae-ct-audit-duty";

const mutate = vi.hoisted(() => vi.fn().mockResolvedValue({ id: "duty" }));
vi.mock("@/hooks/use-api", () => ({
  useAction: () => ({ mutateAsync: mutate, isPending: false, error: null }),
}));
describe("UAE corporate-tax audited statements", () => {
  it("retains explicit unknowns, AED strings and separate clean rule and fact evidence", async () => {
    const created = vi.fn();
    render(
      <UAECTAuditDuty
        eid="eng"
        evidence={[
          {
            id: "clarification",
            label: "Original CTP007",
            scan_status: "CLEAN",
            sha256: "d".repeat(64),
          },
          {
            id: "rule",
            label: "Original MD84",
            scan_status: "CLEAN",
            sha256: "a".repeat(64),
          },
          {
            id: "facts",
            label: "Assessed company facts",
            scan_status: "CLEAN",
            sha256: "b".repeat(64),
          },
          {
            id: "bad",
            label: "Quarantined",
            scan_status: "QUARANTINED",
            sha256: "c".repeat(64),
          },
        ]}
        onCreated={created}
      />,
    );
    fireEvent.click(
      screen.getByText("Assess UAE corporate-tax audited statement duty"),
    );
    const button = screen.getByRole("button", {
      name: "Prepare CT audited statement duty",
    });
    expect(button).toBeDisabled();
    expect(
      screen.getByRole("combobox", { name: "CT Tax Group itself" }),
    ).toHaveValue("unassessed");
    for (const [label, value] of [
      ["CT audit duty title", "SYNTHETIC duty"],
      ["CT registration reference", "SYN-CT"],
      ["CT tax period start", "2026-01-01"],
      ["CT tax period end", "2026-09-30"],
      ["CT assessed on", "2026-10-01"],
      ["CT adopted from", "2025-01-01"],
      ["CT adopted through", "2026-12-31"],
      ["CT operative rule assessment", "SYNTHETIC adopted dated source window"],
      [
        "CT entity and revenue assessment",
        "SYNTHETIC retained explicit missing revenue",
      ],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.change(
      screen.getByRole("combobox", { name: "Original MD84 rule PDF" }),
      { target: { value: "rule" } },
    );
    fireEvent.change(
      screen.getByRole("combobox", {
        name: "Separate CT period and classification facts",
      }),
      { target: { value: "facts" } },
    );
    expect(button).toBeDisabled();
    fireEvent.change(
      screen.getByRole("combobox", {
        name: "Original CTP007 clarification PDF",
      }),
      { target: { value: "clarification" } },
    );
    expect(button).toBeEnabled();
    fireEvent.click(button);
    await waitFor(() => expect(created).toHaveBeenCalledWith("duty"));
    const payload = mutate.mock.calls[0][0].body;
    expect(payload.revenue_aed).toBeNull();
    expect(payload.tax_group).toBe("unassessed");
    expect(payload.tax_group_member).toBe("unassessed");
    expect(payload.clarification_evidence_version_id).toBe("clarification");
    expect(payload.profile).toBe("uae-ct-audited-statements-md84-2025/2");
    expect(payload.other_rule_changes).toBe("unresolved");
    expect(payload.currency).toBe("AED");
    expect(payload.fact_sha256).toBe("b".repeat(64));
    fireEvent.change(
      screen.getByLabelText("Assessed complete-period AED revenue"),
      { target: { value: "50000000.01" } },
    );
    fireEvent.click(button);
    await waitFor(() =>
      expect(mutate.mock.calls.at(-1)?.[0].body.revenue_aed).toBe(
        "50000000.01",
      ),
    );
  });
});
