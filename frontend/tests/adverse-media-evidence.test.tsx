import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import {
  AdverseMediaEvidence,
  MediaMentionAssessments,
} from "@/features/adverse-media-evidence";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("discloses declared query scope, no clearance and disabled automatic monitoring", () => {
  render(
    <AdverseMediaEvidence
      eid="E"
      tenant="T"
      documents={[]}
      scope={{
        country: "AE",
        coverage_from: "2025-01-01",
        coverage_through: "2026-06-28",
        expected_subjects: 2,
        maximum_query_age_days: 7,
        assessment: "Synthetic reviewed country policy and query scope",
      }}
    />,
  );
  expect(
    screen.getByRole("region", { name: "Adverse-media review scope" }),
  ).toHaveTextContent("2 subjects");
  expect(screen.getByText(/No mentions is not clearance/)).toHaveTextContent(
    "unresolved identities block approval",
  );
  expect(screen.getByText(/Follow-up dates/)).toHaveTextContent(
    "automatic monitoring is off",
  );
});

it("shows retained human identity and risk reasons rather than interpreting a headline", () => {
  render(
    <MediaMentionAssessments
      rows={[
        {
          id: "mention:M1",
          kind: "media-mention",
          article_id: "ARTICLE-1",
          identity_status: "different-subject",
          risk: "low",
          disposition: "no-action",
          title: "Synthetic allegation",
          publisher: "Synthetic publisher",
          identity_rationale: "Different registration evidence",
          risk_rationale: "Assessed identity collision",
          reported_stage: "allegation",
          source_evidence_version_id: "ARTICLE-VERSION",
          source_sha256: "a".repeat(64),
        },
      ]}
    />,
  );
  fireEvent.click(screen.getByText(/ARTICLE-1 · different-subject/));
  expect(screen.getByText(/Identity rationale:/)).toHaveTextContent(
    "Different registration evidence",
  );
  expect(screen.getByText(/Risk rationale:/)).toHaveTextContent(
    "Assessed identity collision",
  );
  expect(screen.getByText(/Reported stage:/)).toHaveTextContent("allegation");
});

it("downloads original media evidence through the tenant-scoped authenticated route", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue({
      ok: true,
      blob: async () => new Blob(["SYNTHETIC article"]),
      headers: new Headers(),
    });
  vi.stubGlobal("fetch", fetcher);
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:media-test");
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => {});
  render(
    <AdverseMediaEvidence
      eid="E"
      tenant="T"
      documents={[{ id: "V", record_id: "R", sha256: "a".repeat(64) }]}
    />,
  );
  fireEvent.click(
    screen.getByText(
      "Retained search, article, identity and policy evidence (1)",
    ),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Download media evidence 1" }),
  );
  await waitFor(() => expect(click).toHaveBeenCalled());
  expect(fetcher).toHaveBeenCalledWith(
    "/api/backend/engagements/E/audit/evidence-files/R/V/download",
    { headers: { "X-Tenant-ID": "T" }, cache: "no-store" },
  );
});
