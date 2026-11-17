// ② 영상 선택: 고민 한 줄과 AI 댓글 초안(5단계, R1에서 자동으로).
// - ①에서 영상을 고르면 단추를 누르지 않아도 "영상 자료 읽는 중 → 고민 정리 중 → 댓글 쓰는 중"을 차례로 돈다.
// - 그 영상에 저장된 초안이 있으면 모델을 부르지 않고 그것을 바로 보인다(GET /api/analysis/{id}, /api/drafts?video_id=).
//   저장된 분석만 있으면 분석은 건너뛰고 초안만 만든다.
// - 다른 영상을 고르면 하던 것은 버린다(차례 번호 runToken으로 늦게 온 응답·타이머를 무시한다).
// - [다른 댓글 만들기]는 이미 쓴 근거를 피해 초안만 다시. 실패하면 이유와 [다시 해 보기].
// - 연애 고민이 없는 자료(no_love_concern)면 초안 없이 멈추고 「자막 직접 넣기」를 연다. 자막을 [저장]하면 다시 만든다.
// - ensureApproved(): ③의 [댓글 달기]가 부른다. 고친 글이면 먼저 저장(PATCH)하고, 아직 승인 전이면 승인한다.
import { api } from './api.js';
import { discloseOn, draftText, loadDraft } from './draft.js';
import { refreshOps } from './ops.js';
import { getState, setState, subscribe } from './state.js';

const $ = (id) => document.getElementById(id);
const PHASES = ['context', 'analysis', 'draft', 'check'];
const PHASE_TEXT = {
  context: '영상 자료 읽는 중',
  analysis: '고민 정리 중',
  draft: '댓글 쓰는 중',
  check: '규칙 검사 정리 중',
};
const SLOW_NOTE = '처음에는 1분쯤 걸릴 수 있습니다';
// R4: 모델이 아직 메모리에 없으면(GET /api/llm/loaded) 그 요청은 서버가 420초까지 기다린다
export const COLD_NOTE = 'AI 모델을 불러오는 중입니다. 처음에는 1~3분 걸립니다';
// 실제 데이터 보정: 영상 자료에 연애 고민이 없으면 서버가 초안을 만들지 않고 이 오류로 멈춘다.
const NO_CONCERN = 'no_love_concern';

let lastSelected = null;
let ticker = null;
let runToken = 0; // 영상을 바꾸거나 새로 돌 때마다 하나씩 늘린다. 옛 차례의 응답은 버린다

export const isRunning = (state) => Boolean(state.run && state.run.videoId === state.selectedId
  && !['done', 'error'].includes(state.run.phase));
const mine = (videoId) => getState().selectedId === videoId;

function openTranscriptPaste() {
  const paste = $('transcript-paste');
  if (!paste) return;
  paste.open = true;
  const box = $('transcript-text');
  if (box && !box.disabled) box.focus({ preventScroll: true });
}

// 첫 AI 요청 전에 모델이 올라가 있는지 본다. 아니면 run.cold로 안내를 바꾼다(모르면 그대로)
function checkCold(live) {
  const ai = getState().ai;
  if (ai && ai.loaded === false) setRun({ cold: true });
  api.llmLoaded()
    .then((d) => { if (live()) setRun({ cold: d.loaded === false }); })
    .catch(() => {});
}

function setRun(patch) {
  setState({ run: { ...(getState().run || {}), ...patch } });
}

function seconds(run) {
  const end = run.endedAt || Date.now();
  return Math.max(0, Math.round((end - run.startedAt) / 1000));
}

// 맥락은 context.js가 영상을 고를 때 이미 만든다. 아직이면 끝날 때까지 기다린다.
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
      else reject(s.contextError || new Error('영상 자료를 읽지 못했습니다.'));
    });
  });
}

