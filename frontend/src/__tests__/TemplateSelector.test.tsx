import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TemplateSelector } from "../components/TemplateSelector";

describe("TemplateSelector", () => {
  it("renders all four template options", () => {
    render(<TemplateSelector value="article" onChange={() => {}} />);
    expect(screen.getByText("article")).toBeInTheDocument();
    expect(screen.getByText("IEEE Transactions")).toBeInTheDocument();
    expect(screen.getByText("ACM SIGCONF")).toBeInTheDocument();
    expect(screen.getByText("Springer LNCS")).toBeInTheDocument();
  });

  it("invokes onChange when user picks a different template", () => {
    const onChange = vi.fn();
    render(<TemplateSelector value="article" onChange={onChange} />);
    fireEvent.click(screen.getByLabelText(/IEEE Transactions/));
    expect(onChange).toHaveBeenCalledWith("ieee");
  });

  it("respects the disabled prop", () => {
    render(<TemplateSelector value="article" onChange={() => {}} disabled />);
    const radios = screen.getAllByRole("radio");
    radios.forEach((r) => expect(r).toBeDisabled());
  });
});
