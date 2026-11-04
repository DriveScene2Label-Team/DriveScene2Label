import type { Recording } from '@/api/models';

/** Pick the recording to show: the pane's explicit choice, else the newest one for the shown job (or GT-only). */
export function pickRecording(list: Recording[], jobId: number | null, explicit: number | null): Recording | undefined {
  if (explicit != null) {
    const found = list.find((r) => r.recordingId === explicit);
    if (found) return found;
  }
  const same = list.filter((r) => r.jobId === jobId).sort((a, b) => b.createdAt - a.createdAt || b.recordingId - a.recordingId);
  return same.find((r) => r.status !== 'FAILED') ?? same[0];
}

export interface RecordingPlan {
  /** Recording of the pane's target (shown job, or GT-only when no job). */
  primary: Recording | undefined;
  /** READY GT-only recording kept on screen while the job's own recording does not exist yet or is being made. */
  fallback: Recording | undefined;
  /** The target has no recording at all: request one (once). A FAILED one is retried only by the user. */
  autoCreate: boolean;
}

/**
 * When a label job finishes the pane switches to that job, which has no recording yet. Instead of dropping the 3D
 * view, keep the GT recording visible and ask the server for the job's recording; switch once it is READY.
 */
export function planRecording(list: Recording[], targetJob: number | null, explicit: number | null): RecordingPlan {
  const primary = pickRecording(list, targetJob, explicit);
  const waiting = !primary || primary.status === 'PENDING' || primary.status === 'RUNNING';
  const fallback = targetJob != null && waiting ? pickRecording(list.filter((r) => r.status === 'READY'), null, null) : undefined;
  return { primary, fallback, autoCreate: primary === undefined };
}
