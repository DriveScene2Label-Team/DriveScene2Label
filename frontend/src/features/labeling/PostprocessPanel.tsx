import { useState } from 'react';
import type { JobResults, SampleRef, Scene } from '@/api/models';
import { describeError, requestJson } from '@/api/http';
import { saveReceipt } from '@/lib/jobs/receipts';
import { useServer } from '@/stores/server';
import { useWorkspace, type PaneId } from '@/stores/workspace';

export function PostprocessPanel({ paneId, scene, samples, results, disabled }: { paneId: PaneId; scene: Scene; samples: SampleRef[]; results: JobResults; disabled: boolean }) {
  const pane = useWorkspace((s) => s.panes[paneId]);
  const selectBox = useWorkspace((s) => s.selectBox);
  const [refs, setRefs] = useState<Record<string, string>>({});
  const [requestKey, setRequestKey] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const frame = pane.displayedSampleToken;
  const boxes = frame ? (results.boxesBySample.get(frame) ?? []).filter((b) => b.trackId != null) : [];
  const selected = boxes.find((b) => b.key === pane.selectedBoxKey);
  const hasTracks = [...results.boxesBySample.values()].some((list) => list.some((box) => box.trackId != null));
  if (!hasTracks) return <p className="help">이 결과에는 객체 추적 정보가 없어요. 후처리를 사용하려면 새 라벨 작업을 실행해 주세요.</p>;
  const update = (next: Record<string, string>) => { setRefs(next); setRequestKey(crypto.randomUUID()); setError(''); };
  const submit = async () => {
    if (!results.classMode || !Object.keys(refs).length || busy || disabled) return;
    const instanceId = useServer.getState().scope;
    const generation = pane.generation;
    setBusy(true); setError('');
    try {
      const { data } = await requestJson<{ jobId: number }>(`/api/auto-label/jobs/${results.jobId}/postprocess`, {
        method: 'POST', body: { references: refs }, headers: { 'Idempotency-Key': requestKey },
      });
      saveReceipt({ instanceId, jobId: data.jobId, datasetId: scene.datasetId, datasetChecksum: null, sceneId: scene.id,
        sceneToken: scene.token, sceneName: scene.name, paneId, classMode: results.classMode, idempotencyKey: requestKey, requestedAt: Date.now() });
      const current = useWorkspace.getState().panes[paneId];
      if (useServer.getState().scope === instanceId && current.generation === generation && current.sceneId === scene.id && current.datasetId === scene.datasetId) useWorkspace.getState().watchJob(paneId, data.jobId);
    } catch (failure) { setError(describeError(failure)); }
    finally { setBusy(false); }
  };
  return <section className="job-card">
    <h3>객체 기준 후처리</h3>
    <p className="help">원본 작업 #{results.jobId}을 보존하고 새 결과를 만들어요. 기준 박스의 크기와 방향을 같은 객체의 다른 프레임에 적용해요. 각 프레임의 바닥 중심 위치는 유지해요.</p>
    <label>현재 프레임의 객체
      <select aria-label="후처리 기준 객체" value={selected?.key ?? ''} disabled={busy || !boxes.length} onChange={(e) => selectBox(paneId, e.target.value || null)}>
        <option value="">박스를 선택하세요</option>
        {boxes.map((box) => <option key={box.key} value={box.key}>T{box.trackId} · {box.label}</option>)}
      </select>
    </label>
    <button className="btn btn--sm btn--weak" disabled={busy || selected?.trackId == null || !frame} onClick={() => { if (selected?.trackId != null && frame) update({ ...refs, [selected.trackId]: frame }); }}>현재 프레임을 기준으로 추가</button>
    <ul>{Object.entries(refs).map(([track, token]) => <li key={track}>T{track} · 기준 프레임 {samples.findIndex((sample) => sample.token === token)}
      <button aria-label={`T${track} 기준 제거`} className="btn btn--sm btn--ghost" disabled={busy} onClick={() => { const next = { ...refs }; delete next[track]; update(next); }}>제거</button></li>)}</ul>
    <button className="btn btn--primary" disabled={busy || disabled || !Object.keys(refs).length} onClick={() => void submit()}>{busy ? '후처리 요청 중…' : error ? '같은 후처리 요청 다시 보내기' : '후처리 결과 생성'}</button>
    {error && <p className="alert" role="alert">{error}</p>}
    <p className="help">프레임 번호는 0부터 시작해요. T 번호는 이 작업 안에서만 유효해요.</p>
  </section>;
}
