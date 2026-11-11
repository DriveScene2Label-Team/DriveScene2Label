import { useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { describeError } from '@/api/http';
import { datasetsQuery, scenesQuery, searchQuery } from '@/api/queries';
import { compareUrl, parseId, searchUrl } from '@/app/urls';
import { Logo } from '@/components/Logo';
import { StateBox } from '@/components/StateBox';
import { SceneCard } from '@/features/scenes/SceneCard';
import { SearchIndexStatus } from '@/features/scenes/SearchIndexStatus';
import { capabilityMessage, stateLabel } from '@/api/system';
import { DataOriginBadge } from '@/features/system/DataOriginBadge';
import { useSystemStatus } from '@/features/system/useSystemStatus';

const EXAMPLES = ['rainy night road', 'pedestrians crossing at intersection', 'construction zone with trucks', 'parking lot'];

interface CompareItem {
  datasetId: number;
  sceneId: number;
  name: string;
  sample: string | null;
}

export function SceneSearchPage() {
  const [sp, setSp] = useSearchParams();
  const navigate = useNavigate();
  const datasetParam = parseId(sp.get('dataset'));
  const q = (sp.get('q') ?? '').trim();
  const [input, setInput] = useState(q);
  const [compare, setCompare] = useState<CompareItem[]>([]);
  useEffect(() => setInput(q), [q]);

  const datasets = useQuery(datasetsQuery());
  const dataset = datasets.data?.find((d) => d.id === datasetParam);
  // A fresh visit opens the latest upload; explicit dataset links remain stable.
  useEffect(() => {
    if (datasetParam == null && datasets.data?.length) {
      const latest = datasets.data.reduce((a, b) => a.id > b.id ? a : b);
      setSp((p) => { p.set('dataset', String(latest.id)); return p; }, { replace: true });
    }
  }, [datasetParam, datasets.data, setSp]);

  const datasetId = dataset?.id ?? null;
  const scenes = useQuery({ ...scenesQuery(datasetId ?? -1), enabled: datasetId != null });
  const system = useSystemStatus(datasetId);
  const searchCap = system.capability('search');
  // Search is a read: it is tried unless the server says it is unavailable (e.g. no embeddings for this dataset).
  const searchBlocked = searchCap.state === 'UNAVAILABLE';
  const search = useQuery({
    ...searchQuery({ q, datasetId, k: 10, aggregation: 'TOP_K_AVERAGE', imageTopK: 3, keyframesOnly: true }),
    // Wait for the readiness answer so a known-unavailable search is never sent (status errors still allow trying).
    enabled: !!q && datasetId != null && !system.isPending && !searchBlocked,
  });

  const setDataset = (id: number) => {
    // Changing dataset drops the query/results so they never mix with another dataset; compare picks keep their own context.
    navigate(searchUrl(id), { replace: false });
  };
  const submit = (text: string) => {
    const t = text.trim();
    setSp((p) => { if (t) p.set('q', t); else p.delete('q'); return p; });
  };
  const toggleCompare = (item: CompareItem) =>
    setCompare((c) => {
      const has = c.some((x) => x.sceneId === item.sceneId && x.datasetId === item.datasetId);
      if (has) return c.filter((x) => !(x.sceneId === item.sceneId && x.datasetId === item.datasetId));
      return [...c, item].slice(-2);
    });
  const isPicked = (datasetIdOf: number, sceneId: number) => compare.some((x) => x.sceneId === sceneId && x.datasetId === datasetIdOf);
  const openCompare = () => {
    const [a, b] = compare;
    if (!a) return;
    const second = b ?? a; // one scene picked → same scene on both sides (different frames allowed)
    navigate(compareUrl({
      A: { datasetId: a.datasetId, sceneId: a.sceneId, sample: a.sample, job: null },
      B: { datasetId: second.datasetId, sceneId: second.sceneId, sample: second.sample, job: null },
      sync: false, active: 'A',
    }));
  };

  return (
    <div className="app app--search">
      <header className="topbar">
        <a className="brand" href="/scenes"><Logo /><span>DriveScene2Label</span></a>
        <div className="ds-chip">
          <b>데이터셋</b>
          {datasets.isPending ? <span>불러오는 중</span> : datasets.isError ? <span>목록 오류</span> : (
            <select className="select select--sm" aria-label="데이터셋 선택" value={datasetId ?? ''} onChange={(e) => setDataset(Number(e.currentTarget.value))}>
              {datasetId == null && <option value="">선택</option>}
              {datasets.data?.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
            </select>
          )}
        </div>
        <DataOriginBadge datasetId={datasetId} />
        <Link className="btn btn--primary topbar-end" to="/labels">파일 업로드 · 라벨 편집</Link>
      </header>
      <main className="search-main">
        <section className="search-head" aria-labelledby="search-title">
          <h1 className="search-title" id="search-title">찾고 싶은 주행 장면을<br />문장으로 적어 보세요</h1>
          <p className="search-sub">nuScenes 씬을 자연어로 찾고, 6개 카메라와 LiDAR로 바로 확인할 수 있어요.</p>
          <form className="searchbar" role="search" onSubmit={(e) => { e.preventDefault(); submit(input); }}>
            <Search className="icon" aria-hidden="true" />
            <label className="sr-only" htmlFor="q">씬 검색어</label>
            <input id="q" type="search" autoComplete="off" spellCheck={false} placeholder="예: rainy night road" value={input} onChange={(e) => setInput(e.currentTarget.value)} maxLength={500} />
            <button className="btn btn--primary" type="submit" disabled={!input.trim() || datasetId == null || searchBlocked}>검색</button>
          </form>
          {datasetId != null && <SearchIndexStatus key={datasetId} datasetId={datasetId} />}
          {datasetId != null && searchCap.state !== 'READY' && searchCap.reasonCode !== 'STATUS_CHECKING' && searchCap.reasonCode !== 'EMBEDDINGS_NOT_READY' && (
            <div className="search-note" role="status" data-testid="search-readiness" data-reason={searchCap.reasonCode ?? ''}>
              <span className={`status status--${searchCap.state === 'UNAVAILABLE' ? 'FAILED' : 'UNKNOWN'}`}><i />검색 {stateLabel(searchCap.state)}</span>
              <span>{capabilityMessage(searchCap)}{searchBlocked ? ' 씬 목록 탐색은 그대로 쓸 수 있어요.' : ''}</span>
              <button type="button" className="btn btn--sm btn--ghost" onClick={() => void system.recheck(searchCap)} disabled={system.refreshing}>다시 확인</button>
            </div>
          )}
          <div className="examples">
            <span className="examples-label">예시</span>
            {EXAMPLES.map((ex) => <button key={ex} type="button" className="chip" onClick={() => { setInput(ex); submit(ex); }}>{ex}</button>)}
          </div>
        </section>

        <section className="results" aria-live="polite">
          {datasets.isError ? (
            <StateBox kind="error" title="데이터셋 목록을 불러오지 못했어요" actions={<button type="button" className="btn btn--weak" onClick={() => void datasets.refetch()}>다시 불러오기</button>}>
              {describeError(datasets.error)}
            </StateBox>
          ) : datasets.data && datasets.data.length === 0 ? (
            <StateBox title="등록된 데이터셋이 없어요" actions={<Link className="btn btn--primary" to="/labels">원본 데이터 업로드</Link>}>nuScenes ZIP을 업로드하면 씬 탐색·검색 준비·자동 라벨링을 시작할 수 있어요.</StateBox>
          ) : datasetParam != null && datasets.data && !dataset ? (
            <StateBox kind="error" title="링크의 데이터셋을 찾을 수 없어요" actions={<button type="button" className="btn btn--weak" onClick={() => navigate(searchUrl(null))}>데이터셋 다시 고르기</button>}>
              dataset {datasetParam}은(는) 이 서버에 없어요.
            </StateBox>
          ) : q && searchBlocked ? (
            <StateBox title="이 데이터셋에서는 지금 검색할 수 없어요" actions={<button type="button" className="btn btn--ghost btn--sm" onClick={() => submit('')}>전체 씬 보기</button>}>
              {capabilityMessage(searchCap)}
            </StateBox>
          ) : q ? (
            <SearchResults q={q} search={search} datasetId={datasetId} isPicked={isPicked} toggle={toggleCompare} clear={() => submit('')} retry={() => void search.refetch()} />
          ) : (
            <>
              <div className="results-head">
                <h2 className="results-title">{scenes.data ? `전체 씬 ${scenes.data.length}개` : '씬 목록'}</h2>
                {dataset && <span className="results-sub">{dataset.label}</span>}
              </div>
              {scenes.isError ? (
                <StateBox kind="error" title="씬 목록을 불러오지 못했어요" actions={<button type="button" className="btn btn--weak" onClick={() => void scenes.refetch()}>다시 불러오기</button>}>{describeError(scenes.error)}</StateBox>
              ) : !scenes.data ? <SkeletonGrid /> : scenes.data.length === 0 ? (
                <StateBox title="이 데이터셋에는 씬이 없어요" />
              ) : (
                <div className="scene-grid">
                  {scenes.data.map((s) => (
                    <SceneCard key={s.id} datasetId={s.datasetId} sceneId={s.id} name={s.name} description={s.description} nbrSamples={s.nbrSamples}
                      selectedForCompare={isPicked(s.datasetId, s.id)} onToggleCompare={() => toggleCompare({ datasetId: s.datasetId, sceneId: s.id, name: s.name, sample: null })} />
                  ))}
                </div>
              )}
            </>
          )}
        </section>

        {compare.length > 0 && (
          <div className="compare-bar" role="region" aria-label="비교할 씬">
            <b>비교</b>
            {compare.map((c, i) => <span key={`${c.datasetId}-${c.sceneId}`} className="tag"><span className={`pane-dot pane-dot--${i === 0 ? 'A' : 'B'}`}>{i === 0 ? 'A' : 'B'}</span>{c.name}</span>)}
            <span className="dim">{compare.length === 1 ? '하나만 고르면 같은 씬을 양쪽에 열어요' : ''}</span>
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => setCompare([])}>비우기</button>
              <button type="button" className="btn btn--primary btn--sm" onClick={openCompare}>두 씬 비교 열기</button>
            </div>
          </div>
        )}

        <p className="foot-note">검색 유사도는 텍스트와 카메라 이미지 임베딩의 점수라서 확률이나 정확도가 아니에요. 영문 검색어를 권장해요(한국어 검색 품질은 검증되지 않았어요). 결과가 비어 있으면 해당 데이터셋의 이미지 임베딩이 준비되지 않았을 수도 있어요.</p>
      </main>
    </div>
  );
}

function SkeletonGrid() {
  return (
    <div className="scene-grid" aria-hidden="true">
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="scene-card"><div className="thumb skel" /><div className="card-body"><div className="skel skel-line" /><div className="skel skel-line" /><div className="skel skel-line short" /></div></div>
      ))}
    </div>
  );
}

