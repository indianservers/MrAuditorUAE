import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
const mock = vi.hoisted(() => ({ mutateAsync: vi.fn() }));
vi.mock("@/hooks/use-api", () => ({
  useAction: () => ({ ...mock, isPending: false, error: null }),
}));
import { PaperEditor, Field, initial, type Schema } from "@/features/grc-forms";
beforeEach(() => {
  mock.mutateAsync.mockReset();
  mock.mutateAsync.mockResolvedValue({ id: "x" });
});
describe("GRC evidence editor", () => {
  it("keeps numeric matrix options numeric and requires explicit conclusions", () => {
    const change = vi.fn();
    const schema: Schema = { type: "integer", enum: [3, 5] };
    render(
      <Field
        name="matrix_size"
        schema={schema}
        root={schema}
        value={5}
        change={change}
      />,
    );
    fireEvent.change(screen.getByLabelText("Matrix size"), {
      target: { value: "3" },
    });
    expect(change).toHaveBeenCalledWith(3);
    expect(
      initial({ type: "string", enum: ["effective", "ineffective"] }),
    ).toBe("");
  });
  it("keeps a business review date while stripping only workflow metadata", async () => {
    const schema: Schema = {
      type: "object",
      properties: {
        review_date: { type: "string", format: "date" },
        observations: {
          type: "array",
          items: {
            type: "object",
            properties: { value: { type: "string" } },
            required: ["value"],
          },
        },
      },
    };
    render(
      <PaperEditor
        base="grc/engagements/E"
        kind="risk"
        schema={schema}
        paper={{
          id: "R",
          reference: "R-01",
          title: "Risk",
          kind: "grc-risk",
          version: 3,
          status: "REVIEW_NOTES",
          body: {
            review_date: "2026-12-31",
            review_stage: 0,
            review_approvers: [],
            observations: [],
          },
        }}
        done={() => {}}
      />,
    );
    expect(screen.getByLabelText("Review date")).toHaveValue("2026-12-31");
    fireEvent.click(screen.getByRole("button", { name: "Add Observations" }));
    fireEvent.change(screen.getByLabelText("Value"), {
      target: { value: "Evidence-backed movement" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(mock.mutateAsync).toHaveBeenCalled());
    const request = mock.mutateAsync.mock.calls[0][0];
    expect(request.method).toBe("PATCH");
    expect(request.body.version).toBe(3);
    expect(request.body.body.review_date).toBe("2026-12-31");
    expect(request.body.body.review_stage).toBeUndefined();
    expect(request.body.body.observations).toEqual([
      { value: "Evidence-backed movement" },
    ]);
  });
});
