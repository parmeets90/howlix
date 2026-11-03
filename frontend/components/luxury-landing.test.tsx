import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import LuxuryLanding from "./luxury-landing";

describe("landing navigation", () => {
  it("offers authentication to signed-out visitors", () => {
    const markup = renderToStaticMarkup(<LuxuryLanding />);
    expect(markup).toContain('href="/auth/login"');
    expect(markup).toContain("Sign in");
  });

  it("sends signed-in visitors directly to their dashboard", () => {
    const markup = renderToStaticMarkup(<LuxuryLanding signedIn />);
    expect(markup).toContain('href="/dashboard"');
    expect(markup).toContain("Open dashboard");
    expect(markup).not.toContain('href="/auth/login"');
  });
});
