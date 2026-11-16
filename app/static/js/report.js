// 02 영상 맥락 분석과 AI 초안(5단계).
// [분석하고 초안 만들기]를 누르면 "맥락 수집 → 분석 → 초안 → 검사"를 차례로 표시하며 채운다.
// 영상을 고르자마자 돌리지 않는다(모델이 느려서 영상을 훑어보는 동안 매번 돌면 안 된다).
// 영상을 고르면 저장된 분석·초안만 불러온다(모델을 부르지 않는다).
// [다른 초안 생성]은 이미 쓴 근거를 피해 초안만 다시, [이 초안 승인]은 고친 글을 먼저 저장(PATCH)하고 승인.
import { api } from './api.js';
import { draftText, isApproved, loadDraft } from './draft.js';
import { refreshOps } from './ops.js';
import { getState, setState, subscribe } from './state.js';

const $ = (id) => document.getElementById(id);
const PHASES = ['context', 'analysis', 'draft', 'check'];
const PHASE_TEXT = {
  context: '영상 자료 모으는 중',
  analysis: 'AI가 영상 맥락을 분석하는 중',
  draft: 'AI가 초안을 쓰고 규칙 검사로 고치는 중(최대 3번)',
  check: '규칙 검사 결과 정리 중',
};
const SLOW_NOTE = '큰 모델은 처음에 1분쯤 걸립니다';

let lastSelected = null;
let ticker = null;

const isRunning = (state) => Boolean(state.run && !['done', 'error'].includes(state.run.phase));
const mine = (videoId) => getState().selectedId === videoId;

function setRun(patch) {
  const run = { ...(getState().run || {}), ...patch };
  setState({ run });
}

function seconds(run) {
  const end = run.endedAt || Date.now();
  return Math.max(0, Math.round((end - run.startedAt) / 1000));
}

// 맥락은 3단계(context.js)가 영상을 고를 때 이미 만든다. 아직이면 끝날 때까지 기다린다.
function waitForContext(videoId) {
  const state = getState();
  if (state.context && state.context.video_id === videoId) return Promise.resolve();
  if (!state.contextLoading) return api.buildContext(videoId).then((data) => setState({ context: data, quota: data.quota }));
  return new Promise((resolve, reject) => {
    const stop = subscribe((s) => {
      if (s.selectedId !== videoId) { stop(); reject(new Error('stale')); return; }
      if (s.contextLoading) return;
      stop();
      if (s.context && s.context.video_id === videoId) resolve();
      else reject(s.contextError || new Error('맥락을 만들지 못했습니다.'));
    });
  });
}

async function run(videoId, { another = false } = {}) {
  if (!videoId || isRunning(getState())) return;
  const startedAt = Date.now();
  setState({ run: { videoId, phase: another ? 'draft' : 'context', startedAt, endedAt: null, note: '', another }, runError: null });
  startTicker();
  try {
    if (!another) {
      await waitForContext(videoId);
      if (!mine(videoId)) return;
      setRun({ phase: 'analysis' });
      const analysis = await api.analyze(videoId);
      if (!mine(videoId)) return;
      setState({ analysis });
      setRun({ phase: 'draft' });
    }
    const draft = await api.createDraft(videoId, { another });
    if (!mine(videoId)) return;
    setRun({ phase: 'check' });
    loadDraft(draft);
    const tries = draft.passed
      ? `초안 ${draft.attempts}번째에 통과`
      : `초안 ${draft.attempts}번 모두 규칙 검사에 걸림 — 빨간 항목을 고쳐 주세요`;
    setRun({ phase: 'done', endedAt: Date.now(), note: `${tries} · ${draft.model || 'AI'}` });
  } catch (error) {
    if (!mine(videoId) || error.message === 'stale') return;
    setRun({ phase: 'error', failedAt: getState().run.phase, endedAt: Date.now() });
    setState({ runError: error });
  } finally {
    stopTicker();
    refreshOps(); // 분석·초안(성공이든 실패든)이 작업 기록과 오늘 통계에 남는다(7단계)
  }
}

async function approve() {
  const state = getState();
  const draft = state.draft;
  if (!draft || state.approving) return;
  const videoId = draft.video_id;
  setState({ approving: true, runError: null });
  try {
    let current = draft;
    const text = draftText();
    if (text !== draft.body) {
      current = await api.updateDraft(draft.id, text); // 사람이 고친 글: 서버가 다시 검사
      if (!mine(videoId)) return;
      loadDraft(current);
    }
    const approved = await api.approveDraft(current.id);
    if (!mine(videoId)) return;
    loadDraft(approved);
    setState({ approving: false });
  } catch (error) {
    if (!mine(videoId)) return;
    setState({ approving: false, runError: error });
  } finally {
    refreshOps(); // 승인(거절도)이 작업 기록에 남는다(7단계)
  }
}

// 영상을 고르면 저장된 분석과 초안(승인한 것이 있으면 그것, 없으면 가장 새것)만 불러온다.
async function restore(videoId) {
  try {
    const [analysis, list] = await Promise.all([api.storedAnalysis(videoId), api.listDrafts(videoId)]);
    if (!mine(videoId) || getState().run) return; // 그새 [분석하고 초안 만들기]를 눌렀으면 그것을 따른다
    const items = list.items || [];
    const pick = items.find((d) => d.status === 'approved') || items.find((d) => d.status === 'draft');
    setState({ analysis: analysis || null });
    if (pick) loadDraft(pick);
  } catch {
    // 저장된 것을 못 불러와도 [분석하고 초안 만들기]로 새로 만들 수 있다
  }
}

