import { Link } from 'react-router';
import { Icon } from './Icon';

export function AppMark({ to }: { to: string }) {
  return (
    <Link className="app-mark" to={to} aria-label="DriveScene2Label 씬 목록">
      <span className="mark"><Icon name="cube" /></span>DriveScene2Label
    </Link>
  );
}
