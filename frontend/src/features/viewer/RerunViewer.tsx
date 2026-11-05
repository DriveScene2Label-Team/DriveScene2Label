import { useEffect, useRef, useState } from 'react';
import type { Recording } from '@/api/models';
import { useWorkspace, type PaneId } from '@/stores/workspace';
import { useQueryClient } from '@tanstack/react-query';
import type { BoxView } from '@/api/models';
import { boxKeyForSelection, indexForSample, normalizeEntity, objectKeyForBoxKey } from './recordingMap';

type WebViewerType = import('@rerun-io/web-viewer').WebViewer;

interface Props {
  paneId: PaneId;
  recording: Recording;
  /** Displayed sample of the pane (React is the timeline's source of truth). */
  displayedSampleToken: string | null;
  /** The server confirmed the READY file is gone (RECORDING_FILE_MISSING): the panel re-reads the recording state. */
  onFileMissing?: () => void;
}

type Phase = 'loading' | 'ready' | 'download-error' | 'viewer-error';
/** After this long without recording_open the user is offered to re-open (the viewer may be stuck). */
const STALL_MS = 45_000;

class DownloadError extends Error {
  constructor(message: string, readonly status: number | null, readonly code: string | null) { super(message); }
}

/**
 * Rerun Web Viewer 0.38.1 bound to one pane.
 * - React → Viewer: when the displayed frame changes, set the "sample" timeline to that index.
 * - Viewer → React: a time change on the "sample" timeline requests the matching sample (origin 'viewer').
 *   Echoes of our own set_current_time are ignored, so the two never ping-pong.
 * - Box selection maps (entity path, instance id, current sample) → REST box id via the recording metadata.
 * The viewer, its WASM memory and listeners are released on unmount or recording change.
 */
