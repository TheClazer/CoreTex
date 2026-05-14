import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { WarningsPanel } from "../components/WarningsPanel";

describe("WarningsPanel", () => {
  it("shows an empty-state message when there are no warnings", () => {
    render(<WarningsPanel warnings={[]} />);
    expect(screen.getByText(/no warnings/i)).toBeInTheDocument();
  });

  it("renders each warning and tags citation warnings", () => {
    render(
      <WarningsPanel
        warnings={[
          "[CITATION] '[1]' kept as plain text — manual BibTeX needed.",
          "Equation 3 could not be converted from OMML; placeholder inserted.",
        ]}
      />
    );
    expect(screen.getByText(/CITATION/)).toBeInTheDocument();
    expect(screen.getByText(/Equation 3/)).toBeInTheDocument();
  });
});
