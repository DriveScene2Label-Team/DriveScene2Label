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
  /** Search hit: representative image, frame and score (not a probability). */
  hit?: { score: number; contentUrl: string; bestSampleToken: string };
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
  const label = `${name}${hit ? `, 유사도 ${hit.score.toFixed(2)}` : ''}. ${description}`;

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
          {hit && <span className="card-score" title="텍스트와 카메라 이미지 임베딩의 유사도 점수예요. 확률이나 정확도가 아니에요.">유사도 <b>{hit.score.toFixed(2)}</b></span>}
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
        <Link className="card-hit" to={href} aria-label={`${name} 열기. ${description}`}>{inner}</Link>
      )}
    </article>
  );
}
