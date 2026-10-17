import React from "react";
import { it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Providers } from "@/components/providers";
it("announces backend acknowledgement and allows dismissal", () => {
  render(
    <Providers>
      <span>Workspace</span>
    </Providers>,
  );
  fireEvent(
    window,
    new CustomEvent("auditos:notice", { detail: "Request accepted" }),
  );
  expect(screen.getByRole("status")).toHaveTextContent("Request accepted");
  fireEvent.click(screen.getByLabelText("Dismiss notification"));
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});
