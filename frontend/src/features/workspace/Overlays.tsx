import { useQuery, useQueryClient } from '@tanstack/react-query';
import { sceneInstancesQuery } from '@/api/queries';
import { useState } from 'react';
import type { EditScope } from '@/api/dto';
import { describeError } from '@/api/http';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Icon } from '@/components/Icon';
import { CameraGlyph } from '@/features/cameras/CameraGlyph';
import { CameraMedia } from '@/features/cameras/CameraTile';
import { cameraKo } from '@/features/cameras/cameraMeta';
import type { PaneFrames } from '@/features/frames/usePaneFrames';
import { MOD } from '@/features/inspector/EditsPanel';
import { revertWithToast, runEdit } from '@/features/inspector/ObjectsPanel';
import { objectKey } from '@/features/objects/objectKeys';
import type { PredState } from '@/features/objects/useFrameBoxes';
import { FrameTimeline } from '@/features/timeline/FrameTimeline';
import { useElementSize } from '@/hooks/useElementSize';
import { afterEdit, deleteBox, josa } from '@/lib/edits/labelEdits';
import { useOverlay, type Overlay } from '@/stores/overlay';
import { snack, toast } from '@/stores/toast';
import { useWorkspace, type PaneId } from '@/stores/workspace';
import { selectObject, usePaneBoxes } from './actions';
import { LayerToggle } from './Hud';

/** Camera quick look of one pane: large image with the same boxes, camera switcher, layer toggles and timeline. */
export function ZoomDialog({ paneId, sceneName, frames, pred }: { paneId: PaneId; sceneName: string; frames: PaneFrames; pred: PredState }) {
  const overlay = useOverlay((s) => s.overlay);
  const close = useOverlay((s) => s.close);
  const pane = useWorkspace((s) => s.panes[paneId]);
  const setFocus = useWorkspace((s) => s.setFocusCamera);
  const boxes = usePaneBoxes(paneId, frames, pred);
  const [stageRef, stage] = useElementSize<HTMLDivElement>();
  const open = overlay?.kind === 'zoom' && overlay.paneId === paneId;
  if (!open) return null;
  const channel = overlay.channel;
  const slot = frames.displayed.cameras.find((c) => c.channel === channel);
  const W = Math.max(0, stage.width - 24);
  const H = Math.max(0, stage.height - 24);
  let w = W; let h = (W * 9) / 16;
  if (h > H) { h = H; w = (H * 16) / 9; }
  const all = [...(frames.displayed.gt ?? []), ...(pred.kind === 'ready' ? pred.boxes : [])];
  return (
    <Dialog open onOpenChange={(o) => { if (!o) close(); }}>
      <DialogContent className="ql" aria-describedby="zoom-desc">
        <div className="ql-head">
          <DialogTitle className="ql-title"><CameraGlyph channel={channel} /><span>{cameraKo(channel)}</span><span className="sub mono">{channel}</span><span className="sub">{sceneName}</span></DialogTitle>
          <DialogDescription id="zoom-desc" className="sr-only">선택한 카메라 이미지를 크게 보고 GT와 예측 박스를 확인해요. 왼쪽·오른쪽 화살표로 프레임을 옮길 수 있어요.</DialogDescription>
          <div className="seg seg--media seg--sm" role="group" aria-label="카메라 바꾸기">
            {frames.displayed.cameras.map((c) => (
              <button key={c.channel} type="button" aria-pressed={c.channel === channel} title={c.channel}
                onClick={() => { setFocus(paneId, c.channel); useOverlay.getState().open({ kind: 'zoom', paneId, channel: c.channel }); }}>{cameraKo(c.channel)}</button>
            ))}
          </div>
          <span className="ql-gap" />
          <div className="hud-group"><LayerToggle paneId={paneId} layer="gt" /><LayerToggle paneId={paneId} layer="pred" /></div>
          <button type="button" className="ql-close" onClick={close} aria-label="닫기 (Esc)" title="닫기 (Esc)"><Icon name="close" /></button>
        </div>
        <div className="ql-stage" ref={stageRef}>
          {w > 0 && (
            <div className="ql-frame" style={{ width: Math.floor(w), height: Math.floor(h), left: Math.floor((stage.width - w) / 2), top: Math.floor((stage.height - h) / 2) }}>
              {slot && <CameraMedia slot={slot} boxes={boxes} selectedKey={pane.selectedBoxKey} names={pane.layers.names} frameNumber={frames.displayedIndex + 1}
                onSelect={(k) => selectObject(paneId, k, all.find((b) => objectKey(b) === k) ?? null)} />}
            </div>
          )}
        </div>
        <FrameTimeline paneId={paneId} samples={frames.samples} requestedIndex={frames.requestedIndex} displayedIndex={frames.displayedIndex} buffering={frames.buffering} />
      </DialogContent>
    </Dialog>
  );
}

/** Delete confirmation. GT: every frame of the object (default) or only this frame. Predictions: this box. */
export function DeleteDialog() {
  const overlay = useOverlay((s) => s.overlay);
  return overlay?.kind === 'confirm' ? <DeleteBody key={overlay.box.key} overlay={overlay} /> : null;
}

