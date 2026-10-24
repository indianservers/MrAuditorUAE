import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

const mock = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock("@/hooks/use-api", () => ({
  useAction: () => ({ mutate: mock.mutate, isPending: false }),
  useAPI: (path: string) =>
    path.includes("requirements")
      ? {
          data: {
            direct_api: {
              editions: ["online", "desktop-partner-api"],
              credential_fields: ["client_id", "client_secret"],
              config_fields: ["company_id", "functional_currency"],
              partner_fields: ["base_url", "ledger_path"],
              oauth: true,
              documentation: "https://developer.intuit.com/",
            },
          },
        }
      : {},
}));
vi.mock("@/features/shared", () => ({
  JobProgress: () => <p>Job progress</p>,
}));
import { NativeConnection } from "@/features/native-connection";

beforeEach(() => mock.mutate.mockClear());

it("saves direct configuration and new secrets through PATCH without displaying stored credentials", () => {
  render(
    <NativeConnection
      connection={{
        id: "connection-1",
        provider: "quickbooks",
        status: "credentials_pending",
        config: {
          edition: "online",
          company_id: "1000",
          functional_currency: "AED",
        },
      }}
    />,
  );
  fireEvent.click(screen.getByText("Secure credentials"));
  fireEvent.change(screen.getByLabelText("OAuth client secret"), {
    target: { value: "test-secret" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Save direct API configuration" }),
  );
  expect(mock.mutate.mock.calls[0][0]).toMatchObject({
    path: "connectors/native/connection-1/configuration",
    method: "PATCH",
    body: {
      config: { company_id: "1000", edition: "online" },
      credentials: { client_secret: "test-secret" },
    },
  });
  expect(screen.getByLabelText("OAuth client secret")).toHaveAttribute(
    "type",
    "password",
  );
  expect(
    screen.getByText(/Stored credentials are never displayed/),
  ).toBeVisible();
});

it("exposes direct API sync and identifies desktop partner requirements rather than using Online endpoints", () => {
  render(
    <NativeConnection
      connection={{
        id: "connection-1",
        provider: "quickbooks",
        status: "configured",
        config: {},
      }}
    />,
  );
  fireEvent.change(screen.getByLabelText("Product edition"), {
    target: { value: "desktop-partner-api" },
  });
  expect(screen.getByRole("status")).toHaveTextContent(
    "vendor-approved partner API",
  );
  expect(
    screen.queryByRole("button", { name: "Authorize quickbooks" }),
  ).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "Start direct API sync" }),
  );
  expect(mock.mutate.mock.calls[0][0].path).toBe(
    "connectors/native/connection-1/sync",
  );
});
