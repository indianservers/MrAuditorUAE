import {
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

const mock = vi.hoisted(() => ({
  query: vi.fn(),
  mutate: vi.fn(),
  stale: false,
}));
vi.mock("@/hooks/use-api", () => ({
  useAPI: (path: string, enabled = true) => mock.query(path, enabled),
  useAction: () => ({ mutate: mock.mutate, isPending: false }),
}));
vi.mock("@/stores/workspace", () => ({
  useScope: (select: (value: { tenant: string }) => unknown) =>
    select({ tenant: "TENANT" }),
}));
import {
  SoDResults,
  SoDInputAssignments,
  SoDCalculation,
} from "@/features/sod-results";

beforeEach(() => {
  mock.stale = false;
  mock.mutate.mockReset();
  mock.query.mockReset();
  mock.query.mockImplementation((path: string, enabled: boolean) => {
    if (!enabled) return { isPending: true };
    if (path.endsWith("/sod"))
      return {
        data: {
          id: "RUN",
          frozen_at: "2026-10-27",
          snapshot_sha256: "a".repeat(64),
          record_versions_status: mock.stale
            ? "STALE_HISTORICAL_SNAPSHOT"
            : "CURRENT_RECORD_VERSIONS",
          implementation_status: "CURRENT_IMPLEMENTATION",
          results: {
            analysis_from: "2026-01-01",
            analysis_through: "2026-12-31",
            analysis_mode: "period-intervals",
            population_basis: "validity-history",
            source_binding_status: "CSV_BYTES_AND_ASSIGNMENTS_VERIFIED",
            population_control_status: "INDEPENDENT_DECLARED_COUNTS_AGREE",
            population_completeness:
              "DECLARED_SCOPE_ONLY_NOT_INDEPENDENTLY_ESTABLISHED",
            collection_totals: {
              conflicts: 121,
              assignments: 242,
              assignment_pair_links: 121,
            },
            policy_pairs_retained: true,
            limitations: ["No role expansion"],
          },
        },
      };
    if (path.includes("/rows/")) {
      const offset = Number(
        new URL("http://test/" + path).searchParams.get("offset"),
      );
      return {
        data: {
          items: [
            {
              principal: `SYN-user-${offset}`,
              scope: null,
              compensating_control_verified: false,
              delta: 0,
            },
          ],
          total: 121,
          record_versions_status: mock.stale
            ? "STALE_HISTORICAL_SNAPSHOT"
            : "CURRENT_RECORD_VERSIONS",
        },
        isFetching: false,
      };
    }
    return {
      data: {
        items: [
          {
            id: "SAVED",
            created_at: "2026-10-27",
            results: { sod_contract: "permission-overlap-intervals/1" },
          },
        ],
        total: 1,
      },
    };
  });
});

it("pages conflicts independently without fetching closed collections or inventing values", () => {
  render(<SoDResults base="grc/engagements/E" run="RUN" />);
  expect(screen.getByText("SYN-user-0")).toBeInTheDocument();
  expect(screen.getByText("Not supplied")).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "false" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "0" })).toBeInTheDocument();
  expect(mock.query).toHaveBeenCalledWith(
    expect.stringContaining("/rows/assignments?"),
    false,
  );
  fireEvent.click(screen.getByRole("button", { name: "Next Conflicts" }));
  expect(screen.getByText("SYN-user-50")).toBeInTheDocument();
  expect(mock.query).toHaveBeenCalledWith(
    expect.stringContaining("/rows/conflicts?offset=50"),
    true,
  );
});

it("labels stale results and downloads the complete authenticated workbook", async () => {
  mock.stale = true;
  const fetcher = vi
    .fn()
    .mockResolvedValue({ ok: true, blob: async () => new Blob(["SYNTHETIC"]) });
  vi.stubGlobal("fetch", fetcher);
  const create = vi.fn().mockReturnValue("blob:test");
  vi.stubGlobal(
    "URL",
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: vi.fn() }),
  );
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => {});
  render(<SoDResults base="grc/engagements/E" run="RUN" />);
  expect(
    screen.getAllByText(/STALE_HISTORICAL_SNAPSHOT/).length,
  ).toBeGreaterThan(0);
  fireEvent.click(
    screen.getByRole("button", { name: "Download complete SoD workbook" }),
  );
  await waitFor(() => expect(click).toHaveBeenCalled());
  expect(fetcher).toHaveBeenCalledWith(
    "/api/backend/grc/engagements/E/runs/RUN/sod/export",
    expect.objectContaining({
      headers: { "X-Tenant-ID": "TENANT" },
      cache: "no-store",
    }),
  );
  expect(
    screen.getByText(/does not recheck current original-file bytes/),
  ).toBeInTheDocument();
  click.mockRestore();
  vi.unstubAllGlobals();
});

it("keeps imported draft assignments bounded and original indices stable", () => {
  const assignments = Array.from({ length: 121 }, (_, i) => ({
    principal: `SYN-${i}`,
    permission: "create",
    scope: "A",
    valid_from: "2026-01-01",
    valid_to: null,
  }));
  render(<SoDInputAssignments assignments={assignments} />);
  const region = screen.getByRole("region", {
    name: "Imported assignment rows",
    hidden: true,
  });
  expect(within(region).getAllByRole("row", { hidden: true })).toHaveLength(51);
  fireEvent.click(
    screen.getByText("Imported assignment population (121 rows)"),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Next input assignments" }),
  );
  expect(screen.getByText("SYN-50")).toBeInTheDocument();
  expect(screen.queryByText("SYN-0")).not.toBeInTheDocument();
});

it("uses compact calculate and history requests instead of returning full collections", () => {
  render(<SoDCalculation base="grc/engagements/E" paper="PAPER" />);
  expect(mock.query).toHaveBeenCalledWith(
    expect.stringContaining("record_id=PAPER&compact_sod=true"),
    true,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Freeze reviewed calculation" }),
  );
  expect(mock.mutate).toHaveBeenCalledWith({
    path: "grc/engagements/E/records/PAPER/calculate?compact_sod=true",
  });
});

it("keeps saved snapshots readable when recalculation is unavailable", () => {
  render(
    <SoDCalculation
      base="grc/engagements/E"
      paper="PAPER"
      canCalculate={false}
    />,
  );
  expect(
    screen.queryByRole("button", { name: "Freeze reviewed calculation" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Frozen SoD results" }),
  ).toBeInTheDocument();
});

it("uses gateway-compatible hyphenated routes when a collection opens", async () => {
  render(<SoDResults base="grc/engagements/E" run="RUN" />);
  fireEvent.click(screen.getByText("Assignment links", { exact: true }));
  await waitFor(() =>
    expect(mock.query).toHaveBeenCalledWith(
      expect.stringContaining("/rows/assignment-pair-links?offset=0"),
      true,
    ),
  );
});
