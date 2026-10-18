import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
vi.mock("@/hooks/use-api", () => ({
  useAPI: () => ({ data: undefined, error: null }),
  useAction: () => ({}),
}));
vi.mock("@/features/shared", () => ({
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
}));
import { EnterpriseAI, aiAreas } from "@/features/enterprise-ai";
describe("enterprise investigation entry", () => {
  it("exposes sixteen distinct workspaces and requires engagement selection", () => {
    expect(aiAreas).toHaveLength(16);
    expect(new Set(aiAreas.map((a) => a[0])).size).toBe(16);
    render(<EnterpriseAI />);
    expect(
      screen.getByRole("heading", { name: "AI Command Center" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Choose an engagement")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "AI engagement" })).toHaveValue(
      "",
    );
  });
});
