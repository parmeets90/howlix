import type { TranscriptSegment } from "./api";


export function filterTranscriptSegments(
  segments: TranscriptSegment[],
  query: string,
): TranscriptSegment[] {
  const normalized = query.trim().toLocaleLowerCase();
  if (!normalized) return segments;
  return segments.filter((segment) => segment.text.toLocaleLowerCase().includes(normalized));
}
