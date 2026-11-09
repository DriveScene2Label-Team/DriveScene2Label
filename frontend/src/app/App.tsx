import { QueryClientProvider } from '@tanstack/react-query';
import { lazy, Suspense, useState } from 'react';
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router';
import { Toasts } from '@/components/Toasts';
import { InstanceWatcher } from '@/features/system/InstanceWatcher';
import { bindQueryClient } from '@/lib/jobs/submissions';
import { createQueryClient } from './queryClient';
import { SceneSearchPage } from '@/pages/SceneSearchPage';

// Workspace pages carry the camera grid and the Rerun viewer; load them only when needed.
const SceneWorkspacePage = lazy(() => import('@/pages/SceneWorkspacePage'));
const SceneComparePage = lazy(() => import('@/pages/SceneComparePage'));
const LabelEditorPage = lazy(() => import('@/pages/LabelEditorPage'));

const loading = <div className="page-state" role="status"><span className="spin" aria-hidden="true" /></div>;

const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/scenes" replace /> },
  { path: '/scenes', element: <SceneSearchPage /> },
  { path: '/scenes/:sceneId', element: <Suspense fallback={loading}><SceneWorkspacePage /></Suspense> },
  { path: '/compare', element: <Suspense fallback={loading}><SceneComparePage /></Suspense> },
  { path: '/labels', element: <Suspense fallback={loading}><LabelEditorPage /></Suspense> },
  { path: '*', element: <Navigate to="/scenes" replace /> },
]);

export function App() {
  const [client] = useState(() => {
    const qc = createQueryClient();
    bindQueryClient(qc);
    return qc;
  });
  return (
    <QueryClientProvider client={client}>
      <InstanceWatcher />
      <RouterProvider router={router} />
      <Toasts />
    </QueryClientProvider>
  );
}
