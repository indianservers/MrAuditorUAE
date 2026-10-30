import { useState } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { expect, it } from "vitest";
import { Field, initial, type Schema } from "@/features/grc-forms";

const schema: Schema = {
  type: "object",
  properties: {
    authority_scope: {
      anyOf: [{ $ref: "#/$defs/AuthorityScope" }, { type: "null" }],
      default: null,
    },
  },
  $defs: {
    AuthorityScope: {
      type: "object",
      required: ["profile", "assessment"],
      properties: {
        profile: { type: "string", const: "source-pinned-profile/1" },
        assessment: { type: "string" },
      },
    },
  },
};
function Editor({ initialValue }: { initialValue?: unknown }) {
  const [value, setValue] = useState(initialValue ?? initial(schema));
  return (
    <>
      <Field
        name="Body"
        schema={schema}
        root={schema}
        value={value}
        change={setValue}
      />
      <output aria-label="Submitted body">{JSON.stringify(value)}</output>
    </>
  );
}
it("includes the required fixed profile identifier when an optional object is first edited", () => {
  render(<Editor />);
  expect(screen.getByText("source-pinned-profile/1")).toBeVisible();
  expect(screen.getByLabelText("Submitted body")).toHaveTextContent("{}");
  fireEvent.change(screen.getByLabelText("Assessment"), {
    target: { value: "Independently assessed scope" },
  });
  expect(
    JSON.parse(screen.getByLabelText("Submitted body").textContent!),
  ).toEqual({
    authority_scope: {
      profile: "source-pinned-profile/1",
      assessment: "Independently assessed scope",
    },
  });
  fireEvent.click(screen.getByRole("button", { name: "Clear optional field" }));
  expect(
    JSON.parse(screen.getByLabelText("Submitted body").textContent!),
  ).toEqual({});
  fireEvent.change(screen.getByLabelText("Assessment"), {
    target: { value: "New deliberate scope assessment" },
  });
  expect(
    JSON.parse(screen.getByLabelText("Submitted body").textContent!)
      .authority_scope.profile,
  ).toBe("source-pinned-profile/1");
});

it("preserves and displays a retained fixed value rather than silently upgrading an existing object", () => {
  render(
    <Editor
      initialValue={{
        authority_scope: {
          profile: "retained-old-profile/0",
          assessment: "Earlier retained assessment",
        },
      }}
    />,
  );
  expect(screen.getByText("retained-old-profile/0")).toBeVisible();
  expect(screen.queryByText("source-pinned-profile/1")).toBeNull();
  fireEvent.change(screen.getByLabelText("Assessment"), {
    target: { value: "Updated rationale requiring separate profile migration" },
  });
  expect(
    JSON.parse(screen.getByLabelText("Submitted body").textContent!)
      .authority_scope.profile,
  ).toBe("retained-old-profile/0");
});
