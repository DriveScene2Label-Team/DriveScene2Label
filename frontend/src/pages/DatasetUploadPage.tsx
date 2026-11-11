import { Link } from 'react-router';
import { AppMark } from '@/components/AppMark';
import { MoreMenu } from '@/components/MoreMenu';
import { DatasetUpload } from '@/features/labeling/DatasetUpload';

export default function DatasetUploadPage() {
  return <div className="app app--lib">
    <header className="toolbar">
      <div className="tb-left"><AppMark to="/scenes" /></div>
      <div />
      <div className="tb-right"><Link className="btn plain" to="/scenes">씬 목록</Link><MoreMenu workspace={false} /></div>
    </header>
    <main className="library" id="main">
      <div className="upload-page">
        <h1>데이터 업로드</h1>
        <p className="muted">원본을 올린 뒤, 씬을 선택해 라벨을 생성하고 수정하세요.</p>
        <DatasetUpload disabled={false} />
        <p className="muted small">이미 올린 데이터는 <Link className="link" to="/scenes">씬 목록</Link>에서 다시 열 수 있어요.</p>
      </div>
    </main>
  </div>;
}
