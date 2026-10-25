import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import {
  PublishedBenefitSource,
  PublishedPayrollSource,
} from "@/features/published-benefit-source";

const state = vi.hoisted(() => ({
  mutate: vi.fn(),
  pages: {} as Record<string, unknown>,
}));
vi.mock("@/hooks/use-api", () => ({
  useAPI: (path: string) => ({
    data: state.pages[path] || { items: [] },
    error: null,
  }),
  useAction: () => ({
    mutateAsync: state.mutate,
    isPending: false,
    error: null,
  }),
}));
const employee = {
  id: "employees",
  label: "Reviewed employees",
  kind: "workflow-source",
  table_type: "benefit-employees",
  freshness: "CURRENT",
  review_status: "REVIEWED",
};
const profile = {
  id: "profile",
  rule_key: "AE-SYNTHETIC",
  version: 1,
  state: "PUBLISHED",
  body: {
    title: "Synthetic profile",
    method: "benefit_profile",
    effective_from: "2026-01-01",
  },
};
beforeEach(() => {
  state.mutate.mockReset();
  state.pages = {
    "regulatory/rules?country=AE&offset=0&limit=50": { items: [profile] },
  };
});

it("uses India profiles and wage-basis bindings for payroll preparation", async () => {
  state.pages["regulatory/rules?country=IN&offset=0&limit=50"] = {
    items: [
      {
        ...profile,
        rule_key: "IN-SYNTHETIC",
        body: { ...profile.body, method: "payroll_profile" },
      },
      { ...profile, id: "uae", rule_key: "AE-BENEFIT" },
    ],
  };
  state.mutate.mockResolvedValue({ id: "payroll-derived" });
  const created = vi.fn();
  render(
    <PublishedPayrollSource
      eid="india"
      employees={[
        { ...employee, table_type: "payroll-bases" },
        { ...employee, id: "benefit", label: "UAE employees" },
      ]}
      onCreated={created}
    />,
  );
  expect(
    screen.queryByRole("option", { name: "UAE employees" }),
  ).not.toBeInTheDocument();
  expect(screen.getAllByRole("checkbox")).toHaveLength(1);
  fireEvent.change(screen.getByLabelText("Reviewed payroll basis source"), {
    target: { value: "employees" },
  });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.change(screen.getByLabelText("Independent wage-basis row count"), {
    target: { value: "3" },
  });
  fireEvent.change(screen.getByLabelText("Published payroll source title"), {
    target: { value: "Synthetic payroll profiles" },
  });
  fireEvent.change(
    screen.getByLabelText("Payroll profile applicability assessment"),
    {
      target: {
        value:
          "Explicit synthetic membership and jurisdiction for entire wage month",
      },
    },
  );
  fireEvent.click(
    screen.getByRole("button", {
      name: "Prepare published payroll rule source",
    }),
  );
  await waitFor(() => expect(created).toHaveBeenCalledWith("payroll-derived"));
  expect(state.mutate.mock.calls[0][0]).toMatchObject({
    path: "intelligence/engagements/india/payroll-rule-source",
    body: { basis_source_id: "employees", expected_basis_rows: 3 },
  });
  expect(state.mutate.mock.calls[0][0].body).not.toHaveProperty(
    "employee_source_id",
  );
});

it("excludes stale, unreviewed and unrelated employee sources and unpublished profiles", () => {
  state.pages["regulatory/rules?country=AE&offset=0&limit=50"] = {
    items: [
      profile,
      { ...profile, id: "draft", state: "DRAFT", rule_key: "AE-DRAFT" },
      {
        ...profile,
        id: "flat",
        rule_key: "AE-FLAT",
        body: { ...profile.body, method: "flat_rate" },
      },
    ],
  };
  render(
    <PublishedBenefitSource
      eid="engagement"
      employees={[
        employee,
        {
          ...employee,
          id: "stale",
          label: "Stale employees",
          freshness: "STALE",
        },
        {
          ...employee,
          id: "unverified",
          label: "Unverified employees",
          review_status: "UNVERIFIED",
        },
        {
          ...employee,
          id: "bank",
          label: "Bank transactions",
          table_type: "transactions",
        },
      ]}
      onCreated={vi.fn()}
    />,
  );
  expect(
    screen.getByRole("option", { name: "Reviewed employees" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("option", { name: "Stale employees" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("option", { name: "Unverified employees" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("option", { name: "Bank transactions" }),
  ).not.toBeInTheDocument();
  expect(screen.getAllByRole("checkbox")).toHaveLength(1);
});

it("retains selected profile versions across pages and submits explicit employee controls", async () => {
  state.pages["regulatory/rules?country=AE&offset=0&limit=50"] = {
    items: [
      profile,
      ...Array.from({ length: 49 }, (_, id) => ({
        ...profile,
        id: `draft-${id}`,
        state: "DRAFT",
      })),
    ],
  };
  state.pages["regulatory/rules?country=AE&offset=50&limit=50"] = {
    items: [{ ...profile, id: "profile-2", version: 2 }],
  };
  state.mutate.mockResolvedValue({ id: "derived" });
  const created = vi.fn();
  render(
    <PublishedBenefitSource
      eid="engagement"
      employees={[employee]}
      onCreated={created}
    />,
  );
  fireEvent.change(screen.getByLabelText("Reviewed benefit employee source"), {
    target: { value: "employees" },
  });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "Next profile page" }));
  fireEvent.click(screen.getByRole("checkbox"));
  expect(
    screen.getByLabelText("Selected benefit profiles").children,
  ).toHaveLength(2);
  const prepare = screen.getByRole("button", {
    name: "Prepare published benefit rule source",
  });
  expect(prepare).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Independent employee row count"), {
    target: { value: "2" },
  });
  fireEvent.change(screen.getByLabelText("Published benefit source title"), {
    target: { value: "Synthetic selected profiles" },
  });
  fireEvent.change(
    screen.getByLabelText("Benefit profile applicability assessment"),
    {
      target: {
        value: "Synthetic explicit employee cohort and service date assessment",
      },
    },
  );
  fireEvent.click(prepare);
  await waitFor(() => expect(created).toHaveBeenCalledWith("derived"));
  expect(state.mutate).toHaveBeenCalledWith({
    path: "intelligence/engagements/engagement/benefit-rule-source",
    body: {
      employee_source_id: "employees",
      rule_version_ids: ["profile", "profile-2"],
      expected_employee_rows: 2,
      label: "Synthetic selected profiles",
      assessment:
        "Synthetic explicit employee cohort and service date assessment",
    },
  });
});
