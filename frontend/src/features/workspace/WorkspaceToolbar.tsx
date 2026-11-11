import { Icon } from '@/components/Icon';
import { MoreMenu } from '@/components/MoreMenu';
import { DataOriginBadge } from '@/features/system/DataOriginBadge';
import { useLayout } from '@/stores/layout';
import { toast } from '@/stores/toast';

export type WorkspaceMode = 'camlidar' | 'cams' | 'compare';
const MODES: Array<[WorkspaceMode, string]> = [['camlidar', '카메라 + 3D'], ['cams', '카메라'], ['compare', '비교']];

interface Props {
  title: string;
  sub: string;
  mode: WorkspaceMode;
  onMode: (m: WorkspaceMode) => void;
  backLabel: string;
  onBack: () => void;
  datasetId: number | null;
}

export async function copyCurrentLink(): Promise<void> {
  try {
    await navigator.clipboard.writeText(window.location.href);
    toast('링크를 복사했어요', 'ok');
  } catch {
    toast('이 환경에서는 클립보드를 쓸 수 없어요. 주소창의 주소를 사용해 주세요', 'error');
  }
}

export function WorkspaceToolbar({ title, sub, mode, onMode, backLabel, onBack, datasetId }: Props) {
  const hidden = useLayout((s) => s.inspectorHidden);
  const setHidden = useLayout((s) => s.setInspectorHidden);
  return (
    <header className="toolbar">
      <div className="tb-left">
        <button type="button" className="icon-btn" onClick={onBack} aria-label={backLabel} title={backLabel}><Icon name="back" /></button>
        <div className="tb-title">
          <h1 id="page-title" tabIndex={-1}>{title}</h1>
          <p className="tb-sub" title={sub}>{sub}</p>
        </div>
      </div>
      <div className="seg tb-modes" role="group" aria-label="보기 방식">
        {MODES.map(([m, l]) => <button key={m} type="button" aria-pressed={mode === m} onClick={() => onMode(m)}>{l}</button>)}
      </div>
      <div className="tb-right">
        <DataOriginBadge datasetId={datasetId} />
        <button type="button" className="icon-btn" data-action="copy-link" onClick={() => void copyCurrentLink()} aria-label="링크 복사" title="현재 씬, 보기, 프레임이 담긴 링크 복사"><Icon name="link" /></button>
        <button type="button" className="icon-btn" aria-pressed={!hidden} onClick={() => setHidden(!hidden)} aria-label="인스펙터 보기" title="인스펙터 (\)"><Icon name="sidebar" /></button>
        <MoreMenu workspace />
      </div>
    </header>
  );
}

/** Full-page state (bad link, scene not found, loading). */
export function PageState({ title, detail, actions, loading }: { title?: string; detail?: string; actions?: React.ReactNode; loading?: boolean }) {
  if (loading) return <div className="page-state" role="status"><span className="spinner" aria-hidden="true" /></div>;
  return (
    <div className="page-state">
      <div className="empty empty--err" role="alert">
        <Icon name="warn" />
        <b>{title}</b>
        {detail && <p>{detail}</p>}
        {actions && <div className="suggest">{actions}</div>}
      </div>
    </div>
  );
}