function SearchResults({ q, search, datasetId, isPicked, toggle, clear, retry }: {
  q: string;
  search: ReturnType<typeof useQuery<import('@/api/models').SearchResult>>;
  datasetId: number | null;
  isPicked: (d: number, s: number) => boolean;
  toggle: (c: CompareItem) => void;
  clear: () => void;
  retry: () => void;
}) {
  const allBtn = <button type="button" className="btn btn--ghost btn--sm" onClick={clear}>전체 씬 보기</button>;
  if (datasetId == null || search.isPending) return <><div className="results-head"><h2 className="results-title">“{q}” 검색 중</h2></div><SkeletonGrid /></>;
  if (search.isError) {
    return (
      <>
        <div className="results-head"><h2 className="results-title">검색하지 못했어요</h2><div className="results-actions">{allBtn}</div></div>
        <StateBox kind="error" title={describeError(search.error)} actions={<><button type="button" className="btn btn--weak" onClick={retry}>다시 검색</button>{allBtn}</>}>
          잠시 후 다시 검색하거나 전체 씬 목록에서 골라 주세요.
        </StateBox>
      </>
    );
  }
  const hits = search.data.hits;
  if (!hits.length) {
    return (
      <>
        <div className="results-head"><h2 className="results-title">“{q}” 검색 결과 없음</h2><div className="results-actions">{allBtn}</div></div>
        <StateBox kind="empty" title="일치하는 씬이 없어요" actions={allBtn}>
          날씨, 시간대, 장소, 객체처럼 장면을 묘사하는 단어로 다시 검색해 보세요. 이 데이터셋에 이미지 임베딩이 아직 없을 때도 결과가 비어요.
        </StateBox>
      </>
    );
  }
  return (
    <>
      <div className="results-head">
        <h2 className="results-title">“{search.data.query}” 검색 결과 {hits.length}개</h2>
        <span className="results-sub">씬별 상위 이미지 평균 점수 순</span>
        <div className="results-actions">{allBtn}</div>
      </div>
      <div className="scene-grid">
        {hits.map((h) => (
          <SceneCard key={`${h.datasetId}-${h.sceneId}`} datasetId={h.datasetId} sceneId={h.sceneId} name={h.sceneName} description={h.description}
            hit={{ score: h.score, contentUrl: h.contentUrl, bestSampleToken: h.bestSampleToken, matchedImages: h.matchedImages }}
            selectedForCompare={isPicked(h.datasetId, h.sceneId)}
            onToggleCompare={() => toggle({ datasetId: h.datasetId, sceneId: h.sceneId, name: h.sceneName, sample: h.bestSampleToken })} />
        ))}
      </div>
    </>
  );
}
