import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MLSignals } from "@/features/ml-signals";

const state = vi.hoisted(() => ({
  mode: "rules_baseline",
  model: null as string | null,
  runtime: true,
}));
vi.mock("@/hooks/use-api", () => ({
  useCan: () => true,
  useAPI: (path: string) => ({
    data: path.startsWith("engagements")
      ? { items: [{ id: "E1", entity_id: "ENTITY", period_id: "PERIOD" }] }
      : path.includes("capabilities")
        ? { local_runtime_present: state.runtime }
        : {
            items: [
              {
                id: "I1",
                body: {
                  model_id: state.model,
                  execution_mode: state.mode,
                  predictions: [{ transaction_id: "T1", score: 0.5 }],
                },
              },
            ],
          },
    error: null,
  }),
}));
vi.mock("@/stores/workspace", () => ({
  useScope: () => ({ entity: "ENTITY", period: "PERIOD" }),
}));

beforeEach(() => {
  state.mode = "rules_baseline";
  state.model = null;
  state.runtime = true;
});
describe("ML execution provenance", () => {
  it("shows baseline execution without pretending a trained model was used", () => {
    render(<MLSignals />);
    expect(
      screen.getByText(/Execution mode: rules_baseline/),
    ).toHaveTextContent("No trained model used");
    expect(screen.getByText(/Deterministic workflows/)).toHaveTextContent(
      "do not require language-model credentials",
    );
  });
  it("labels a missing local runtime while preserving deterministic workflows", () => {
    state.runtime = false;
    render(<MLSignals />);
    expect(screen.getByText(/Local CPU runtime:/)).toHaveTextContent(
      "unavailable",
    );
  });
  it("preserves explicitly diagnostic mode and model identity for trained execution", () => {
    state.mode = "diagnostic_mock";
    const view = render(<MLSignals />);
    expect(
      screen.getByText(/Execution mode: diagnostic_mock/),
    ).toBeInTheDocument();
    view.unmount();
    state.mode = "trained_model";
    state.model = "model-12345678";
    render(<MLSignals />);
    expect(screen.getByText(/Execution mode: trained_model/)).toHaveTextContent(
      "Model model-12",
    );
  });
});
