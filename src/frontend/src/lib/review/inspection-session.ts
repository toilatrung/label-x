import type { QueueName, RankedFrame } from './types';

export interface InspectionSession {
  runId: number;
  queue: QueueName;
  frames: RankedFrame[];
  currentFrameId?: number;
}
const key = (userId: number, datasetId: number) => `labelx:inspection:${userId}:${datasetId}`;
const positiveId = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value > 0;

/** Navigation hints only. Server-issued grants remain the sole lease authority. */
export function readInspectionSession(userId: number, datasetId: number): InspectionSession | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(key(userId, datasetId)) ?? 'null');
    if (!value || !positiveId(value.runId) || !['risk', 'random'].includes(value.queue) || !Array.isArray(value.frames)) return null;
    const frames = value.frames.filter((frame: RankedFrame) => positiveId(frame?.frame_id)
      && positiveId(frame?.frame_key?.cvat_task_id) && Number.isSafeInteger(frame?.frame_key?.frame_number) && frame.frame_key.frame_number >= 0).slice(0, 2000);
    return { runId: value.runId, queue: value.queue, frames,
      currentFrameId: positiveId(value.currentFrameId) ? value.currentFrameId : undefined };
  } catch { return null; }
}

export function writeInspectionSession(userId: number, datasetId: number, value: InspectionSession): void {
  try { sessionStorage.setItem(key(userId, datasetId), JSON.stringify(value)); } catch { /* Storage may be unavailable. */ }
}