// analysis: 저장된 분석(있으면 분석을 건너뛴다). another: [다른 댓글 만들기]
async function run(videoId, { another = false, analysis = null } = {}) {
  if (!videoId) return;
  const token = ++runToken;
  const live = () => token === runToken && mine(videoId);
  const skipAnalysis = another || Boolean(analysis);
  setState({
    run: { videoId, phase: another ? 'draft' : 'context', startedAt: Date.now(), endedAt: null, note: '', skipAnalysis },
    runError: null,
    ...(analysis ? { analysis } : {}),
  });
  startTicker(token);
  if (!another && analysis) checkCold(live); // 초안이 첫 AI 요청
  try {
    if (!another) {
      await waitForContext(videoId);
      if (!live()) return;
      if (!analysis) {
        setRun({ phase: 'analysis' });
        checkCold(live);
        const fresh = await api.analyze(videoId);
        if (!live()) return;
        setState({ analysis: fresh });
      }
      setRun({ phase: 'draft', ...(analysis ? {} : { cold: false }) }); // 분석이 모델을 불러 뒀다
    }
    const draft = await api.createDraft(videoId, { another, disclose: discloseOn() });
    if (!live()) return;
    setRun({ phase: 'check' });
    loadDraft(draft);
    const tries = draft.passed
      ? `${draft.attempts}번째 초안이 규칙 검사를 통과했습니다`
      : `초안 ${draft.attempts}번 모두 규칙 검사에 걸렸습니다 — 빨간 항목을 고쳐 주세요`;
    setRun({ phase: 'done', endedAt: Date.now(), note: tries });
  } catch (error) {
    if (!live() || error.message === 'stale') return;
    setRun({ phase: 'error', failedAt: getState().run.phase, endedAt: Date.now() });
    setState({ runError: error, ...(error.kind === NO_CONCERN ? { analysis: null } : {}) });
    if (error.kind === NO_CONCERN) openTranscriptPaste();
  } finally {
    if (token === runToken) stopTicker(); // 새 차례의 타이머는 건드리지 않는다
    refreshOps(); // 분석·초안(성공이든 실패든)이 기록과 오늘 숫자에 남는다(7단계)
  }
}

// 영상을 고르면: 저장된 초안이 있으면 그것(승인한 것 → 가장 새 초안), 없으면 자동으로 만든다.
async function pick(videoId) {
  const token = runToken;
  setState({ run: { videoId, phase: 'restore', startedAt: Date.now(), endedAt: null, note: '' } });
  const [analysis, list] = await Promise.all([
    api.storedAnalysis(videoId).catch(() => null),
    api.listDrafts(videoId).catch(() => ({ items: [] })),
  ]);
  if (token !== runToken || !mine(videoId)) return; // 그새 다른 영상을 골랐다
  const items = list.items || [];
  const stored = items.find((d) => d.status === 'approved') || items.find((d) => d.status === 'draft');
  if (stored) {
    setState({ analysis: analysis || null, run: { videoId, phase: 'done', stored: true, startedAt: Date.now(), endedAt: Date.now(), note: '' } });
    loadDraft(stored);
    return;
  }
  run(videoId, { analysis: analysis || null });
}

// ③ [댓글 달기]: 화면의 글을 그대로 승인한 초안을 돌려준다(고친 글이면 먼저 저장 — 서버가 다시 검사한다)
export async function ensureApproved() {
  const state = getState();
  const draft = state.draft;
  if (!draft || draft.video_id !== state.selectedId) {
    throw Object.assign(new Error('댓글 초안이 없습니다.'), { action: '②에서 초안이 나온 뒤 다시 눌러 주세요.' });
  }
  const videoId = draft.video_id;
  setState({ approving: true });
  try {
    let current = draft;
    const text = draftText();
    if (text !== draft.body) {
      current = await api.updateDraft(draft.id, text);
      if (mine(videoId)) loadDraft(current);
    }
    if (current.status !== 'approved') {
      current = await api.approveDraft(current.id);
      if (mine(videoId)) loadDraft(current);
    }
    return current;
  } finally {
    setState({ approving: false });
    refreshOps(); // 승인(거절도)이 기록에 남는다(7단계)
  }
}

function startTicker(token) {
  stopTicker();
  ticker = setInterval(() => {
    if (token !== runToken) return;
    render(getState());
  }, 1000);
}

function stopTicker() {
  clearInterval(ticker);
  ticker = null;
}

function line(id, text, full = text) {
  const node = $(id);
  if (node.textContent !== text) node.textContent = text;
  if (full) node.setAttribute('title', full);
  else node.removeAttribute('title');
}

