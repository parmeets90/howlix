import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  cancelYouTubeImport: vi.fn(),
  createYouTubeImport: vi.fn(),
  listYouTubeImports: vi.fn().mockResolvedValue([]),
  retryYouTubeImport: vi.fn(),
}));

import { YouTubeImporter } from "./youtube-importer";


describe("YouTube importer", () => {
  it("requires provenance confirmation and offers manual-upload guidance", () => {
    const markup = renderToStaticMarkup(<YouTubeImporter projectId="project-1" />);
    expect(markup).toContain("YouTube link");
    expect(markup).toContain("I own this video, or I have permission to use it");
    expect(markup).toContain("Playlists and private videos will not work");
    expect(markup).toContain("Add YouTube video");
  });
});