function DeleteBody({ overlay }: { overlay: Extract<Overlay, { kind: 'confirm' }> }) {
  const close = useOverlay((s) => s.close);
  const qc = useQueryClient();
  const [scope, setScope] = useState<EditScope>('INSTANCE');
  const { box, paneId, instanceFrames, frameIndex } = overlay;
  const gt = box.source === 'GT';
  const canInstance = gt && !!box.instanceToken;
  const sceneId = useWorkspace((s) => s.panes[paneId].sceneId);
  const inst = useQuery({ ...sceneInstancesQuery(sceneId ?? -1), enabled: canInstance && sceneId != null });
  const nFrames = (box.instanceToken ? inst.data?.get(box.instanceToken)?.size : undefined) || instanceFrames || '…';
  const effective: EditScope = canInstance ? scope : 'SAMPLE';
  const what = `${gt ? 'GT' : '예측 박스'} ${box.cls}`;
  const run = async () => {
    close();
    await runEdit(async () => {
      try {
        const e = await deleteBox(box, effective);
        const st = useWorkspace.getState();
        if (st.panes[paneId].selectedBoxKey === objectKey(box)) st.selectBox(paneId, null);
        await afterEdit(qc, e);
        snack(`${josa(what, '을/를')} 삭제했어요${e.count > 1 ? ` (${e.count}개 프레임)` : ''}`, '되돌리기', () => void revertWithToast(qc, e.id));
      } catch (err) {
        toast(`삭제하지 못했어요: ${describeError(err)}`, 'error');
      }
    });
  };
  return (
    <Dialog open onOpenChange={(o) => { if (!o) close(); }}>
      <DialogContent className="alert" role="alertdialog" aria-describedby="dlg-d" onOpenAutoFocus={(e) => { e.preventDefault(); document.getElementById('dlg-cancel')?.focus(); }}>
        <DialogTitle className="alert-title">{josa(what, '을/를')} 삭제할까요?</DialogTitle>
        <DialogDescription className="alert-msg" id="dlg-d">화면과 목록에서 빠져요. 기록 탭에서 되돌릴 수 있어요. 원본 데이터는 바뀌지 않아요.</DialogDescription>
        {canInstance && (
          <fieldset className="alert-opts">
            <legend className="sr-only">삭제 범위</legend>
            <label className="opt"><input type="radio" name="dlg-scope" value="INSTANCE" checked={scope === 'INSTANCE'} onChange={() => setScope('INSTANCE')} /><span className="opt-t">이 객체의 모든 프레임<span className="opt-s">{nFrames}개 프레임에서 지워요</span></span></label>
            <label className="opt"><input type="radio" name="dlg-scope" value="SAMPLE" checked={scope === 'SAMPLE'} onChange={() => setScope('SAMPLE')} /><span className="opt-t">지금 프레임만<span className="opt-s">{frameIndex + 1}번째 프레임에서만 지워요</span></span></label>
          </fieldset>
        )}
        <div className="alert-btns">
          <button type="button" className="btn" id="dlg-cancel" onClick={close}>취소</button>
          <button type="button" className="btn danger" onClick={() => void run()} data-testid="confirm-delete">삭제하기</button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function KeysSheet() {
  const overlay = useOverlay((s) => s.overlay);
  const close = useOverlay((s) => s.close);
  if (overlay?.kind !== 'keys') return null;
  const k = (...ks: string[]) => ks.map((x) => <kbd key={x}>{x}</kbd>);
  const rows: Array<[React.ReactNode, string]> = [
    [k('Space'), '재생 / 일시정지'], [k('←', '→'), '이전 / 다음 프레임'], [k('G'), 'GT 박스 보이기 / 숨기기'], [k('P'), '예측 박스 보이기 / 숨기기'],
    [k('H'), '선택한 객체 숨기기 / 다시 보이기'], [k('Delete'), '선택한 객체 삭제'], [k(MOD, 'Z'), '마지막 수정 되돌리기'], [k('Esc'), '선택 해제, 창 닫기'],
    [k('\\'), '인스펙터 보이기 / 숨기기'], [k('?'), '단축키 보기'],
  ];
  return (
    <Dialog open onOpenChange={(o) => { if (!o) close(); }}>
      <DialogContent className="sheet" aria-describedby={undefined}>
        <DialogTitle>단축키</DialogTitle>
        <table className="ktable"><tbody>{rows.map(([a, b]) => <tr key={b}><td>{a}</td><td>{b}</td></tr>)}</tbody></table>
        <div className="sheet-btns"><button type="button" className="btn" onClick={close}>닫기</button></div>
      </DialogContent>
    </Dialog>
  );
}

/** ⌘Z / Ctrl+Z: revert the newest revertible edit of the scene (history order from the server). */
export function useUndoLast() {
  const qc = useQueryClient();
  return (sceneId: number | null, jobId: number | null) => {
    if (sceneId == null) return;
    const list = qc.getQueryData<Array<{ id: number; revertible: boolean }>>(['labelEdits', sceneId, jobId]);
    const e = list?.find((x) => x.revertible);
    if (!e) { toast('되돌릴 수정이 없어요'); return; }
    void revertWithToast(qc, e.id);
  };
}
