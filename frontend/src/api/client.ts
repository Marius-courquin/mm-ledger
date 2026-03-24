const BASE_URL = import.meta.env.VITE_API_URL ?? '/api';

interface ApiErrorResponse {
  status: number;
  detail: string;
}

function buildURL(path: string, params?: Record<string, string | number | boolean | undefined>): string {
  const url = new URL(`${BASE_URL}${path}`, window.location.origin);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.pathname + url.search;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (res.status === 423) {
    window.dispatchEvent(new Event('vault-locked'));
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      // keep statusText as detail
    }
    throw { status: res.status, detail } as ApiErrorResponse;
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

async function get<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
  const res = await fetch(buildURL(path, params), {
    method: 'GET',
    headers: { 'Accept': 'application/json' },
  });
  return handleResponse<T>(res);
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(buildURL(path), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return handleResponse<T>(res);
}

async function put<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(buildURL(path), {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return handleResponse<T>(res);
}

async function del(path: string): Promise<void> {
  const res = await fetch(buildURL(path), {
    method: 'DELETE',
    headers: { 'Accept': 'application/json' },
  });
  await handleResponse<void>(res);
}

export const api = { get, post, put, del };
