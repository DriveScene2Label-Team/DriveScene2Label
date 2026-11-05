import { QueryClientProvider } from '@tanstack/react-query';
import { lazy, Suspense, useEffect, useState } from 'react';
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router';
import { IconSprite } from '@/components/Icon';
import { ThemeSync } from '@/components/ThemeSync';
import { ToastHost } from '@/components/ToastHost';
import { InstanceWatcher } from '@/features/system/InstanceWatcher';
import { bindQueryClient } from '@/lib/jobs/submissions';
import { createQueryClient } from './queryClient';
import { SceneSearchPage } from '@/pages/SceneSearchPage';

// Workspace pages carry the camera grid and the Rerun viewer; load them only when needed.
const SceneWorkspacePage = lazy(() => import('@/pages/SceneWorkspacePage'));
const SceneComparePage = lazy(() => import('@/pages/SceneComparePage'));

const loading = <div className="page-state" role="status"><span className="spinner" aria-hidden="true" /></div>;

const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/scenes" replace /> },
  { path: '/scenes', element: <SceneSearchPage /> },
  { path: '/scenes/:sceneId', element: <Suspense fallback={loading}><SceneWorkspacePage /></Suspense> },
  { path: '/compare', element: <Suspense fallback={loading}><SceneComparePage /></Suspense> },
  { path: '*', element: <Navigate to="/scenes" replace /> },
]);

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