export function RerunViewer({ paneId, recording, displayedSampleToken, onFileMissing }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<WebViewerType | null>(null);
  const rrIdRef = useRef<string | null>(null);
  const lastSentRef = useRef<number | null>(null);
  const currentIdxRef = useRef<number>(-1);
  const activeTimelineRef = useRef<string>(recording.timeline);
  const [phase, setPhase] = useState<Phase>('loading');
  const [error, setError] = useState<string | null>(null);
  // Re-opening the same READY recording: a new attempt tears down the previous viewer/channel/listeners/fetch and
  // mounts a fresh host element. It never creates a recording or a job.
  const [attempt, setAttempt] = useState(0);
  const [stalled, setStalled] = useState(false);
  const fileMissingRef = useRef(onFileMissing);
  fileMissingRef.current = onFileMissing;
  const requestSample = useWorkspace((s) => s.requestSample);
  const selectBox = useWorkspace((s) => s.selectBox);
  const qc = useQueryClient();
  const contentUrl = recording.contentUrl;

  const recRef = useRef(recording);
  recRef.current = recording;

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !contentUrl) return;
    let disposed = false;
    const offs: Array<() => void> = [];
    setPhase('loading');
    setError(null);
    setStalled(false);
    const stallTimer = window.setTimeout(() => setStalled(true), STALL_MS);
    const controller = new AbortController();
    let channel: { close: () => void } | null = null;
    (async () => {
      try {
        // Rerun 0.38.1 only treats HTTP URLs ending in `.rrd` as recordings, so the Spring content endpoint is fetched
        // here (cancellable, HTTP errors visible) and the bytes are pushed through a log channel.
        const [{ WebViewer }, bytes] = await Promise.all([
          import('@rerun-io/web-viewer'),
          fetch(contentUrl, { signal: controller.signal }).then(async (res) => {
            if (!res.ok) {
              let code: string | null = null;
              try { code = ((await res.json()) as { code?: string }).code ?? null; } catch { /* non-JSON error body */ }
              throw new DownloadError(`recording 파일을 받지 못했어요 (HTTP ${res.status}${code ? ` ${code}` : ''})`, res.status, code);
            }
            return new Uint8Array(await res.arrayBuffer());
          }, (e: unknown) => {
            if (controller.signal.aborted) throw e;
            throw new DownloadError('recording 파일을 받는 중 연결이 끊겼어요', null, null);
          }),
        ]);
        if (disposed) return;
        const viewer = new WebViewer();
        viewerRef.current = viewer;
        await viewer.start(null, host, { hide_welcome_screen: true, width: '100%', height: '100%', theme: 'dark' });
        if (disposed) {
          viewer.stop();
          return;
        }
        // The React timeline/inspector own frame and object state; keep the viewer to its 3D view.
        viewer.override_panel_state('top', 'hidden');
        viewer.override_panel_state('blueprint', 'collapsed');
        viewer.override_panel_state('selection', 'collapsed');
        viewer.override_panel_state('time', 'collapsed');
        offs.push(viewer.on('recording_open', (e) => {
          rrIdRef.current = e.recording_id;
          viewer.set_active_timeline(e.recording_id, recRef.current.timeline);
          viewer.set_playing(e.recording_id, false);
          const idx = currentIdxRef.current;
          if (idx >= 0) {
            lastSentRef.current = idx;
            viewer.set_current_time(e.recording_id, recRef.current.timeline, idx);
          }
          window.clearTimeout(stallTimer);
          setStalled(false);
          setPhase('ready');
        }));
        offs.push(viewer.on('timeline_change', (e) => { activeTimelineRef.current = e.timeline; }));
        offs.push(viewer.on('time_update', (e) => {
          // Last time reported by the viewer itself; lets tests and diagnostics confirm React → viewer sync.
          host.dataset.viewerTime = String(e.time);
          if (activeTimelineRef.current !== recRef.current.timeline) return;
          const idx = Math.round(e.time);
          if (idx === lastSentRef.current || idx === currentIdxRef.current) return;
          const s = recRef.current.samples.find((x) => x.index === idx);
          if (s) {
            lastSentRef.current = idx;
            requestSample(paneId, s.sampleToken, 'viewer');
          }
        }));
        offs.push(viewer.on('selection_change', (e) => {
          const rec = recRef.current;
          const item = e.items.find((i) => i.type === 'entity' && i.instance_id != null);
          if (!item || item.type !== 'entity') return;
          const key = boxKeyForSelection(rec, normalizeEntity(item.entity_path), item.instance_id ?? -1, currentIdxRef.current);
          const objKey = key ? objectKeyForBoxKey(key, (k) => {
            for (const [, data] of qc.getQueriesData<BoxView[]>({ queryKey: ['annotations'] })) {
              const box = data?.find((b) => b.key === k);
              if (box) return box;
            }
            return undefined;
          }) : null;
          if (objKey) selectBox(paneId, objKey);
        }));
        const ch = viewer.open_channel(`ds2l-recording-${recRef.current.recordingId}`);
        channel = ch;
        ch.send_rrd(bytes);
      } catch (e) {
        if (!disposed && !controller.signal.aborted) {
          window.clearTimeout(stallTimer);
          if (e instanceof DownloadError) {
            setPhase('download-error');
            if (e.code === 'RECORDING_FILE_MISSING') fileMissingRef.current?.();
          } else setPhase('viewer-error');
          setError(e instanceof Error ? e.message : String(e));
        }
      }
    })();
    return () => {
      disposed = true;
      window.clearTimeout(stallTimer);
      controller.abort();
      offs.forEach((off) => off());
      try { channel?.close(); } catch { /* viewer already stopped */ }
      viewerRef.current?.stop();
      viewerRef.current = null;
      rrIdRef.current = null;
      lastSentRef.current = null;
    };
  }, [contentUrl, paneId, requestSample, selectBox, attempt, qc]);

  // React timeline → viewer.
  useEffect(() => {
    const idx = indexForSample(recording, displayedSampleToken);
    currentIdxRef.current = idx;
    const viewer = viewerRef.current;
    const rr = rrIdRef.current;
    if (!viewer || !rr || idx < 0 || phase !== 'ready') return;
    lastSentRef.current = idx;
    viewer.set_current_time(rr, recording.timeline, idx);
  }, [displayedSampleToken, recording, phase]);

  const reopen = <button type="button" className="btn sm weak" onClick={() => setAttempt((a) => a + 1)} data-testid="reopen-recording">같은 recording 다시 열기</button>;
  return (
    <>
      {/* Rerun sets `position: relative` on the element it is given, so it gets a full-size child of an absolute frame.
          The key gives each attempt a fresh element. */}
      <div className="v3d-frame"><div key={attempt} ref={hostRef} className="v3d-host" data-testid="rerun-host" data-phase={phase} data-attempt={attempt} /></div>
      {phase === 'loading' && (
        <div className="v3d-state" role="status">
          <span className="spinner" aria-hidden="true" /><b>3D 뷰어를 불러오고 있어요</b>
          <span>recording {(recording.sizeBytes ?? 0) > 0 ? `${((recording.sizeBytes ?? 0) / 1e6).toFixed(1)} MB` : ''}</span>
          {stalled && <><span>예상보다 오래 걸려요.</span>{reopen}</>}
        </div>
      )}
      {phase === 'download-error' && (
        <div className="v3d-state" role="alert" data-testid="viewer-download-error">
          <b>3D 파일을 받지 못했어요</b><span className="mono">{error}</span>
          <span>recording은 만들어져 있어요. 파일만 다시 받아요(새로 만들거나 라벨 작업을 다시 실행하지 않아요).</span>
          {reopen}
        </div>
      )}
      {phase === 'viewer-error' && (
        <div className="v3d-state" role="alert" data-testid="viewer-start-error">
          <b>3D 뷰어를 시작하지 못했어요</b><span className="mono">{error}</span>
          <span>브라우저의 WebGL/WebGPU 또는 뷰어 로딩 문제일 수 있어요. 카메라와 작업 조회는 그대로 쓸 수 있어요.</span>
          {reopen}
        </div>
      )}
    </>
  );
}
