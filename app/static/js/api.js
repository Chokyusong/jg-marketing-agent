// 서버 API 호출. 오류는 ApiError(kind, message, action)로 바꿔 던진다.

export class ApiError extends Error {
  constructor({ kind = 'unknown', message = '요청을 처리하지 못했습니다.', action = '', failures = [] } = {}) {
    super(message);
    this.kind = kind;
    this.action = action;
    this.failures = failures; // 승인 거절(409)일 때 걸린 검사 항목
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
  // 3단계: 영상 맥락
  buildContext: (videoId, { refresh = false } = {}) =>
    request(`/api/videos/${encodeURIComponent(videoId)}/context${refresh ? '?refresh=true' : ''}`, { method: 'POST' }),
  saveTranscript: (videoId, text) =>
    request(`/api/videos/${encodeURIComponent(videoId)}/transcript`, { method: 'PUT', body: JSON.stringify({ text }) }),
  clearTranscript: (videoId) =>
    request(`/api/videos/${encodeURIComponent(videoId)}/transcript`, { method: 'DELETE' }),
  // 6단계: 규칙 검사 V1~V12
  validate: (videoId, text) =>
    request('/api/validate', { method: 'POST', body: JSON.stringify({ video_id: videoId, text }) }),
  // 5단계: 분석과 초안
  analyze: (videoId) => request(`/api/analysis/${encodeURIComponent(videoId)}`, { method: 'POST' }),
  storedAnalysis: (videoId) => request(`/api/analysis/${encodeURIComponent(videoId)}`),
  createDraft: (videoId, { another = false } = {}) =>
    request('/api/drafts', { method: 'POST', body: JSON.stringify({ video_id: videoId, another }) }),
  listDrafts: (videoId) => request(`/api/drafts?video_id=${encodeURIComponent(videoId)}`),
  updateDraft: (id, body) => request(`/api/drafts/${id}`, { method: 'PATCH', body: JSON.stringify({ body }) }),
  approveDraft: (id) => request(`/api/drafts/${id}/approve`, { method: 'POST' }),
  // 7단계: 운영 규칙과 기록
  profiles: (target) => request(`/api/profiles?target=${encodeURIComponent(target)}`),
  records: (limit) => request(`/api/records?limit=${encodeURIComponent(limit)}`),
  todayStats: (target, dailyLimit) => {
    const params = new URLSearchParams({ target });
    if (dailyLimit) params.set('daily_limit', String(dailyLimit));
    return request(`/api/stats/today?${params}`);
  },
};
