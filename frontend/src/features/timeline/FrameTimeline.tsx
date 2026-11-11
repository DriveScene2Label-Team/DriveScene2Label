import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import type { SampleRef } from '@/api/models';
import { jobResultsQuery, sceneInstancesQuery } from '@/api/queries';
import { Icon } from '@/components/Icon';
import { instanceOfKey } from '@/features/objects/objectKeys';
import { SPEEDS, type Speed } from '@/lib/time/timeline';
import { useWorkspace, type PaneId } from '@/stores/workspace';

interface Props {
  paneId: PaneId;
  samples: SampleRef[];
  requestedIndex: number;
  displayedIndex: number;
  buffering: boolean;
  /** Accessible-name prefix in compare mode, e.g. "씬 A ". */
  prefix?: string;
}

const PRED_COLOR = '#3d8bff';
const GT_COLOR = '#ffc800';

/**
 * Keyframe timeline (JPG keyframes at their real timestamps, not a video). The slider shows the requested frame; the
 * readout shows the frame on screen. The strip above marks frames with predictions of the shown job (blue) and the
 * frames where the selected GT object appears (yellow).
 */
export function FrameTimeline({ paneId, samples, requestedIndex, displayedIndex, buffering, prefix = '' }: Props) {
  const pane = useWorkspace((s) => s.panes[paneId]);
  const requestSample = useWorkspace((s) => s.requestSample);
  const setPlaying = useWorkspace((s) => s.setPlaying);
  const setSpeed = useWorkspace((s) => s.setSpeed);
  const n = samples.length;
  const ready = n > 0;
  const idx = Math.max(0, requestedIndex);
  const shown = displayedIndex >= 0 ? displayedIndex : idx;
  const go = (i: number) => {
    const s = samples[Math.min(n - 1, Math.max(0, i))];
    if (s) requestSample(paneId, s.token, 'user');
  };
  const togglePlay = () => {
    if (pane.playing) return setPlaying(paneId, false);
    if (idx >= n - 1) go(0);
    setPlaying(paneId, true);
  };
  const pct = n > 1 ? (idx / (n - 1)) * 100 : 0;
  const t0 = samples[0]?.timestampUs;
  const cur = samples[shown];

  return (
    <div className="tl" data-pane={paneId}>
      <div className="tl-btns">
        <button type="button" className="tl-btn" onClick={() => { setPlaying(paneId, false); go(idx - 1); }} disabled={!ready || idx <= 0} aria-label={`${prefix}이전 프레임`} title="이전 프레임 (←)">
          <Icon name="prev" />
        </button>
        <button type="button" className="tl-btn tl-play" onClick={togglePlay} disabled={n < 2} aria-label={`${prefix}${pane.playing ? '일시정지' : '재생'}`} aria-pressed={pane.playing} title="재생 / 일시정지 (Space)">
          <Icon name={pane.playing ? 'pause' : 'play'} />
        </button>
        <button type="button" className="tl-btn" onClick={() => { setPlaying(paneId, false); go(idx + 1); }} disabled={!ready || idx >= n - 1} aria-label={`${prefix}다음 프레임`} title="다음 프레임 (→)">
          <Icon name="next" />
        </button>
      </div>
      <div className="tl-track">
        <TimelineStrip paneId={paneId} samples={samples} />
        <input type="range" className="tl-range" min={0} max={Math.max(0, n - 1)} step={1} value={idx} disabled={!ready}
          style={{ ['--pct' as string]: `${pct}%` }}
          onChange={(e) => { setPlaying(paneId, false); go(Number(e.currentTarget.value)); }}
          aria-label={`${prefix}프레임`} aria-valuetext={n ? `${n}프레임 중 ${idx + 1}번째` : '프레임 없음'} />
      </div>
      <div className="tl-read">
        <span className="tl-frame" data-testid={`frame-readout-${paneId}`}><b className="tl-cur">{n ? shown + 1 : 0}</b><span className="tl-tot"> / {n}</span></span>
        <span className="tl-ts" title="장면 시작부터의 sample timestamp 차이">
          {buffering ? <span className="tl-buf"><span className="spinner" aria-hidden="true" />불러오는 중</span> : cur && t0 != null ? `${((cur.timestampUs - t0) / 1e6).toFixed(1)}초` : ''}
        </span>
      </div>
      <label className="tl-speed">
        <span className="sr-only">{prefix}재생 속도</span>
        <select className="popup popup--media popup--sm" value={pane.speed} onChange={(e) => setSpeed(paneId, Number(e.currentTarget.value) as Speed)} title="실제 키프레임 timestamp 간격 기준">
          {SPEEDS.map((s) => <option key={s} value={s}>{s}×</option>)}
        </select>
      </label>
    </div>
  );
}

function TimelineStrip({ paneId, samples }: { paneId: PaneId; samples: SampleRef[] }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const pane = useWorkspace((s) => s.panes[paneId]);
  const results = useQuery({ ...jobResultsQuery(pane.resultJobId ?? -1), enabled: pane.resultJobId != null });
  const inst = instanceOfKey(pane.selectedBoxKey);
  const instances = useQuery({ ...sceneInstancesQuery(pane.sceneId ?? -1), enabled: pane.sceneId != null && inst != null });
  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const draw = () => {
      const d = window.devicePixelRatio || 1;
      const w = Math.max(1, Math.round(cv.clientWidth * d));
      const h = Math.round(5 * d);
      if (cv.width !== w) cv.width = w;
      if (cv.height !== h) cv.height = h;
      const ctx = cv.getContext?.('2d');
      if (!ctx) return;
      ctx.clearRect(0, 0, w, h);
      const N = samples.length;
      if (!N) return;
      const cw = w / N;
      const r = results.data;
      if (pane.layers.pred && r) {
        ctx.fillStyle = PRED_COLOR;
        samples.forEach((s, k) => {
          if (r.datasetId === s.datasetId && (r.boxesBySample.get(s.token)?.length ?? 0) > 0) ctx.fillRect(k * cw + 0.5, h * 0.6, Math.max(1, cw - 1), h * 0.4);
        });
      }
      const frames = inst ? instances.data?.get(inst) : undefined;
      if (frames) {
        ctx.fillStyle = GT_COLOR;
        samples.forEach((s, k) => { if (frames.has(s.token)) ctx.fillRect(k * cw + 0.5, 0, Math.max(1, cw - 1), h * 0.45); });
      }
    };
    draw();
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(draw);
    ro.observe(cv);
    return () => ro.disconnect();
  }, [samples, results.data, pane.layers.pred, inst, instances.data]);
  return <canvas ref={ref} className="tl-strip" aria-hidden="true" />;
}
