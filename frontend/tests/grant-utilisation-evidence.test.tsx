import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import {
  GrantSourceNotice,
  GrantUtilisationEvidence,
} from "@/features/grant-utilisation-evidence";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
it("separates signed book utilisation from cash, legal eligibility and certificates", () => {
  render(
    <GrantUtilisationEvidence
      eid="E"
      tenant="T"
      documents={[]}
      currencies={["AED", "USD"]}
      reviewWindow={{ from: "2026-01-01", through: "2026-06-30" }}
    />,
  );
  expect(screen.getByText(/2026-01-01 through 2026-06-30/)).toHaveTextContent(
    "AED, USD",
  );
  expect(
    screen.getByText(/They do not establish cash available/),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/Credits always require a separate recovery review/),
  ).toBeInTheDocument();
});

it("uses retained evidence record/version identifiers for authenticated downloads", async () => {
  const fetcher = vi.fn().mockResolvedValue({
    ok: true,
    blob: async () => new Blob(["SYNTHETIC grant evidence"]),
    headers: new Headers({
      "content-disposition": 'attachment; filename="SYNTHETIC-mandate.txt"',
    }),
  });
  vi.stubGlobal("fetch", fetcher);
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:grant-test");
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => {});
  render(
    <GrantUtilisationEvidence
      eid="E"
      tenant="T"
      documents={[
        { id: "VERSION", record_id: "RECORD", sha256: "a".repeat(64) },
      ]}
    />,
  );
  fireEvent.click(
    screen.getByText("Retained grant mandate and recovery evidence (1)"),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Download grant evidence 1" }),
  );
  await waitFor(() => expect(click).toHaveBeenCalled());
  expect(fetcher).toHaveBeenCalledWith(
    "/api/backend/engagements/E/audit/evidence-files/RECORD/VERSION/download",
    expect.objectContaining({
      headers: { "X-Tenant-ID": "T" },
      cache: "no-store",
    }),
  );
});

it("explains mixed file totals as integrity controls rather than available grant funds", () => {
  render(<GrantSourceNotice kind="grant-utilisation-controls" />);
  expect(screen.getByRole("note")).toHaveTextContent(
    "solely to check this file",
  );
  expect(screen.getByRole("note")).toHaveTextContent(
    "separate each fund/category opening",
  );
});
