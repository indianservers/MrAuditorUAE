import { expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AuditJourney } from "@/features/audit-journey";
import type { Workspace } from "@/features/global-workspace";
it("keeps stale approved papers in attention and links the reviewer to the actual blocker", () => {
  const data = {
    records: [
      {
        id: "paper",
        kind: "working-papers",
        status: "APPROVED",
        freshness: "STALE",
        label: "Cash",
        url: "/paper",
      },
      {
        id: "risk",
        kind: "risks",
        status: "APPROVED",
        freshness: "CURRENT",
        label: "Risk",
        url: "/risk",
      },
    ],
    source_freshness: [{ freshness: "STALE" }],
    blockers: [
      {
        id: "source",
        label: "Changed cash source",
        reason: "STALE",
        url: "/source-review",
      },
    ],
    truncated: true,
  } as Workspace;
  render(<AuditJourney data={data} eid="engagement" />);
  expect(screen.getByRole("link", { name: /Resolve blocker/ })).toHaveAttribute(
    "href",
    "/source-review",
  );
  expect(
    screen.getByRole("link", { name: /Working papers/ }),
  ).toHaveTextContent("Source review needed");
  fireEvent.click(screen.getByRole("button", { name: "Focus on attention" }));
  expect(
    screen.queryByRole("link", { name: /Risk assessment/ }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: /Working papers/ }),
  ).toBeInTheDocument();
  expect(screen.getByText(/Bounded view/)).toBeInTheDocument();
});
