import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { filterTranscriptSegments } from "../lib/transcript";
import { TranscriptViewer } from "./transcript-viewer";


const segments = [
  { id: "1", start_ms: 0, end_ms: 1000, text: "Find the moments" },
  { id: "2", start_ms: 1200, end_ms: 2200, text: "worth watching" },
];

describe("transcript viewer search", () => {
  it("returns all segments for an empty query", () => {
    expect(filterTranscriptSegments(segments, "")).toEqual(segments);
  });

  it("filters timestamped segments case-insensitively", () => {
    expect(filterTranscriptSegments(segments, "WATCH")).toEqual([segments[1]]);
  });

  it("renders a real loading state before transcript status is available", () => {
    const markup = renderToStaticMarkup(
      <TranscriptViewer assetId="asset-1" videoElementId="video-asset-1" />,
    );
    expect(markup).toContain("Loading transcript status");
  });
});
