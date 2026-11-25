// @vitest-environment jsdom
import { StrictMode } from "react";
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

it("announces a new form error and re-announces the same error after another failure", () => {
  function renderForm(message?: string, failureCount?: number) {
    return (
      <>
        <TextField label="Email" />
        <FormError message={message} failureCount={failureCount} />
      </>
    );
  }

  const { rerender } = render(renderForm());
  const field = screen.getByRole("textbox", { name: "Email" });
  field.focus();
  const alert = screen.getByRole("alert");
  expect(alert).toBeEmptyDOMElement();

  rerender(renderForm("Sign-in failed.", 1));
  const firstMessage = screen.getByText("Sign-in failed.");
  expect(alert).toContainElement(firstMessage);
  expect(field).toHaveFocus();

  rerender(renderForm("Sign-in failed.", 2));
  const repeatedMessage = screen.getByText("Sign-in failed.");
  expect(firstMessage).not.toBeInTheDocument();
  expect(alert).toContainElement(repeatedMessage);
  expect(field).toHaveFocus();
});

it("does not move focus to a stale error on mount or an unrelated rerender", () => {
  const staleError = (
    <StrictMode>
      <FormError message="Sign-in failed." />
    </StrictMode>
  );
  const { rerender } = render(staleError);
  expect(screen.getByRole("alert")).toHaveTextContent("Sign-in failed.");
  expect(document.body).toHaveFocus();
  rerender(
    <StrictMode>
      <FormError message="Sign-in failed." />
    </StrictMode>,
  );
  expect(document.body).toHaveFocus();
});
