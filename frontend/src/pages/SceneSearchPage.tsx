import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { describeError } from '@/api/http';
import { datasetsQuery, scenesQuery, searchQuery } from '@/api/queries';
import { capabilityMessage, stateLabel } from '@/api/system';
import { compareUrl, parseId, searchUrl } from '@/app/urls';
import { AppMark } from '@/components/AppMark';
import { Icon } from '@/components/Icon';
import { MoreMenu } from '@/components/MoreMenu';
import { josa } from '@/lib/edits/labelEdits';
import { SceneCard, type CardData } from '@/features/scenes/SceneCard';
import { SearchIndexStatus } from '@/features/scenes/SearchIndexStatus';
import { DataOriginBadge } from '@/features/system/DataOriginBadge';
import { useSystemStatus } from '@/features/system/useSystemStatus';
import { announce, toast } from '@/stores/toast';

const EXAMPLES = ['rainy night road', 'pedestrians crossing at intersection', 'construction zone with trucks', 'parking lot'];
type SortKey = 'score' | 'name' | 'frames';

interface Pick { datasetId: number; sceneId: number; name: string; sample: string | null }

/** Scene library: natural-language search over the dataset's scenes, the scene list, and picking two scenes to compare. */
export function SceneSearchPage() {
  const [sp, setSp] = useSearchParams();
  const navigate = useNavigate();
  const datasetParam = parseId(sp.get('dataset'));
  const q = (sp.get('q') ?? '').trim();
  const [input, setInput] = useState(q);
  const [picking, setPicking] = useState(false);
  const [picked, setPicked] = useState<Pick[]>([]);
  const [sort, setSort] = useState<SortKey | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const compareBtn = useRef<HTMLButtonElement>(null);
  useEffect(() => { setInput(q); setSort(null); }, [q]);

  const datasets = useQuery(datasetsQuery());
  const dataset = datasets.data?.find((d) => d.id === datasetParam);
  // No dataset in the URL: use the first dataset the server lists (never a hard-coded id).
  useEffect(() => {
    if (datasetParam == null && datasets.data?.[0]) setSp((p) => { p.set('dataset', String(datasets.data[0]!.id)); return p; }, { replace: true });
  }, [datasetParam, datasets.data, setSp]);

  const datasetId = dataset?.id ?? null;
  const scenes = useQuery({ ...scenesQuery(datasetId ?? -1), enabled: datasetId != null });
  const system = useSystemStatus(datasetId);
  const searchCap = system.capability('search');
  const searchBlocked = searchCap.state === 'UNAVAILABLE';
  const search = useQuery({
    ...searchQuery({ q, datasetId, k: 10, aggregation: 'TOP_K_AVERAGE', imageTopK: 3, keyframesOnly: true }),
    enabled: !!q && datasetId != null && !system.isPending && !searchBlocked,
  });
  useEffect(() => {
    if (search.data) announce(search.data.hits.length ? `“${q}” 검색 결과 ${search.data.hits.length}개` : `“${q}” 검색 결과 없음`);
  }, [search.data, q]);
  useEffect(() => {
    if (!picking) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { setPicking(false); setPicked([]); } };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [picking]);

  const submit = (text: string) => {
    const t = text.trim();
    setSp((p) => { if (t) p.set('q', t); else p.delete('q'); return p; });
  };
  const clear = () => { setInput(''); submit(''); inputRef.current?.focus(); };
  const togglePick = (item: Pick) => {
    const has = picked.some((x) => x.datasetId === item.datasetId && x.sceneId === item.sceneId);
    if (!has && picked.length >= 2) { toast('비교할 씬은 두 개까지 고를 수 있어요'); return; }
    const next = has ? picked.filter((x) => !(x.datasetId === item.datasetId && x.sceneId === item.sceneId)) : [...picked, item];
    setPicked(next);
    if (next.length === 2) window.setTimeout(() => compareBtn.current?.focus({ preventScroll: true }), 0);
  };
  const isPicked = (d: number, s: number) => picked.some((x) => x.datasetId === d && x.sceneId === s);
  const openCompare = () => {
    const [a, b] = picked;
    if (!a || !b) return;
    navigate(compareUrl({
      A: { datasetId: a.datasetId, sceneId: a.sceneId, sample: a.sample, job: null },
      B: { datasetId: b.datasetId, sceneId: b.sceneId, sample: b.sample, job: null },
      sync: false, active: 'A',
    }));
  };

  const frames = useMemo(() => new Map(scenes.data?.map((s) => [s.id, s.nbrSamples]) ?? []), [scenes.data]);
  const searching = !!q && !searchBlocked;
  const sortKey: SortKey = sort && (sort !== 'score' || searching) ? sort : searching ? 'score' : 'name';

  let results: React.ReactNode;
  const bar = (title: React.ReactNode, count: number | null) => (
    <div className="lib-bar">
      <h2>{title}{count != null && <span className="count">{count}</span>}</h2>
      <span className="gap" />
      {!!count && (
        <label className="sort">정렬
          <select className="popup popup--sm" value={sortKey} onChange={(e) => setSort(e.currentTarget.value as SortKey)}>
            {searching && <option value="score">일치도</option>}
            <option value="name">이름</option>
            <option value="frames">프레임 수</option>
          </select>
        </label>
      )}
    </div>
  );
  const skeleton = (
    <div className="grid" aria-hidden="true">
      {Array.from({ length: 6 }, (_, i) => <div key={i} className="card skeleton-card"><span className="card-thumb" /><div className="skeleton-line" /><div className="skeleton-line short" /></div>)}
    </div>
  );
  const grid = (rows: CardData[]) => {
    const dir = sortKey === 'name' ? 1 : -1;
    const v = (r: CardData) => (sortKey === 'score' ? r.hit?.score ?? -1 : sortKey === 'frames' ? r.nbrSamples ?? -1 : r.name);
    const sorted = [...rows].sort((a, b) => { const x = v(a); const y = v(b); return (x < y ? -1 : x > y ? 1 : 0) * dir || (a.name < b.name ? -1 : 1); });
    return (
      <div className="grid">
        {sorted.map((r) => (
          <SceneCard key={`${r.datasetId}-${r.sceneId}`} data={r} picking={picking} picked={isPicked(r.datasetId, r.sceneId)}
            onPick={() => togglePick({ datasetId: r.datasetId, sceneId: r.sceneId, name: r.name, sample: r.hit?.bestSampleToken ?? null })} />
        ))}
      </div>
    );
  };
  const allBtn = <button type="button" className="btn plain" onClick={clear}>모든 씬 보기</button>;

  if (datasets.isError) {
    results = <ErrorBlock title="데이터셋 목록을 불러오지 못했어요" detail={describeError(datasets.error)} actions={<button type="button" className="btn" onClick={() => void datasets.refetch()}>다시 불러오기</button>} />;
  } else if (datasets.data && datasets.data.length === 0) {
    results = <div className="empty"><Icon name="info" /><b>등록된 데이터셋이 없어요</b><p>nuScenes 원본을 올리고 씬을 선택해 라벨링하세요.</p><Link className="btn primary" to="/uploads">원본 데이터 업로드</Link></div>;
  } else if (datasetParam != null && datasets.data && !dataset) {
    results = <ErrorBlock title="링크의 데이터셋을 찾을 수 없어요" detail={`dataset ${datasetParam}은(는) 이 서버에 없어요.`} actions={<button type="button" className="btn" onClick={() => navigate(searchUrl(null))}>데이터셋 다시 고르기</button>} />;
  } else if (q && searchBlocked) {
    results = <ErrorBlock title="이 데이터셋에서는 지금 검색할 수 없어요" detail={capabilityMessage(searchCap) ?? "검색 기능을 사용할 수 없어요."} actions={allBtn} />;
  } else if (q) {
    if (datasetId == null || search.isPending) results = <>{bar(<><span className="spinner" aria-hidden="true" />“{q}” 검색 중</>, null)}{skeleton}</>;
    else if (search.isError) results = <ErrorBlock title="검색하지 못했어요" detail={describeError(search.error)} actions={<><button type="button" className="btn" onClick={() => void search.refetch()}>다시 검색</button>{allBtn}</>} />;
    else if (!search.data.hits.length) {
      results = (
        <div className="empty">
          <Icon name="search" />
          <b>“{q}”에 맞는 씬이 없어요</b>
          <p>날씨, 시간대, 장소, 객체 같은 단어를 넣어 다시 검색해 보세요. 이 데이터셋에 이미지 임베딩이 아직 없을 때도 결과가 비어요.</p>
          <div className="suggest">
            {EXAMPLES.slice(0, 3).map((ex) => <button key={ex} type="button" className="token" onClick={() => { setInput(ex); submit(ex); }}>{ex}</button>)}
            <button type="button" className="btn plain sm" onClick={clear}>모든 씬 보기</button>
          </div>
        </div>
      );
    } else {
      const rows: CardData[] = search.data.hits.map((h) => ({
        datasetId: h.datasetId, sceneId: h.sceneId, name: h.sceneName, description: h.description, nbrSamples: frames.get(h.sceneId) ?? null,
        hit: { score: h.score, matchScore: h.matchScore, contentUrl: h.contentUrl, bestSampleToken: h.bestSampleToken },
      }));
      results = <>{bar(`“${search.data.query}” 검색 결과`, rows.length)}{grid(rows)}</>;
    }
  } else if (scenes.isError) {
    results = <ErrorBlock title="씬 목록을 불러오지 못했어요" detail={describeError(scenes.error)} actions={<button type="button" className="btn" onClick={() => void scenes.refetch()}>다시 불러오기</button>} />;
  } else if (!scenes.data) {
    results = <>{bar(<><span className="spinner" aria-hidden="true" />모든 씬</>, null)}{skeleton}</>;
  } else if (!scenes.data.length) {
    results = <div className="empty"><Icon name="info" /><b>이 데이터셋에는 씬이 없어요</b></div>;
  } else {
    const rows: CardData[] = scenes.data.map((s) => ({ datasetId: s.datasetId, sceneId: s.id, name: s.name, description: s.description, nbrSamples: s.nbrSamples }));
    results = <>{bar('모든 씬', rows.length)}{grid(rows)}</>;
  }

  return (
    <div className="app app--lib">
      <header className="toolbar">
        <div className="tb-left"><AppMark to={searchUrl(datasetId)} /></div>
        <div />
        <div className="tb-right">
          <Link className="btn primary" to="/uploads">데이터 업로드</Link>
          {picking
            ? <button type="button" className="btn plain" onClick={() => { setPicking(false); setPicked([]); }}>선택 취소</button>
            : <button type="button" className="btn weak" onClick={() => { setPicking(true); setPicked([]); }} title="두 씬을 골라 나란히 비교해요">비교할 씬 고르기</button>}
          <MoreMenu workspace={false} />
        </div>
      </header>
      <main className="library" id="main">
        <div className={picking ? 'lib is-picking' : 'lib'}>
          <section className="lib-hero">
            <div className="lib-eyebrow">
              {datasets.isPending ? <span>데이터셋 불러오는 중</span> : datasets.data && datasets.data.length > 0 && (
                <select className="popup popup--sm" aria-label="데이터셋" value={datasetId ?? ''} onChange={(e) => navigate(searchUrl(Number(e.currentTarget.value)))}>
                  {datasetId == null && <option value="">데이터셋 선택</option>}
                  {datasets.data.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
                </select>
              )}
              {scenes.data && <span>씬 {scenes.data.length}개</span>}
              <DataOriginBadge datasetId={datasetId} />
            </div>
            <h1 className="lib-title" id="page-title" tabIndex={-1}>어떤 주행 장면을 찾고 있나요?</h1>
            <p className="lib-lead">씬을 선택해 라벨을 생성·수정하세요. 문장으로 원하는 장면을 검색할 수도 있어요.</p>
            <form className="searchfield" role="search" onSubmit={(e) => { e.preventDefault(); submit(input); }}>
              <Icon name="search" />
              <label className="sr-only" htmlFor="q">장면 설명으로 검색</label>
              <input id="q" ref={inputRef} type="search" autoComplete="off" spellCheck={false} placeholder="예: rainy night road, parking lot" value={input} maxLength={500}
                onChange={(e) => setInput(e.currentTarget.value)} />
              {input && <button type="button" className="clear" onClick={clear} aria-label="검색어 지우기"><Icon name="close" /></button>}
              <button className="btn primary sm" type="submit" disabled={datasetId == null || searchBlocked}>검색</button>
            </form>
            {datasetId != null && searchCap.state !== 'READY' && searchCap.reasonCode !== 'STATUS_CHECKING' && (
              <div className="notice lib-notice" role="status" data-testid="search-readiness" data-reason={searchCap.reasonCode ?? ''}>
                <Icon name="warn" />
                <span><b>검색 {stateLabel(searchCap.state)}</b> · {capabilityMessage(searchCap)}{searchBlocked ? ' 씬 목록 탐색은 그대로 쓸 수 있어요.' : ''}{' '}
                  <button type="button" className="link" onClick={() => void system.recheck(searchCap)} disabled={system.refreshing}>다시 확인</button></span>
              </div>
            )}
            {datasetId != null && <SearchIndexStatus datasetId={datasetId} />}
            <div className="suggest">
              <span className="lbl">이렇게 찾아보세요</span>
              {EXAMPLES.map((ex) => <button key={ex} type="button" className="token" onClick={() => { setInput(ex); submit(ex); }}>{ex}</button>)}
            </div>
          </section>
          <section id="results" aria-live="polite">{results}</section>
          <p className="lib-note">씬 이름과 설명은 데이터셋 원본을 따라요. 일치도는 검색어와 카메라 이미지 임베딩의 코사인 유사도를 0~100점으로 보정한 값이라 확률이나 정확도가 아니에요(0점 ≈ 관련 없는 문장, 100점 ≈ 짧은 검색어가 맞는 씬에서 받는 대표 점수). 80점 이상은 잘 맞음, 50~79점은 관련 있음, 50점 미만은 약함으로 표시하지만, 맞지 않는 장면도 80점을 넘을 수 있으니 이미지로 확인해 주세요. 영문 검색어를 권장해요(한국어 검색 품질은 검증되지 않았어요).</p>
        </div>
      </main>
      {picking && (
        <div className="pickbar" role="region" aria-label="비교할 씬">
          <span className="pick-dots" aria-hidden="true"><i className={picked.length > 0 ? 'on' : ''} /><i className={picked.length > 1 ? 'on' : ''} /></span>
          <span className="pick-text" aria-live="polite">
            {picked.length === 2 ? `${josa(picked[0]!.name, '과/와')} ${picked[1]!.name}` : picked.length === 1 ? <>{picked[0]!.name}<span className="muted"> 그리고 하나 더</span></> : <span className="muted">비교할 씬 두 개를 골라 주세요</span>}
          </span>
          <button ref={compareBtn} type="button" className="btn primary" onClick={openCompare} disabled={picked.length !== 2}>비교하기</button>
        </div>
      )}
    </div>
  );
}

function ErrorBlock({ title, detail, actions }: { title: string; detail: string; actions?: React.ReactNode }) {
  return (
    <div className="empty empty--err" role="alert">
      <Icon name="warn" />
      <b>{title}</b>
      <p>{detail}</p>
      {actions && <div className="suggest">{actions}</div>}
    </div>
  );
}
