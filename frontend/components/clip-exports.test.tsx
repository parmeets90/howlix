import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ClipExports, ClipExportSettingsForm } from "./clip-exports";


describe("clip exports", () => {
  it("renders export history without fabricating a finished preview", () => {
    const markup = renderToStaticMarkup(<ClipExports momentId="moment-1" />);
    expect(markup).toContain("Your clips");
    expect(markup).toContain("No clips made yet");
    expect(markup).not.toContain("Download MP4");
  });

  it("renders validated aspect, framing, caption, and quality settings", () => {
    const markup = renderToStaticMarkup(
      <ClipExportSettingsForm submitting={false} onSubmit={async () => undefined} />,
    );
    expect(markup).toContain("9:16 vertical");
    expect(markup).toContain("1080p · high quality");
    expect(markup).toContain("Face-aware · best effort");
    expect(markup).toContain("Karaoke");
    expect(markup).toContain("Caption size");
    expect(markup).toContain("Create Clip");
  });
});
