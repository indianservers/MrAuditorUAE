import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

const mock = vi.hoisted(() => ({ mutate: vi.fn() }));
const session = "11111111-1111-4111-8111-111111111111";
vi.mock("@/hooks/use-api", () => ({
  useAction: () => ({ mutate: mock.mutate, isPending: false }),
  useAPI: () => ({
    data: {
      status: "sync_failed",
      records: [
        {
          id: "record",
          namespace: "session",
          payload: {
            status: "failed",
            resume_session: "11111111-1111-4111-8111-111111111111",
          },
        },
      ],
    },
    refetch: vi.fn(),
  }),
}));
vi.mock("@/features/shared", () => ({
  JobProgress: () => <p>Job progress</p>,
}));
import { ConnectorOperations } from "@/features/connector-operations";

beforeEach(() => mock.mutate.mockClear());

it("replays a saved session through the matching source sync endpoint", () => {
  render(
    <ConnectorOperations
      connection={{
        id: "connection",
        provider: "quickbooks",
        config: { edition: "online" },
      }}
    />,
  );
  fireEvent.click(screen.getByText("Sync health and recovery"));
  fireEvent.click(screen.getByRole("button", { name: "Replay session" }));
  expect(mock.mutate.mock.calls[0][0].path).toBe(
    `connectors/native/connection/sync?resume_session=${session}`,
  );
  expect(
    screen.getByRole("button", { name: "Repair QuickBooks changes" }),
  ).toBeVisible();
});

it("retains saved Zoho evidence preferences when enabling document deltas", () => {
  render(
    <ConnectorOperations
      connection={{
        id: "zoho",
        provider: "zoho",
        config: { include_documents: true, include_attachments: true },
      }}
    />,
  );
  fireEvent.click(screen.getByText("Sync health and recovery"));
  fireEvent.click(
    screen.getByLabelText(
      "Use documented document deltas; refresh the full ledger",
    ),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Save evidence preferences" }),
  );
  expect(mock.mutate.mock.calls[0][0]).toMatchObject({
    method: "PATCH",
    body: {
      include_documents: true,
      include_attachments: true,
      incremental_documents: true,
    },
  });
});

it("requires a complete company fingerprint before enrolling Tally identity", () => {
  render(
    <ConnectorOperations
      connection={{ id: "tally", provider: "tally", config: {} }}
    />,
  );
  fireEvent.click(screen.getByText("Sync health and recovery"));
  const pin = screen.getByRole("button", {
    name: "Pin selected company identity",
  });
  expect(pin).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Selected Tally company"), {
    target: { value: "Test company" },
  });
  fireEvent.change(
    screen.getByLabelText("Company fingerprint from the local agent"),
    { target: { value: "a".repeat(64) } },
  );
  fireEvent.click(pin);
  expect(mock.mutate.mock.calls[0][0]).toMatchObject({
    path: "connectors/operations/tally/tally-identity",
    body: { company: "Test company", company_fingerprint: "a".repeat(64) },
  });
});
