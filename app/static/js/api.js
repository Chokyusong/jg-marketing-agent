// 서버 API 호출. 오류는 ApiError(kind, message, action)로 바꿔 던진다.

export class ApiError extends Error {
  constructor({ kind = 'unknown', message = '요청을 처리하지 못했습니다.', action = '' } = {}) {
    super(message);
    this.kind = kind;
    this.action = action;
  }
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}) },
      ...options,
    });
  } catch {
    throw new ApiError({
      kind: 'server_down',
      message: '대시보드 서버에 연결하지 못했습니다.',
      action: '.\\scripts\\run.ps1로 서버가 켜져 있는지 확인해 주세요.',
    });
  }
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    if (body && body.error) throw new ApiError(body.error);
    if (response.status === 422) {
      throw new ApiError({ kind: 'invalid_input', message: '입력값을 확인해 주세요.', action: '' });
    }
    throw new ApiError({ message: `서버 오류 (HTTP ${response.status})`, action: '잠시 뒤 다시 시도해 주세요.' });
  }
  return body;
}

export const api = {
  status: () => request('/api/status'),
  searchVideos: ({ q, period, order, maxResults }) => {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (period) params.set('period', period);
    if (order) params.set('order', order);
    if (maxResults) params.set('max_results', String(maxResults));
    const qs = params.toString();
    return request(`/api/videos${qs ? `?${qs}` : ''}`);
  },
  resolveVideo: (url) => request('/api/videos/resolve', { method: 'POST', body: JSON.stringify({ url }) }),
};
