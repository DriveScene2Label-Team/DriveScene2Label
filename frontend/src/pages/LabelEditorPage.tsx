import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, Upload, Save, ArrowLeft, RotateCcw, Plus, Trash2 } from 'lucide-react';
import { getLabel, labelHistory, labelsFromJob, listLabels, saveLabel, uploadLabels, type LabelBox, type LabelData, type LabelDetail } from '@/api/labels';
import { describeError, isApiError } from '@/api/http';
import { changeBox, EDIT_CLASSES, invalidGeometry, newBox, rotateBox } from '@/features/labeling/editing';
import { DatasetUpload } from '@/features/labeling/DatasetUpload';
import '@/styles/labels.css';

export default function LabelEditorPage() {
  const [params, setParams] = useSearchParams();
  const client = useQueryClient();
  const [page, setPage] = useState(0);
  const documents = useQuery({ queryKey: ['label-documents', page], queryFn: () => listLabels(page) });
  const [detail, setDetail] = useState<LabelDetail | null>(null);
  const [draft, setDraft] = useState<LabelData | null>(null);
  const [frame, setFrame] = useState('');
  const [selected, setSelected] = useState<number | null>(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState('');
  const [step, setStep] = useState(0.1);
  const id = Number(params.get('id'));
  const job = Number(params.get('job'));
  const history = useQuery({ queryKey: ['label-history', detail?.document.id, detail?.document.headRevision], queryFn: () => labelHistory(detail!.document.id), enabled: detail != null });

  const load = (value: LabelDetail) => {
    setDetail(value); setDraft(structuredClone(value.data)); setFrame(Object.keys(value.data.results)[0] ?? '');
    setSelected(null); setDirty(false); setNote(''); setError(null);
  };
  useEffect(() => {
    if (!Number.isSafeInteger(id) || id <= 0) return;
    let active = true;
    setBusy(true);
    void getLabel(id).then((value) => { if (active) load(value); }).catch((e: unknown) => { if (active) setError(describeError(e)); }).finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [id]);
  useEffect(() => {
    const preventLoss = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', preventLoss);
    return () => window.removeEventListener('beforeunload', preventLoss);
  }, [dirty]);
  const discard = () => !dirty || window.confirm('저장하지 않은 수정사항을 버리고 이동할까요?');
  const run = async (operation: () => Promise<void>) => {
    setBusy(true); setError(null); setMessage('');
    try { await operation(); }
    catch (e) { setError(isApiError(e) ? describeError(e) : e instanceof Error ? e.message : '요청을 처리하지 못했습니다.'); }
    finally { setBusy(false); }
  };
  const accept = (value: LabelDetail) => {
    load(value); setParams({ id: String(value.document.id) }, { replace: true });
    void client.invalidateQueries({ queryKey: ['label-documents'] });
  };
  const boxes = draft?.results[frame] ?? [];
  const box = selected == null ? null : boxes[selected] ?? null;
  const edit = (update: (value: LabelBox) => void) => {
    if (!draft || selected == null || busy) return;
    setDraft(changeBox(draft, frame, selected, update)); setDirty(true); setMessage('');
  };
  const frames = Object.keys(draft?.results ?? {});
  const invalid = draft ? invalidGeometry(draft) : false;

  return (
    <div className="labels-page">
      <header className="topbar">
        <Link className="btn btn--ghost" to="/scenes" onClick={(e) => { if (!discard()) e.preventDefault(); }}><ArrowLeft className="icon" />씬 목록</Link>
        <h1>파일 · 라벨 편집</h1>
        <span className="topbar-end">{dirty ? '저장하지 않은 수정사항' : detail ? `저장된 버전 v${detail.revision}` : '파일을 올려 시작하세요'}</span>
      </header>
      <main className="labels-layout">
        <aside className="labels-library">
          <DatasetUpload disabled={busy || dirty} />
          <h2>라벨 JSON 업로드</h2>
          <p className="note">nuScenes / VESPA의 results 형식 · 최대 20MB</p>
          <input aria-label="라벨 JSON 파일" type="file" accept=".json,application/json" disabled={busy} onChange={(e) => setFile(e.currentTarget.files?.[0] ?? null)} />
          <button className="btn btn--primary" disabled={!file || busy} onClick={() => {
            if (!file || !discard()) return;
            if (file.size > 20 * 1024 * 1024) { setError('20MB 이하의 JSON 파일을 선택해 주세요.'); return; }
            void run(async () => { accept(await uploadLabels(file)); setMessage('원본 파일을 보관했습니다. 이제 라벨을 수정할 수 있어요.'); });
          }}><Upload className="icon" />파일 업로드</button>
          {job > 0 && <button className="btn btn--weak" disabled={busy} onClick={() => { if (discard()) void run(async () => { accept(await labelsFromJob(job)); }); }}>자동 라벨 작업 #{job} 불러오기</button>}
          <h2>저장한 라벨</h2>
          {documents.isPending && <p role="status">목록 불러오는 중…</p>}
          {documents.isError && <p role="alert">{describeError(documents.error)} <button onClick={() => void documents.refetch()}>다시 시도</button></p>}
          {documents.data?.length === 0 && <p className="note">저장된 라벨이 없습니다.</p>}
          <ul className="labels-documents">{documents.data?.map((document) => <li key={document.id}>
            <button disabled={busy} aria-pressed={document.id === detail?.document.id} onClick={() => { if (discard()) setParams({ id: String(document.id) }); }}>
              <strong>{document.name}</strong><span>v{document.headRevision} · {document.sourceType === 'UPLOAD' ? '업로드' : '자동 라벨'}</span>
            </button>
          </li>)}</ul>
          <div className="labels-actions"><button className="btn btn--sm" disabled={page === 0 || busy} onClick={() => setPage(page - 1)}>이전</button><span>{page + 1} 페이지</span><button className="btn btn--sm" disabled={documents.data?.length !== 50 || busy} onClick={() => setPage(page + 1)}>다음</button></div>
        </aside>
        <section className="labels-editor" aria-label="라벨 편집기">
          {error && <p className="labels-error" role="alert">{error}</p>}
          {message && <p className="labels-success" role="status">{message}</p>}
          {busy && <p role="status">처리 중…</p>}
          {detail && draft ? <>
            <div className="labels-actions">
              <h2>{detail.document.name}</h2>
              <label>저장 버전 <select aria-label="저장 버전" disabled={busy} value={detail.revision} onChange={(e) => {
                const revision = Number(e.currentTarget.value);
                if (discard()) void run(async () => load(await getLabel(detail.document.id, revision)));
              }}>{history.data?.map((revision) => <option key={revision.number} value={revision.number}>v{revision.number}{revision.note ? ` · ${revision.note}` : ''}</option>)}</select></label>
              <a className="btn btn--weak" href={`/api/label-documents/${detail.document.id}/original`}>원본 다운로드</a>
              <a className="btn btn--weak" href={`/api/label-documents/${detail.document.id}/download?revision=${detail.revision}`}><Download className="icon" />저장본 v{detail.revision} 다운로드</a>
            </div>
            <div className="labels-actions">
              <label>프레임 <select aria-label="편집 프레임" value={frame} disabled={busy} onChange={(e) => { setFrame(e.currentTarget.value); setSelected(null); }}>{frames.map((token, index) => <option key={token} value={token}>{index + 1} · {token}</option>)}</select></label>
              <button className="btn btn--weak" disabled={busy || !frame} onClick={() => {
                const next = structuredClone(draft); const index = next.results[frame]!.length;
                next.results[frame]!.push(newBox(frame, boxes[0]?.translation)); setDraft(next); setSelected(index); setDirty(true);
              }}><Plus className="icon" />박스 추가</button>
              <span>{boxes.length}개 객체</span>
            </div>
            <div className="labels-canvas-layout">
              <div><Overview boxes={boxes} baseline={detail.data.results[frame] ?? []} selected={selected} onSelect={setSelected} /><p className="note">WORLD 좌표를 위에서 본 XY 평면입니다. 박스를 클릭한 뒤 오른쪽에서 수정하세요.</p></div>
              <div className="labels-controls">
                <label>객체 <select aria-label="편집 객체" value={selected ?? ''} disabled={busy} onChange={(e) => setSelected(e.currentTarget.value === '' ? null : Number(e.currentTarget.value))}>
                  <option value="">객체 선택</option>{boxes.map((item, index) => <option key={index} value={index}>{index + 1} · {item.detection_name}</option>)}
                </select></label>
                {box && <fieldset disabled={busy}>
                  <legend>선택한 객체 수정</legend>
                  <label>클래스 <select aria-label="라벨 클래스" value={box.detection_name} onChange={(e) => edit((value) => { value.detection_name = e.currentTarget.value; })}>{EDIT_CLASSES.map((name) => <option key={name}>{name}</option>)}</select></label>
                  <NumberFields title="중심 위치 (m)" names={['X', 'Y', 'Z']} values={box.translation} onChange={(index, value) => edit((item) => { item.translation[index] = value; })} />
                  <NumberFields title="크기 (m)" names={['W', 'L', 'H']} values={box.size} onChange={(index, value) => edit((item) => { item.size[index] = value; })} />
                  <label>이동 단위 (m) <input type="number" aria-label="이동 단위" min="0.01" step="0.1" value={step} onChange={(e) => { const value = e.currentTarget.valueAsNumber; if (Number.isFinite(value) && value > 0) setStep(value); }} /></label>
                  <div className="labels-actions">{(['X', 'Y', 'Z'] as const).flatMap((axis, index) => [-1, 1].map((direction) => <button className="btn btn--sm" key={`${axis}${direction}`} onClick={() => edit((value) => { value.translation[index] = value.translation[index]! + direction * step; })}>{axis} {direction < 0 ? '−' : '+'}</button>))}</div>
                  <div className="labels-actions"><button className="btn btn--sm" onClick={() => edit((value) => rotateBox(value, -5))}>회전 −5°</button><button className="btn btn--sm" onClick={() => edit((value) => rotateBox(value, 5))}>회전 +5°</button></div>
                  <NumberFields title="회전 quaternion" names={['W', 'X', 'Y', 'Z']} values={box.rotation} onChange={(index, value) => edit((item) => { item.rotation[index] = value; })} />
                  <button className="btn btn--sm" onClick={() => edit((value) => { const norm = Math.hypot(...value.rotation); if (norm > 0) value.rotation = value.rotation.map((n) => n / norm) as LabelBox['rotation']; })}>회전 정규화</button>
                  <button className="btn btn--weak" onClick={() => { const next = structuredClone(draft); next.results[frame]!.splice(selected!, 1); setDraft(next); setSelected(null); setDirty(true); }}><Trash2 className="icon" />선택 박스 삭제</button>
                </fieldset>}
              </div>
            </div>
            <div className="labels-save">
              <label>수정 메모 <input aria-label="수정 메모" maxLength={500} value={note} disabled={busy} onChange={(e) => setNote(e.currentTarget.value)} placeholder="예: 차량 클래스와 박스 위치 보정" /></label>
              {invalid && <p role="alert">크기는 0보다 커야 하며, 회전 quaternion을 정규화해야 저장할 수 있습니다.</p>}
              <div className="labels-actions">
                <button className="btn btn--primary" disabled={!dirty || busy || invalid} onClick={() => void run(async () => {
                  const saved = await saveLabel(detail.document.id, detail.document.version, draft, note);
                  load(saved); void client.invalidateQueries({ queryKey: ['label-documents'] }); setMessage(`수정본 v${saved.revision}을 서버에 저장했습니다.`);
                })}><Save className="icon" />수정본 저장</button>
                <button className="btn btn--weak" disabled={!dirty || busy} onClick={() => { if (discard()) load(detail); }}><RotateCcw className="icon" />저장 상태로 되돌리기</button>
                {dirty && <span className="note">화면의 수정사항은 저장 버튼을 눌러야 다운로드에 반영됩니다.</span>}
              </div>
            </div>
          </> : <div className="labels-empty"><h2>라벨 파일을 올리고 수정해 보세요</h2><p>왼쪽에서 JSON을 업로드하거나, 씬 작업대에서 완료된 자동 라벨 결과의 편집 버튼을 누르세요.</p><p>원본과 모든 저장 버전을 서버에 따로 보관합니다.</p></div>}
        </section>
      </main>
    </div>
  );
}

function NumberFields({ title, names, values, onChange }: { title: string; names: string[]; values: number[]; onChange: (index: number, value: number) => void }) {
  return <div className="labels-numbers"><b>{title}</b><div>{values.map((value, index) => <label key={index}>{names[index]}<input type="number" step="0.1" aria-label={`${title} ${names[index]}`} value={value} onChange={(e) => { const next = e.currentTarget.valueAsNumber; if (Number.isFinite(next)) onChange(index, next); }} /></label>)}</div></div>;
}

function Overview({ boxes, baseline, selected, onSelect }: { boxes: LabelBox[]; baseline: LabelBox[]; selected: number | null; onSelect: (index: number) => void }) {
  const reference = baseline[0]?.translation ?? [0, 0, 0];
  const extent = baseline.reduce((max, box) => Math.max(max, Math.abs(box.translation[0] - reference[0]) + 5, Math.abs(box.translation[1] - reference[1]) + 5), 20);
  const points = (box: LabelBox) => {
    const [w, x, y, z] = box.rotation;
    return [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, b]) => {
      const localX = a! * box.size[1] / 2, localY = b! * box.size[0] / 2;
      return `${box.translation[0] - reference[0] + (1 - 2 * (y * y + z * z)) * localX + 2 * (x * y - z * w) * localY},${-(box.translation[1] - reference[1] + 2 * (x * y + z * w) * localX + (1 - 2 * (x * x + z * z)) * localY)}`;
    }).join(' ');
  };
  return <svg className="labels-overview" viewBox={`${-extent} ${-extent} ${extent * 2} ${extent * 2}`} role="group" aria-label="WORLD XY 라벨 미리보기">
    <path d={`M${-extent} 0H${extent}M0 ${-extent}V${extent}`} stroke="#334155" strokeWidth="0.1" />
    {boxes.map((box, index) => <polygon key={index} points={points(box)} role="button" tabIndex={0} aria-label={`박스 ${index + 1} ${box.detection_name}`} aria-pressed={selected === index}
      fill={selected === index ? '#2dd4bf88' : '#38bdf833'} stroke={selected === index ? '#5eead4' : '#38bdf8'} strokeWidth={selected === index ? 0.22 : 0.12}
      onClick={() => onSelect(index)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(index); } }}><title>{box.detection_name} · {box.translation.join(', ')}</title></polygon>)}
  </svg>;
}
