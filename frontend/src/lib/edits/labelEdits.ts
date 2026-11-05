import type { QueryClient } from '@tanstack/react-query';
import type { EditResultDto, EditScope } from '@/api/dto';
import { requestJson } from '@/api/http';
import { toLabelEdit } from '@/api/mappers';
import type { BoxView, LabelEdit } from '@/api/models';

/**
 * Label edits (rename / delete / revert). Each call is a single request: edits are not retried automatically because a
 * lost response may already have been applied — the history tab shows the server's state after a refresh.
 * Originals stay unchanged on the server; the REST views return the effective class and leave deleted boxes out.
 */
export async function renameBox(box: BoxView, label: string, scope: EditScope): Promise<LabelEdit> {
  const path = box.source === 'GT' ? `/api/annotations/${box.id}` : `/api/auto-label/predictions/${box.id}`;
  const body = box.source === 'GT' ? { label, scope } : { label };
  const res = await requestJson<EditResultDto>(path, { method: 'PATCH', body });
  return toLabelEdit(res.data.edit);
}

export async function deleteBox(box: BoxView, scope: EditScope): Promise<LabelEdit> {
  const path = box.source === 'GT' ? `/api/annotations/${box.id}?scope=${scope}` : `/api/auto-label/predictions/${box.id}`;
  const res = await requestJson<EditResultDto>(path, { method: 'DELETE' });
  return toLabelEdit(res.data.edit);
}

export async function revertEdit(editId: number): Promise<LabelEdit> {
  const res = await requestJson<EditResultDto>(`/api/label-edits/${editId}/revert`, { method: 'POST' });
  return toLabelEdit(res.data.edit);
}

/**
 * After an edit or revert: re-read only what it touched. GT → per-sample annotations and the scene instance index;
 * prediction → that job's results (a GET of finished results, never a new VESPA run). History always.
 */
export async function afterEdit(qc: QueryClient, edit: LabelEdit): Promise<void> {
  const tasks: Array<Promise<unknown>> = [qc.invalidateQueries({ queryKey: ['labelEdits', edit.sceneId] })];
  if (edit.targetType === 'ANNOTATION') {
    tasks.push(qc.invalidateQueries({ queryKey: ['annotations'] }));
    tasks.push(qc.invalidateQueries({ queryKey: ['sceneInstances', edit.sceneId] }));
  } else if (edit.jobId != null) {
    tasks.push(qc.invalidateQueries({ queryKey: ['jobResults', edit.jobId] }));
  }
  await Promise.all(tasks);
}

/** Korean particle after a word, chosen by its last sound (also for latin letters / digits, e.g. "car를", "scene-0061과"). */
export function josa(word: string, pair: '을/를' | '이/가' | '은/는' | '과/와' | '으로/로'): string {
  const ch = word.trim().slice(-1);
  const code = ch.charCodeAt(0);
  let fin: 0 | 1 | 'l';
  if (code >= 0xac00 && code <= 0xd7a3) {
    const j = (code - 0xac00) % 28;
    fin = j === 0 ? 0 : j === 8 ? 'l' : 1;
  } else if (/[0-9]/.test(ch)) fin = ({ 0: 1, 1: 'l', 2: 0, 3: 1, 4: 0, 5: 0, 6: 1, 7: 'l', 8: 'l', 9: 0 } as const)[Number(ch) as 0];
  else if (/l/i.test(ch)) fin = 'l';
  else if (/[mnk]/i.test(ch)) fin = 1;
  else fin = 0;
  if (pair === '으로/로') return word + (fin && fin !== 'l' ? '으로' : '로');
  const [a, b] = pair.split('/') as [string, string];
  return word + (fin ? a : b);
}