function renderAnalysis(state) {
  const a = state.analysis && state.analysis.video_id === state.selectedId ? state.analysis : null;
  const r = state.run && state.run.videoId === state.selectedId ? state.run : null;
  const busy = r && ['restore', 'context', 'analysis'].includes(r.phase);
  const empty = !state.selectedId ? '–' : busy ? '정리 중…' : '–';
  const none = !a && !busy && state.selectedId && state.runError && state.runError.kind === NO_CONCERN;
  line('an-topic', a ? a.topic : empty, a ? a.topic : '');
  line('an-concern', a ? a.concern : none ? '이 영상에서는 연애 고민을 찾지 못했습니다' : busy ? '고민 정리 중…' : '–', a ? a.concern : '');
  line('an-tone', a ? a.tone : empty, a ? a.tone : '');
  line('an-needs', a ? a.viewer_needs : empty, a ? a.viewer_needs : '');
  // C1: 그 영상의 핵심 말(초안이 하나 이상 담는다 — 검사 V7)
  const keys = a && a.key_phrases && a.key_phrases.length ? a.key_phrases.join(' · ') : '';
  line('an-keys', a ? keys || '없음' : empty, keys);
  if (!a || !a.evidence.length) {
    line('an-evidence', a ? '근거 없음' : none ? '자막을 직접 넣으면 다시 찾아봅니다' : '근거 문장과 출처', '');
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
    const finished = r && r.phase === 'done';
    const done = r && (finished || (at >= 0 && i < at) || (r.skipAnalysis && i === 1 && r.phase !== 'error'));
    li.classList.toggle('is-done', Boolean(done));
    li.classList.toggle('is-current', Boolean(r && i === at && running));
    li.classList.toggle('is-bad', Boolean(r && r.phase === 'error' && i === PHASES.indexOf(r.failedAt || '')));
  }
  const note = $('run-note');
  note.classList.toggle('is-busy', running);
  let text = SLOW_NOTE;
  if (!state.selectedId) text = SLOW_NOTE;
  else if (r && r.phase === 'restore') text = '앞서 만든 초안을 찾는 중…';
  else if (r && running) text = `${PHASE_TEXT[r.phase]}… ${seconds(r)}초 · ${r.cold && r.phase !== 'context' ? COLD_NOTE : SLOW_NOTE}`;
  else if (r && r.phase === 'done' && r.stored) text = '앞서 만든 초안입니다 · 새로 만들려면 [다른 댓글 만들기]';
  else if (r && r.phase === 'done') text = `${seconds(r)}초 · ${r.note}`;
  else if (r && r.phase === 'error') text = `${seconds(r)}초 만에 멈췄습니다 · 아래 안내를 확인해 주세요`;
  if (note.textContent !== text) note.textContent = text;

  const btn = $('run-btn');
  btn.disabled = !state.selectedId || running;
  $('report-box').setAttribute('aria-busy', String(running));

  const err = state.runError;
  const box = $('run-error');
  if (state.selectedId && err) {
    $('run-error-msg').textContent = err.message || '요청을 처리하지 못했습니다.';
    $('run-error-action').textContent = err.action || '';
    btn.hidden = err.kind === NO_CONCERN; // 고민이 없으면 다시 해도 같다. 자막을 넣으면 저절로 다시 만든다
    box.hidden = false;
  } else {
    box.hidden = true;
  }
}

function renderButtons(state) {
  const d = state.draft && state.draft.video_id === state.selectedId ? state.draft : null;
  const job = state.job;
  const posting = Boolean(job && !job.finished);
  $('another-btn').disabled = !d || isRunning(state) || state.approving || state.jobBusy || posting;
}

function render(state) {
  renderAnalysis(state);
  renderRun(state);
  renderButtons(state);
}

export function initReport() {
  $('run-btn').addEventListener('click', () => run(getState().selectedId));
  $('another-btn').addEventListener('click', () => {
    const state = getState();
    if (!isRunning(state)) run(state.selectedId, { another: true });
  });
  // 자막을 직접 넣었는데 아직 초안이 없으면(고민 없음·실패) 그 자막으로 다시 만든다
  document.addEventListener('transcript:saved', (event) => {
    const state = getState();
    const videoId = event.detail;
    const hasDraft = state.draft && state.draft.video_id === videoId;
    if (mine(videoId) && !hasDraft && !isRunning(state)) run(videoId);
  });

  subscribe((state) => {
    if (state.selectedId !== lastSelected) {
      lastSelected = state.selectedId;
      runToken += 1; // 하던 것은 버린다
      stopTicker();
      setState({ analysis: null, runError: null, run: null, approving: false });
      if (state.selectedId) pick(state.selectedId);
      return; // setState가 다시 그린다
    }
    render(state);
  });
}
