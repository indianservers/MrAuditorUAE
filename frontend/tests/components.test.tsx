import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import {
  Button,
  Drawer,
  Empty,
  ErrorState,
  Pagination,
  Status,
  Tabs,
} from "@/components/ui/primitives";
import { useScope, useUI } from "@/stores/workspace";
import { ApiError, api } from "@/lib/api/client";
describe("professional states and interactions", () => {
  it("does not label inactive or unbalanced states as successful", () => {
    render(
      <>
        <Status value="inactive" />
        <Status value="unbalanced" />
        <Status value="Critical" />
      </>,
    );
    expect(screen.getByText("inactive")).toHaveClass("neutral");
    expect(screen.getByText("unbalanced")).toHaveClass("danger");
    expect(screen.getByText("Critical")).toHaveClass("danger");
  });
  it("activates enabled buttons and prevents disabled actions", () => {
    const fn = vi.fn();
    render(
      <>
        <Button onClick={fn}>Save</Button>
        <Button disabled onClick={fn}>
          Restricted
        </Button>
      </>,
    );
    fireEvent.click(screen.getByText("Save"));
    fireEvent.click(screen.getByText("Restricted"));
    expect(fn).toHaveBeenCalledTimes(1);
  });
  it("paginates only available server pages", () => {
    const fn = vi.fn();
    render(<Pagination offset={0} total={110} limit={50} onChange={fn} />);
    expect(screen.getByLabelText("Previous page")).toBeDisabled();
    fireEvent.click(screen.getByLabelText("Next page"));
    expect(fn).toHaveBeenCalledWith(50);
  });
  it("exposes tab selection", () => {
    const fn = vi.fn();
    render(
      <Tabs items={["Overview", "Findings"]} value="Overview" onChange={fn} />,
    );
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    fireEvent.click(screen.getByRole("tab", { name: "Findings" }));
    expect(fn).toHaveBeenCalledWith("Findings");
  });
  it("shows unavailable and permission errors honestly", () => {
    render(
      <>
        <Empty title="Not yet configured">Phase 5</Empty>
        <ErrorState error={new ApiError(403, "Denied")} />
        <Status value="insufficient_evidence" />
      </>,
    );
    expect(screen.getByText("Not yet configured")).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent("Access restricted");
    expect(screen.getByText("insufficient evidence")).toBeVisible();
  });
  it("provides an accessible detail dialog", () => {
    const fn = vi.fn();
    render(
      <Drawer open onOpenChange={fn} title="Source detail">
        <p>Immutable source</p>
      </Drawer>,
    );
    expect(screen.getByRole("dialog", { name: "Source detail" })).toBeVisible();
    fireEvent.click(screen.getByLabelText("Close details"));
    expect(fn).toHaveBeenCalledWith(false);
  });
  it("clears downstream business context on every scope change", () => {
    useScope.getState().setTenant("a");
    useScope.getState().setClient("c");
    useScope.getState().setEntity("e");
    useScope.getState().setPeriod("p");
    useScope.getState().setSnapshot("s");
    useScope.getState().setClient("new");
    expect(useScope.getState()).toMatchObject({
      tenant: "a",
      client: "new",
      entity: "",
      period: "",
      snapshot: "",
    });
    useScope.getState().setTenant("b");
    expect(useScope.getState()).toMatchObject({
      tenant: "b",
      client: "",
      entity: "",
      period: "",
      snapshot: "",
    });
  });
  it("stores layout preference without session or financial data", () => {
    useUI.getState().setDensity("comfortable");
    const saved = localStorage.getItem("auditos-ui-v3");
    expect(saved).toContain("comfortable");
    expect(saved).not.toMatch(/token|client_id|account|balance/);
  });
  it("normalizes backend errors and passes cancellation", async () => {
    const controller = new AbortController();
    const mock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(
          JSON.stringify({ error: { message: "Conflict", request_id: "r1" } }),
          { status: 409 },
        ),
      );
    await expect(
      api("clients", { signal: controller.signal }, "tenant-a"),
    ).rejects.toMatchObject({
      status: 409,
      message: "Conflict",
      requestId: "r1",
    });
    expect(mock.mock.calls[0][1]?.signal).toBe(controller.signal);
    expect(new Headers(mock.mock.calls[0][1]?.headers).get("X-Tenant-ID")).toBe(
      "tenant-a",
    );
  });
});
