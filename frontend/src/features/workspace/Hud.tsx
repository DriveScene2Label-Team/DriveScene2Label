import { Icon } from '@/components/Icon';
import { announce } from '@/stores/toast';
import { useWorkspace, type LayerKey, type PaneId } from '@/stores/workspace';

const META: Record<LayerKey, { label: string; key: string; ko: string }> = {
  gt: { label: 'GT', key: 'G', ko: 'GT 박스' },
  pred: { label: '예측', key: 'P', ko: '예측 박스' },
  names: { label: '클래스 이름', key: '', ko: '클래스 이름' },
};

export function toggleLayerAnnounced(paneId: PaneId, layer: LayerKey): void {
  const st = useWorkspace.getState();
  st.toggleLayer(paneId, layer);
  announce(`${META[layer].ko} ${useWorkspace.getState().panes[paneId].layers[layer] ? '보이기' : '숨기기'}`);
}

export function LayerToggle({ paneId, layer }: { paneId: PaneId; layer: LayerKey }) {
  const on = useWorkspace((s) => s.panes[paneId].layers[layer]);
  const m = META[layer];
  return (
    <button type="button" className="hud-tog" aria-pressed={on} data-layer={layer} onClick={() => toggleLayerAnnounced(paneId, layer)}
      title={`${m.label} ${on ? '숨기기' : '보이기'}${m.key ? ` (${m.key})` : ''}${layer !== 'names' ? ' · 카메라 박스와 객체 목록에 적용' : ''}`}>
      {layer === 'names' ? <Icon name="text" /> : <><Icon name="eye" className="i-on" /><Icon name="eye-off" className="i-off" /></>}
      {layer !== 'names' && <span className={`sw sw-${layer}`} aria-hidden="true" />}
      <span>{m.label}</span>
      {m.key && <kbd aria-hidden="true">{m.key}</kbd>}
    </button>
  );
}

interface Props {
  paneId: PaneId;
  /** Compare mode: the toggles apply to the work-target pane, shown by its tag. */
  compareTag?: 'A' | 'B';
  sync?: { on: boolean; set: (on: boolean) => void };
  onResetSplit?: () => void;
  onExitCompare?: () => void;
}

/** Display bar on top of the sensor card. */
export function Hud({ paneId, compareTag, sync, onResetSplit, onExitCompare }: Props) {
  const hidden = useWorkspace((s) => s.panes[paneId].hidden.length);
  const showAll = useWorkspace((s) => s.showAllHidden);
  return (
    <div className="hud" role="toolbar" aria-label={compareTag ? `씬 ${compareTag} 표시` : '표시'}>
      {compareTag && <span className="hud-pane" title={`표시 설정은 작업 대상인 씬 ${compareTag}에 적용돼요`} aria-hidden="true">{compareTag}</span>}
      <div className="hud-group">
        <LayerToggle paneId={paneId} layer="gt" />
        <LayerToggle paneId={paneId} layer="pred" />
        <LayerToggle paneId={paneId} layer="names" />
      </div>
      {hidden > 0 && (
        <span className="hud-note">숨긴 객체 {hidden}개<button type="button" className="hud-link" onClick={() => { showAll(paneId); announce('숨긴 객체를 모두 다시 보이게 했어요'); }}>모두 보이기</button></span>
      )}
      <span className="hud-gap" />
      {sync && (
        <label className="hud-switch" title="각 씬의 시간 범위에서 같은 비율 위치로 맞춰요. 같은 촬영 시각이라는 뜻은 아니에요.">
          <input type="checkbox" role="switch" className="switch switch--media" checked={sync.on} onChange={(e) => sync.set(e.currentTarget.checked)} />재생 위치 맞추기
        </label>
      )}
      {onResetSplit && <button type="button" className="hud-btn icon" data-action="reset-split" onClick={onResetSplit} aria-label="화면 비율 초기화" title="화면 비율 초기화"><Icon name="reset" /></button>}
      {onExitCompare && <button type="button" className="hud-btn" onClick={onExitCompare}>비교 닫기</button>}
    </div>
  );
}
