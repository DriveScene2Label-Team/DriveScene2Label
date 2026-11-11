import { QueryClientProvider } from '@tanstack/react-query';
import { lazy, Suspense, useEffect, useState } from 'react';
import { createBrowserRouter, Navigate, RouterProvider, useSearchParams } from 'react-router';
import { IconSprite } from '@/components/Icon';
import { ThemeSync } from '@/components/ThemeSync';
import { ToastHost } from '@/components/ToastHost';
import { InstanceWatcher } from '@/features/system/InstanceWatcher';
import { bindQueryClient } from '@/lib/jobs/submissions';
import { createQueryClient } from './queryClient';
import { SceneSearchPage } from '@/pages/SceneSearchPage';
import { RouteErrorPage } from './RouteErrorPage';

// Workspace pages carry the camera grid and the Rerun viewer; load them only when needed.
const SceneWorkspacePage = lazy(() => import('@/pages/SceneWorkspacePage'));
const SceneComparePage = lazy(() => import('@/pages/SceneComparePage'));
const LabelEditorPage = lazy(() => import('@/pages/LabelEditorPage'));
const DatasetUploadPage = lazy(() => import('@/pages/DatasetUploadPage'));

function LegacyLabelRoute() {
  const [params] = useSearchParams();
  return params.has('id') || params.has('job') ? <LabelEditorPage /> : <Navigate to="/uploads" replace />;
}

const loading = <div className="page-state" role="status"><span className="spinner" aria-hidden="true" /></div>;

const router = createBrowserRouter([{ errorElement: <RouteErrorPage />, children: [
  { path: '/', element: <Navigate to="/scenes" replace /> },
  { path: '/scenes', element: <SceneSearchPage /> },
  { path: '/scenes/:sceneId', element: <Suspense fallback={loading}><SceneWorkspacePage /></Suspense> },
  { path: '/compare', element: <Suspense fallback={loading}><SceneComparePage /></Suspense> },
  { path: '/uploads', element: <Suspense fallback={loading}><DatasetUploadPage /></Suspense> },
  { path: '/labels', element: <Suspense fallback={loading}><LegacyLabelRoute /></Suspense> },
  { path: '/label-files', element: <Suspense fallback={loading}><LabelEditorPage /></Suspense> },
  { path: '*', element: <Navigate to="/scenes" replace /> },
]}]);

export function App() {
  const [client] = useState(createQueryClient);
  // Bind after commit: in development StrictMode runs state initializers twice and keeps only one result, so binding
  // inside the initializer could point submissions (job/recording POST follow-ups) at a discarded QueryClient.
  useEffect(() => bindQueryClient(client), [client]);
  return (
    <QueryClientProvider client={client}>
      <IconSprite />
      <ThemeSync />
      <InstanceWatcher />
      <RouterProvider router={router} />
      <ToastHost />
    </QueryClientProvider>
  );
}