function startTicker() {
  stopTicker();
  ticker = setInterval(() => render(getState()), 1000);
}

function stopTicker() {
  clearInterval(ticker);
  ticker = null;
}

function line(id, text, full = text) {
  const dd = $(id);
  dd.textContent = text;
  if (full) dd.setAttribute('title', full);
  else dd.removeAttribute('title');
}

function renderAnalysis(state) {
  const a = state.analysis && state.analysis.video_id === state.selectedId ? state.analysis : null;
  const busy = state.run && state.run.videoId === state.selectedId && ['context', 'analysis'].includes(state.run.phase);
  const empty = !state.selectedId ? '–' : busy ? '분석 중…' : '–';
  line('an-topic', a ? a.topic : empty, a ? a.topic : '');
  line('an-concern', a ? a.concern : empty, a ? a.concern : '');
  line('an-tone', a ? a.tone : empty, a ? a.tone : '');
  line('an-needs', a ? a.viewer_needs : empty, a ? a.viewer_needs : '');
  if (!a || !a.evidence.length) {
    line('an-evidence', a ? '근거 없음' : '근거 문장과 출처', '');
    return;
  }
  // 지금 초안이 쓴 근거를 맨 앞에. 전체는 마우스를 올리면 보인다.
  const d = state.draft && state.draft.video_id === state.selectedId ? state.draft : null;
  const used = d ? a.evidence.find((e) => e.quote === d.evidence_quote) : null;
  const first = used || a.evidence[0];
  const rest = a.evidence.length - 1;
  const text = `'${first.quote}' · ${first.source_label}${rest > 0 ? ` 외 ${rest}개` : ''}`;
  const full = a.evidence.map((e) => `'${e.quote}' · ${e.source_label}`).join('\n')
    + (a.dropped_count ? `\n(영상 자료에 없어 버린 근거 ${a.dropped_count}개)` : '');
  line('an-evidence', text, full);
}

function renderRun(state) {
  const r = state.run && state.run.videoId === state.selectedId ? state.run : null;
  const running = isRunning(state);
  const at = r ? PHASES.indexOf(r.phase) : -1;
  for (const li of $('run-steps').children) {
    const i = PHASES.indexOf(li.dataset.phase);
    const done = r && (r.phase === 'done' || (at >= 0 && i < at) || (r.another && i < 2 && r.phase !== 'error'));
    li.classList.toggle('is-done', Boolean(done));
    li.classList.toggle('is-current', Boolean(r && i === at && running));
    li.classList.toggle('is-bad', Boolean(r && r.phase === 'error' && i === PHASES.indexOf(r.failedAt || '')));
  }
  const note = $('run-note');
  note.classList.toggle('is-busy', running);
  if (!state.selectedId) note.textContent = SLOW_NOTE;
  else if (r && running) note.textContent = `${PHASE_TEXT[r.phase]}… ${seconds(r)}초 · ${SLOW_NOTE}`;
  else if (r && r.phase === 'done') note.textContent = `${seconds(r)}초 · ${r.note}`;
  else if (r && r.phase === 'error') note.textContent = `${seconds(r)}초 만에 멈춤 · 아래 안내를 확인해 주세요`;
  else if (state.analysis && state.analysis.video_id === state.selectedId) note.textContent = '저장된 분석 · 다시 누르면 새로 분석합니다';
  else note.textContent = SLOW_NOTE;

  const btn = $('run-btn');
  btn.disabled = !state.selectedId || running;
  btn.textContent = running ? '진행 중…' : '분석하고 초안 만들기 ↗';
  $('report-box').setAttribute('aria-busy', String(running));

  const err = state.runError;
  const box = $('run-error');
  if (state.selectedId && err) {
    $('run-error-msg').textContent = err.message || '요청을 처리하지 못했습니다.';
    $('run-error-action').textContent = err.action || '';
    box.hidden = false;
  } else {
    box.hidden = true;
  }
}

function renderButtons(state) {
  const d = state.draft && state.draft.video_id === state.selectedId ? state.draft : null;
  const running = isRunning(state);
  const another = $('another-btn');
  another.disabled = !d || running || state.approving;
  const v = state.validation;
  const text = draftText();
  const fresh = v && v.videoId === state.selectedId && v.text === text;
  const passed = Boolean(fresh && v.result.passed);
  const approved = isApproved(state);
  const approveBtn = $('approve-btn');
  approveBtn.disabled = !d || running || state.approving || !passed || approved || d.status === 'superseded';
  approveBtn.textContent = state.approving ? '승인 중…' : approved ? '승인됨' : '이 초안 승인';
  if (!d) approveBtn.title = '[분석하고 초안 만들기]로 AI 초안을 만든 뒤 승인할 수 있습니다';
  else if (!passed) approveBtn.title = '규칙 검사를 모두 통과해야 승인할 수 있습니다';
  else approveBtn.removeAttribute('title');
}

function render(state) {
  renderAnalysis(state);
  renderRun(state);
  renderButtons(state);
}

export function initReport() {
  $('run-btn').addEventListener('click', () => run(getState().selectedId));
  $('another-btn').addEventListener('click', () => run(getState().selectedId, { another: true }));
  $('approve-btn').addEventListener('click', approve);
  $('draft-text').addEventListener('input', () => renderButtons(getState()));

  subscribe((state) => {
    if (state.selectedId !== lastSelected) {
      lastSelected = state.selectedId;
      setState({ analysis: null, runError: null, run: null, approving: false });
      if (state.selectedId) restore(state.selectedId);
      return; // setState가 다시 그린다
    }
    render(state);
  });
}
