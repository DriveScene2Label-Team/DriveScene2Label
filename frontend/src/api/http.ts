import type { ApiErrorBody } from './dto';

/** Normalized error. `kind` separates "the server answered with an error" from "we could not reach it". */
export type ApiErrorKind = 'http' | 'network' | 'format' | 'aborted';

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly code: string | null;
  readonly path: string;

  constructor(kind: ApiErrorKind, path: string, message: string, status: number | null = null, code: string | null = null) {
    super(message);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = status;
    this.code = code;
    this.path = path;
  }

  /** True for failures where retrying the same GET may help (no answer, 502/503/504). */
  get transient(): boolean {
    return this.kind === 'network' || this.status === 502 || this.status === 503 || this.status === 504;
  }
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError;
}

async function parseErrorBody(res: Response): Promise<ApiErrorBody | null> {
  try {
    const text = await res.text();
    if (!text) return null;
    const body = JSON.parse(text) as unknown;
    return body && typeof body === 'object' ? (body as ApiErrorBody) : null;
  } catch {
    return null;
  }
}

/** Accepts both `{code,message}` (ApiErrors) and Spring default `{status,error,message,path}`. */
export async function toApiError(res: Response, path: string): Promise<ApiError> {
  const body = await parseErrorBody(res);
  const code = body?.code ?? (body?.error ? `HTTP_${res.status}` : `HTTP_${res.status}`);
  const message = body?.message || body?.error || res.statusText || `HTTP ${res.status}`;
  return new ApiError('http', path, message, res.status, code);
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

export interface JsonResponse<T> {
  status: number;
  data: T;
}

/** Fetch a Spring `/api/*` JSON endpoint. Paths are same-origin relative URLs. */
export async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<JsonResponse<T>> {
  if (!path.startsWith('/api/')) throw new ApiError('format', path, 'Only Spring /api/* may be called');
  let res: Response;
  try {
    res = await fetch(path, {
      method: options.method ?? 'GET',
      headers: {
        Accept: 'application/json',
        ...(options.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
    });
  } catch (e) {
    if (options.signal?.aborted || (e instanceof DOMException && e.name === 'AbortError')) {
      throw new ApiError('aborted', path, 'Request aborted');
    }
    throw new ApiError('network', path, '서버에 연결할 수 없어요');
  }
  if (!res.ok) throw await toApiError(res, path);
  const text = await res.text();
  try {
    return { status: res.status, data: (text ? JSON.parse(text) : null) as T };
  } catch {
    throw new ApiError('format', path, '서버 응답 형식을 읽을 수 없어요', res.status);
  }
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  return (await requestJson<T>(path, { signal })).data;
}

export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') sp.set(k, String(v));
  const s = sp.toString();
  return s ? `?${s}` : '';
}

/**
 * Short Korean message for UI. Keeps 404/409 meaning distinct from connection failures. A stable server code (e.g.
 * VESPA_NOT_CONFIGURED from a readiness check) is shown with the server's own message. A bare 502/504 means a
 * gateway/upstream failure, not a model failure.
 */
export function describeError(e: unknown): string {
  if (!isApiError(e)) return '알 수 없는 오류가 발생했어요';
  if (e.kind === 'network') return '서버에 연결할 수 없어요';
  if (e.kind === 'format') return '서버 응답 형식을 읽을 수 없어요';
  if (e.kind === 'aborted') return '요청이 취소되었어요';
  if (e.code && !/^HTTP_\d+$/.test(e.code) && e.code !== 'INVALID_REQUEST') return e.message;
  switch (e.status) {
    case 400: return `요청을 확인해 주세요 (${e.message})`;
    case 404: return '대상을 찾을 수 없어요';
    case 409: return `지금 처리할 수 없는 요청이에요 (${e.message})`;
    case 502: return '중계 서버가 상위 서비스의 올바른 응답을 받지 못했어요 (HTTP 502)';
    case 503: return '서비스를 일시적으로 사용할 수 없어요';
    case 504: return '상위 서비스 응답 시간이 초과됐어요 (HTTP 504)';
    default: return `서버 오류가 발생했어요 (HTTP ${e.status ?? '?'})`;
  }
}
