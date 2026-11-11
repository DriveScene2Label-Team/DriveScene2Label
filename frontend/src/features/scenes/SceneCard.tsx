import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';
import { getJson, qs } from '@/api/http';
import type { SampleDetailDto, SampleDto } from '@/api/dto';
import { workspaceUrl } from '@/app/urls';

export interface CardData {
  datasetId: number;
  sceneId: number;
  name: string;
  description: string;
  nbrSamples: number | null;
  /** Search hit: representative image, frame, raw cosine score and calibrated matchScore (neither is a probability). */
  hit?: { score: number; matchScore: number | null; contentUrl: string; bestSampleToken: string };
}

export type MatchLevel = 'good' | 'fair' | 'weak';

/**
 * Display band of a calibrated matchScore (docs/search-match-score.md): 80+ 잘 맞음, 50–79 관련 있음, below 50 약함.
 * A reading aid for the same number, not a probability; wrong scenes can also reach 80 (about 31% on mini).
 */
export function matchLevel(matchScore: number): { level: MatchLevel; label: string } {
  if (matchScore >= 80) return { level: 'good', label: '잘 맞음' };
  if (matchScore >= 50) return { level: 'fair', label: '관련 있음' };
  return { level: 'weak', label: '약함' };
}

/** Tooltip text: raw cosine value and what the number is not. Exported for tests. */
export function matchTooltip(score: number, matchScore: number | null): string {
  const raw = `원래 코사인 유사도 ${score.toFixed(3)}`;
  if (matchScore == null) return `${raw}. 텍스트와 이미지 임베딩의 유사도이며 확률이 아니에요.`;
  return `${raw}. 일치도는 이 값을 0~100점으로 보정한 것으로 확률이 아니에요. `
    + '0점은 관련 없는 문장 수준, 100점은 짧은 검색어가 맞는 scene에서 받는 대표 점수예요. '
    + '80점 이상 잘 맞음, 50~79점 관련 있음, 50점 미만 약함.';
}

/** Spoken form of the hit score for the card's aria-label. */
function matchSpeech(hit: { score: number; matchScore: number | null }): string {
  return hit.matchScore == null ? `유사도 ${hit.score.toFixed(2)}` : `일치도 ${hit.matchScore}점, ${matchLevel(hit.matchScore).label}`;
}

function MatchBadge({ score, matchScore }: { score: number; matchScore: number | null }) {
  const tip = matchTooltip(score, matchScore);
  if (matchScore == null) return <span className="card-score" title={tip}>유사도 <b>{score.toFixed(2)}</b></span>;
  const { level, label } = matchLevel(matchScore);
  return (
    <span className="card-score" data-level={level} title={tip}>
      일치도<b>{matchScore}점</b><span className="sim-level">{label}</span>
    </span>
  );
}

/** First frame's CAM_FRONT for list cards, fetched only once the card is near the viewport. */
function useFirstFrameImage(sceneId: number, visible: boolean) {
  return useQuery({
    queryKey: ['sceneThumb', sceneId],
    enabled: visible,
    staleTime: Infinity,
    queryFn: async ({ signal }) => {
      const first = await getJson<SampleDto[]>(`/api/scenes/${sceneId}/samples${qs({ limit: 1, offset: 0 })}`, signal);
      if (!first[0]) return null;
      const detail = await getJson<SampleDetailDto>(`/api/samples/${first[0].id}${qs({ keyframesOnly: true })}`, signal);
      const cam = detail.sensorFiles.find((f) => f.channel === 'CAM_FRONT') ?? detail.sensorFiles.find((f) => f.modality === 'camera');
      return cam?.contentUrl ?? null;
    },
  });
}

/** Weather/time words of the original description (same keyword rule as the DB's is_night / is_rain columns). */
export function conditionOf(description: string): string | null {
  const night = /\bnight\b/i.test(description);
  const rain = /\brain(y|ing)?\b/i.test(description);
  return night && rain ? '밤, 비' : night ? '밤' : rain ? '비' : null;
}

interface Props {
  data: CardData;
  picking: boolean;
  picked: boolean;
  onPick: () => void;
}

export function SceneCard({ data, picking, picked, onPick }: Props) {
  const { datasetId, sceneId, name, description, nbrSamples, hit } = data;
  const ref = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || hit) return;
    if (typeof IntersectionObserver === 'undefined') return setVisible(true);
    const io = new IntersectionObserver((entries) => { if (entries.some((e) => e.isIntersecting)) { setVisible(true); io.disconnect(); } }, { rootMargin: '200px' });
    io.observe(el);
    return () => io.disconnect();
  }, [hit]);
  const thumb = useFirstFrameImage(sceneId, visible && !hit);
  const imgUrl = hit ? hit.contentUrl : thumb.data;
  const href = workspaceUrl({ datasetId, sceneId, sample: hit?.bestSampleToken ?? null, view: 'split' });
  const cond = conditionOf(description);
  const meta = [nbrSamples != null ? `${nbrSamples}프레임` : null, cond, hit ? '대표 프레임으로 열기' : null].filter(Boolean).join(' · ');
  const label = `${name}${hit ? `, ${matchSpeech(hit)}` : ''}. ${description}`;

  const inner = (
    <>
      <span className="card-thumb">
        {imgUrl ? <img src={imgUrl} alt="" loading="lazy" draggable={false} /> : (
          <span className={!hit && (thumb.isPending || !visible) ? 'thumb-empty is-loading' : 'thumb-empty'}>
            {thumb.isError ? '대표 이미지를 불러오지 못했어요' : thumb.data === null ? '카메라 이미지 없음' : ''}
          </span>
        )}
        <span className="card-check" aria-hidden="true" />
      </span>
      <span className="card-body">
        <span className="card-title">
          <span className="card-name">{name}</span>
          {hit && <MatchBadge score={hit.score} matchScore={hit.matchScore} />}
        </span>
        <span className="card-desc">{description || '설명 없음'}</span>
        {meta && <span className="card-meta">{meta}</span>}
      </span>
    </>
  );
  return (
    <article className={picked ? 'card is-picked' : 'card'} ref={ref} data-scene-id={sceneId}>
      {picking ? (
        <button type="button" className="card-hit" aria-pressed={picked} aria-label={label} onClick={onPick}>{inner}</button>
      ) : (
        <Link className="card-hit" to={href} aria-label={`${name} 열기. ${hit ? `${matchSpeech(hit)}. ` : ''}${description}`}>{inner}</Link>
      )}
    </article>
  );
}
