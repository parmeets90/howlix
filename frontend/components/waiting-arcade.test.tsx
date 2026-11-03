import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { WaitingArcade } from "./waiting-arcade";

describe("waiting arcade", () => {
  it("offers two lightweight games with accessible controls", () => {
    const markup = renderToStaticMarkup(<WaitingArcade />);
    expect(markup).toContain("A tiny game while you wait");
    expect(markup).toContain("Catch the spark");
    expect(markup).toContain("Odd one out");
    expect(markup).toContain("Spark tile 1");
  });
});
