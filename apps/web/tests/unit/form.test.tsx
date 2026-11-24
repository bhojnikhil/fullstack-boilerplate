// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { FormError, TextField } from "@/components/form";

it("associates the field label, hint, and error with its input", () => {
  render(
    <>
      <TextField
        label="Email"
        aria-describedby="hint"
        error="Enter an email address."
      />
      <p id="hint">Use your work address.</p>
    </>,
  );

  const input = screen.getByRole("textbox", { name: "Email" });
  expect(input).toBeInvalid();
  expect(input).toHaveAccessibleDescription(
    "Use your work address. Enter an email address.",
  );
});

it("moves focus to a new form error", () => {
  const { rerender } = render(<FormError />);
  rerender(<FormError message="Sign-in failed." />);
  expect(screen.getByText("Sign-in failed.")).toHaveFocus();
});
