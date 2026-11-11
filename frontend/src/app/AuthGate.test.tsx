import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { AuthGate } from './AuthGate';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('keeps the application unmounted until the gateway validates the session', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 202 })));
  render(<AuthGate required><div>Scene workspace</div></AuthGate>);
  expect(screen.queryByText('Scene workspace')).not.toBeInTheDocument();
  expect(await screen.findByText('Scene workspace')).toBeInTheDocument();
});

it('offers login for an unauthenticated session', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 401 })));
  render(<AuthGate required><div>Scene workspace</div></AuthGate>);
  const link = await screen.findByRole('link', { name: '팀 계정으로 로그인' });
  expect(link.getAttribute('href')).toMatch(/^\/oauth2\/start\?rd=/);
  expect(screen.queryByText('Scene workspace')).not.toBeInTheDocument();
});

it('does not treat an unreachable gateway as a successful session', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network')));
  render(<AuthGate required><div>Scene workspace</div></AuthGate>);
  expect(await screen.findByRole('alert')).toBeInTheDocument();
  expect(screen.queryByText('Scene workspace')).not.toBeInTheDocument();
});

it('leaves local development available without the hosted login gateway', () => {
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);
  render(<AuthGate required={false}><div>Scene workspace</div></AuthGate>);
  expect(screen.getByText('Scene workspace')).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});
