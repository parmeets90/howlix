import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { MomentCandidate } from "../lib/api";
import { formatMomentTimestamp, MomentDiscovery, MomentReviewPanel } from "./moment-discovery";


const candidate: MomentCandidate = {
  id: "moment-1",
  analysis_run_id: "run-1",
  asset_id: "asset-1",
  start_ms: 20_000,
  end_ms: 65_000,
  ai_start_ms: 20_000,
  ai_end_ms: 65_000,
  duration_ms: 45_000,
  suggested_title: "A complete standalone lesson",
  hook_text: "What if the usual advice is backwards?",
  topic: "Learning",
  category: "education",
  overall_score: 84.5,
  score_breakdown: {
    hook_strength: { score: 90, weight: 0.3, assessed: true },
    visual_quality: { score: null, weight: 0.05, assessed: false },
  },
  explanation: "A clear question leads to a useful payoff.",
  confidence_notes: "Review the opening pause.",
  needs_context: false,
  rank: 1,
  review_status: "pending",
  transcript_excerpt: "What if the usual advice is backwards? Here is the complete explanation.",
  created_at: "2026-10-30T00:00:00Z",
  updated_at: "2026-10-30T00:00:00Z",
};


describe("moment discovery review", () => {
  it("formats absolute timestamps", () => {
    expect(formatMomentTimestamp(65_000)).toBe("1:05");
  });

  it("renders a real loading state before the analysis request resolves", () => {
    const markup = renderToStaticMarkup(<MomentDiscovery assetId="asset-1" videoElementId="video-1" />);
    expect(markup).toContain("Loading moment analysis");
    expect(markup).toContain("Find Best Moments");
  });

  it("renders review, boundary editing, preview, and reset controls", () => {
    const markup = renderToStaticMarkup(createElement(MomentReviewPanel, {
      candidate,
      onSave: async () => undefined,
      onReset: async () => undefined,
      onReview: async () => undefined,
      onPreview: () => undefined,
    }));
    expect(markup).toContain("Review recommendation #1");
    expect(markup).toContain("Preview range");
    expect(markup).toContain("Reset to AI");
    expect(markup).toContain("Save changes");
    expect(markup).toContain("Approve");
    expect(markup).toContain("Reject");
    expect(markup).toContain(candidate.transcript_excerpt);
  });
});
