import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  RegulatorySources,
  bindRetainedSource,
  type RegulatorySource,
} from "@/features/regulatory-sources";

const state = vi.hoisted(() => ({
  mutate: vi.fn(),
  canManage: true,
  pages: {} as Record<string, unknown>,
}));
vi.mock("@/hooks/use-api", () => ({
  useAPI: (path: string) => ({
    data: state.pages[path] || { items: [] },
    error: null,
  }),
  useCan: () => state.canManage,
  useAction: () => ({
    mutateAsync: state.mutate,
    isPending: false,
    error: null,
  }),
}));
vi.mock("@/stores/workspace", () => ({
  useScope: (select: (scope: { tenant: string }) => unknown) =>
    select({ tenant: "firm" }),
}));
const document: RegulatorySource = {
  id: "source-1",
  title: "SYNTHETIC retained source",
  country: "AE",
  source_url: "https://mof.gov.ae/",
  retrieved_on: "2026-10-24",
  sha256: "a".repeat(64),
  filename: "SYNTHETIC.txt",
  scan_status: "CLEAN",
};
const proposal = JSON.stringify({
  country: "AE",
  validation_status: "AWAITING_VALIDATION",
  professional_review_status: "PENDING",
  citations: [{ paragraph: "FIRST" }, { paragraph: "SECOND" }],
});
beforeEach(() => {
  state.mutate.mockReset();
  state.canManage = true;
  state.pages = {};
});

describe("retained regulatory sources", () => {
  it("binds only the selected citation without granting content qualification", () => {
    const bound = JSON.parse(bindRetainedSource(proposal, document, 2));
    expect(bound.citations[0]).toEqual({ paragraph: "FIRST" });
    expect(bound.citations[1]).toMatchObject({
      paragraph: "SECOND",
      source_document_id: "source-1",
      document_sha256: "a".repeat(64),
      retrieval_status: "RETRIEVED",
    });
    expect(bound.validation_status).toBe("AWAITING_VALIDATION");
    expect(bound.professional_review_status).toBe("PENDING");
    expect(() =>
      bindRetainedSource(proposal, { ...document, country: "IN" }, 1),
    ).toThrow(/jurisdiction/);
    expect(() => bindRetainedSource(proposal, document, 3)).toThrow(
      /citation number/,
    );
  });
  it("retains selected copies across source pages for explicit attachment", () => {
    state.pages["regulatory/sources?country=AE&offset=0"] = {
      items: Array.from({ length: 50 }, (_, index) => ({
        ...document,
        id: "source-" + index,
      })),
    };
    const attach = vi.fn();
    render(
      <RegulatorySources country="AE" editor={proposal} onAttach={attach} />,
    );
    fireEvent.click(screen.getByText("Firm regulatory reference copies"));
    expect(
      screen.getByRole("combobox", { name: /^Retained regulatory source$/ }),
    ).toBeVisible();
    fireEvent.change(screen.getByLabelText("Retained regulatory source"), {
      target: { value: "source-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Next source copies" }));
    expect(screen.getByLabelText("Retained regulatory source")).toHaveValue(
      "source-1",
    );
    fireEvent.change(screen.getByLabelText("Citation number"), {
      target: { value: "2" },
    });
    fireEvent.click(
      screen.getByRole("button", {
        name: "Attach source to proposal citation",
      }),
    );
    expect(attach).toHaveBeenCalledWith(
      expect.objectContaining({ id: "source-1" }),
      2,
    );
  });
  it("sends actual reference bytes and explicitly entered metadata", async () => {
    state.mutate.mockResolvedValue(document);
    render(<RegulatorySources country="AE" editor="" onAttach={vi.fn()} />);
    fireEvent.click(screen.getByText("Firm regulatory reference copies"));
    for (const [label, value] of [
      ["Reference title", "SYNTHETIC retained source"],
      ["Source HTTPS URL", "https://mof.gov.ae/"],
      ["Source retrieved on", "2026-10-24"],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    const file = new File(["SYNTHETIC bytes"], "SYNTHETIC.txt", {
      type: "text/plain",
    });
    fireEvent.change(screen.getByLabelText("Regulatory reference file"), {
      target: { files: [file] },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Retain scanned reference copy" }),
    );
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    const request = state.mutate.mock.calls[0][0];
    expect(request.path).toBe("regulatory/sources");
    expect(request.body.get("file").name).toBe("SYNTHETIC.txt");
    expect(JSON.parse(request.body.get("metadata"))).toEqual({
      title: "SYNTHETIC retained source",
      country: "AE",
      source_url: "https://mof.gov.ae/",
      retrieved_on: "2026-10-24",
    });
  });
  it("requires the source-management permission for uploading", () => {
    state.canManage = false;
    render(<RegulatorySources country="AE" editor="" onAttach={vi.fn()} />);
    fireEvent.click(screen.getByText("Firm regulatory reference copies"));
    expect(
      screen.queryByLabelText("Regulatory reference file"),
    ).not.toBeInTheDocument();
  });
});
