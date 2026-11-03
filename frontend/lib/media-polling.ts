import type { MediaAsset } from "@/lib/api";

export function mergeMediaWithoutReloadingVideo(
  current: MediaAsset[],
  incoming: MediaAsset[],
): MediaAsset[] {
  const previousById = new Map(current.map((asset) => [asset.id, asset]));
  const merged = incoming.map((asset) => {
    const previous = previousById.get(asset.id);
    if (!previous) return asset;
    const previousJob = previous.latest_job;
    const nextJob = asset.latest_job;
    const unchanged =
      previous.status === asset.status &&
      previous.updated_at === asset.updated_at &&
      previousJob?.status === nextJob?.status &&
      previousJob?.progress_stage === nextJob?.progress_stage &&
      previousJob?.progress_completed === nextJob?.progress_completed &&
      previousJob?.progress_total === nextJob?.progress_total &&
      previousJob?.error_message === nextJob?.error_message &&
      previousJob?.dispatch_error_message === nextJob?.dispatch_error_message;
    return unchanged ? previous : asset;
  });
  return merged.length === current.length && merged.every((asset, index) => asset === current[index])
    ? current
    : merged;
}
