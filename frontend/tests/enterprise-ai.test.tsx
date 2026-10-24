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
  it("includes the UAE workflows alongside distinct investigation workspaces and requires engagement selection", () => {
    expect(aiAreas).toContainEqual(["uae-use-cases", "UAE Business Workflows"]);
    expect(aiAreas).toContainEqual(["command-center", "AI Command Center"]);
    expect(aiAreas).toContainEqual(["approvals", "Human Approval Inbox"]);
    expect(new Set(aiAreas.map((a) => a[0])).size).toBe(aiAreas.length);
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
