// ③ 댓글 달기(8단계, R1): 큰 단추 [댓글 달기] 한 번 → 고친 글 저장 → 초안 승인 → 게시 작업 시작.
// - 화면에 보이는 초안이 규칙 검사를 통과했을 때만 눌린다. 못 누르면 단추 아래에 이유를 쓴다(startBlocker).
// - 연습 모드(켬)면 프로그램 안의 연습 페이지에 자동으로 입력·게시한다. 끄면 실제 유튜브:
//   내 채널 영상(own_video)이면 그 영상 페이지에 자동 입력, 그 밖의 영상은 크롬을 프로필과 영상 주소로 열기만 한다.
// - 서버는 지금처럼 게시 직전에 사람의 승인을 기다린다(R1에서 서버 동작은 바꾸지 않는다). 그때 큰 단추가
//   금색 [게시]로 바뀐다. 사람이 직접 게시하는 경우에는 [게시했어요] · [게시 안 함].
// - 진행 중에는 GET /api/jobs/{id}를 0.5초마다 물어 온다. 끝나면 오늘 숫자·기록·①의 「댓글 달았음」을 바로 고친다.
// - 바깥 글은 textContent로만 넣는다.
import { api } from './api.js';
import { draftText, ownVideo } from './draft.js';
import { targetName } from './format.js';
import { refreshOps } from './ops.js';
import { ensureApproved, isRunning } from './report.js';
import { getState, selectedVideo, setState, subscribe } from './state.js';
import { refreshStatus } from './topbar.js';

const $ = (id) => document.getElementById(id);
const POLL_MS = 500;

let timer = null;
let lastFinishedId = null;

const running = (job) => Boolean(job && !job.finished);
// 연습 모드 → API 대상. 끄면 실제 유튜브(내 채널 영상이면 자동 게시 youtube_auto, 그 밖은 열기만 assist)
const autoPost = (state, target) => target === 'youtube' && ownVideo(state);
const apiTarget = (state, target) => {
  if (target !== 'youtube') return 'sandbox';
  return autoPost(state, target) ? 'youtube_auto' : 'assist';
};

// 진행 상태 말(UI_SPEC 0절: 프로필 여는 중 → 입력 중 → 게시 완료)
export const STATE_WORDS = {
  queued: '준비 중',
  launching: '프로필 여는 중',
  typing: '입력 중',
  awaiting_approval: '게시 대기',
  awaiting_confirm: '직접 게시 대기',
  posting: '게시 중',
  verifying: '확인 중',
  posted: '게시 완료',
  failed: '실패',
};

// 서버의 진행 칸(0~6) → 화면의 네 칸(프로필 여는 중 · 입력 중 · 게시 · 확인). 6은 모두 지남
const PHASE_OF_STEP = [0, 1, 2, 3, 3, 4, 5];

export function modeNote(target, auto = false) {
  if (target === 'sandbox') return '연습 모드 · 실제 유튜브가 아니라 프로그램 안의 연습 페이지에 답니다';
  return auto
    ? '실제 유튜브 · 내 채널 영상이라 자동으로 입력하고 게시합니다'
    : '실제 유튜브 · 크롬으로 영상을 열고 댓글을 복사해 둡니다. 게시는 직접 합니다';
}

function checkFor(state) {
  const v = state.validation;
  if (!v || v.videoId !== state.selectedId || v.text !== draftText()) return null;
  return v.result;
}

// [댓글 달기]를 누를 수 있는지와, 못 누르면 그 이유(쉬운 말로)
export function startBlocker(state) {
  const video = selectedVideo();
  const ops = state.ops;
  const target = ops ? ops.target : 'sandbox';
  if (running(state.job)) return '다른 댓글을 다는 중입니다.';
  if (!video) return '①에서 영상을 고르면 초안이 나옵니다.';
  if (isRunning(state)) return '②에서 댓글 초안을 만드는 중입니다.';
  const d = state.draft && state.draft.video_id === state.selectedId ? state.draft : null;
  if (!d) return '②에서 댓글 초안이 나와야 달 수 있습니다.';
  if (video.commented && video.commented[target]) return '이미 댓글을 단 영상입니다. 영상 하나에는 댓글을 하나만 답니다.';
  const result = checkFor(state);
  if (!result) return state.validationError ? '규칙 검사를 하지 못했습니다. 글을 다시 고쳐 보세요.' : '규칙 검사 중입니다.';
  if (!result.passed) {
    const failed = result.checks.filter((c) => !c.passed).length;
    return `규칙 검사에 걸린 항목 ${failed}개를 고쳐야 달 수 있습니다.`;
  }
  if (ops && ops.stats && ops.stats.remaining <= 0) return '오늘 올릴 수 있는 댓글을 다 썼습니다. 자정(한국 시각)이 지나면 다시 됩니다.';
  const b = state.browser;
  if (b && !b.chrome_found) return '이 PC에서 크롬을 찾지 못했습니다. 크롬을 설치해 주세요.';
  if (b && target === 'sandbox' && !b.playwright_ready) return '자동 입력 도구가 설치되지 않아 연습 모드를 쓸 수 없습니다.';
  if (b && autoPost(state, target) && !b.playwright_ready) return '자동 입력 도구가 설치되지 않아 자동 게시를 할 수 없습니다.';
  return null;
}

function stopPolling() {
  clearInterval(timer);
  timer = null;
}

function startPolling(id) {
  stopPolling();
  timer = setInterval(() => poll(id), POLL_MS);
}

async function poll(id) {
  try {
    const job = await api.getJob(id);
    if (getState().job && getState().job.id !== id) return;
    setState({ job });
    if (job.finished) {
      stopPolling();
      onFinished(job);
    }
  } catch (error) {
    if (error.kind === 'job_not_found') {
      stopPolling();
      setState({ job: null });
    }
  }
}

// 끝난 작업: 숫자·기록을 다시 받고, 게시됐으면 ① 목록에 「댓글 달았음」을 바로 붙인다
function onFinished(job) {
  if (lastFinishedId === job.id) return;
  lastFinishedId = job.id;
  if (job.state === 'posted') {
    const videos = getState().videos.map((v) => (v.video_id === job.video_id
      ? { ...v, commented: { ...(v.commented || {}), [job.target]: true } }
      : v));
    setState({ videos });
  }
  refreshOps();
  refreshStatus();
}

async function act(fn) {
  setState({ jobBusy: true, jobError: null });
  try {
    const job = await fn();
    setState({ job, jobBusy: false });
    if (job.finished) onFinished(job);
    else if (!timer) startPolling(job.id);
  } catch (error) {
    setState({ jobBusy: false, jobError: error });
    refreshOps();
  }
}

// [댓글 달기] 한 번: 고친 글 저장 → 승인 → 시작
function start() {
  const state = getState();
  if (startBlocker(state) || state.jobBusy) return;
  const videoId = state.selectedId;
  act(async () => {
    const draft = await ensureApproved();
    const now = getState();
    if (now.selectedId !== videoId) throw Object.assign(new Error('그사이 다른 영상을 골랐습니다.'), { action: '다시 [댓글 달기]를 눌러 주세요.' });
    const ops = now.ops;
    return api.startJob({
      videoId,
      draftId: draft.id,
      profile: ops.profile,
      target: apiTarget(now, ops.target),
      dailyLimit: ops.dailyLimit,
    });
  });
}

async function copyDraft() {
  const job = getState().job;
  if (!job) return;
  const button = $('job-copy');
  try {
    await navigator.clipboard.writeText(job.comment_text);
  } catch {
    const area = document.createElement('textarea');
    area.value = job.comment_text;
    document.body.append(area);
    area.select();
    document.execCommand('copy');
    area.remove();
  }
  button.textContent = '복사했어요';
  setTimeout(() => { button.textContent = '댓글 복사'; }, 1500);
}

function onPrimary() {
  const { job } = getState();
  if (job && job.waiting_for === 'approve') act(() => api.approveJob(job.id));
  else if (job && job.waiting_for === 'confirm') act(() => api.confirmJob(job.id, true));
  else start();
}

// 작업 상자에 보일 작업: 진행 중이면 그것, 끝났으면 지금 고른 영상의 것
// (고른 영상이 없으면 — 새로 고친 뒤 이어 본 작업 — 마지막 결과를 그대로 둔다)
function shownJob(state) {
  const job = state.job;
  if (!job) return null;
  if (running(job) || !state.selectedId || job.video_id === state.selectedId) return job;
  return null;
}

function show(id, on) {
  const node = $(id);
  node.hidden = !on;
  return node;
}

function paintSteps(job) {
  const at = job ? PHASE_OF_STEP[Math.min(Math.max(job.step, 0), 6)] : 0;
  for (const li of $('job-steps').querySelectorAll('li')) {
    const n = Number(li.dataset.phase);
    const failed = Boolean(job) && job.state === 'failed' && n === Math.max(at, 1);
    li.classList.toggle('is-done', Boolean(job) && !failed && (n < at || job.state === 'posted'));
    li.classList.toggle('is-current', Boolean(job) && !job.finished && n === at);
    li.classList.toggle('is-failed', failed);
  }
}

function idleTitle(state, video, blocker) {
  if (!video) return ['영상 선택 대기', '①에서 영상을 고르면 댓글 초안이 나오고, [댓글 달기]를 누르면 끝까지 진행합니다.'];
  if (isRunning(state)) return ['초안 만드는 중', `${video.title} — 초안이 나오면 [댓글 달기]를 누를 수 있습니다.`];
  if (!blocker) return ['댓글 달 준비 완료', `${video.title} — [댓글 달기]를 누르면 프로필을 열고 입력해 게시합니다.`];
  return ['아직 달 수 없음', video.title];
}

function paint(state) {
  const job = shownJob(state);
  const video = selectedVideo();
  const target = state.ops ? state.ops.target : 'sandbox';
  const primary = $('job-primary');
  const blocker = startBlocker(state);
  $('job-box').dataset.state = job ? job.state : 'idle';
  paintSteps(job);

  // 큰 단추 하나가 상태에 따라 [댓글 달기] → [게시] / [게시했어요] → (실패하면) [다시 시도]
  let label = '댓글 달기';
  let disabled = state.jobBusy || Boolean(blocker);
  if (job && job.waiting_for === 'approve') { label = '게시'; disabled = state.jobBusy; }
  else if (job && job.waiting_for === 'confirm') { label = '게시했어요'; disabled = state.jobBusy; }
  else if (running(job)) { label = `${STATE_WORDS[job.state] || job.state_label}…`; disabled = true; }
  else if (state.jobBusy) label = '준비 중…';
  else if (job && job.state === 'failed' && video && job.video_id === video.video_id) label = '다시 시도';
  if (primary.textContent !== label) primary.textContent = label;
  primary.disabled = disabled;
  const why = !job || job.finished ? (state.jobBusy ? '' : blocker || '') : '';
  $('job-why').textContent = why && video && !isRunning(state) ? why : '';

  // 작은 단추 줄: 필요한 것만
  const waitingConfirm = Boolean(job && job.waiting_for === 'confirm');
  show('job-copy', waitingConfirm);
  show('job-not-posted', waitingConfirm);
  show('job-cancel', running(job));
  const view = show('job-view', Boolean(job && job.state === 'posted'));
  if (job) {
    view.href = job.view_url;
    view.textContent = job.target === 'sandbox' ? '댓글 보기' : '유튜브에서 내 댓글 보기';
  }
  const shot = show('job-shot', Boolean(job && job.has_screenshot));
  if (job && job.screenshot_url) shot.href = job.screenshot_url;
  $('job-actions').hidden = ![...$('job-actions').children].some((n) => !n.hidden);

  // 오류(시작·승인 거절)와 실패 이유
  const err = $('job-error');
  const problem = state.jobError
    ? `${state.jobError.message} ${state.jobError.action || ''}`.trim()
    : job && job.state === 'failed' ? `실패 · ${job.reason}` : '';
  err.textContent = problem;
  err.hidden = !problem;

  // 제목·설명
  const title = $('exec-title');
  const desc = $('exec-desc');
  if (job) {
    const where = job.target === 'sandbox' ? '연습' : '유튜브';
    const left = job.seconds_left !== null && job.seconds_left !== undefined ? ` (남은 시간 ${Math.ceil(job.seconds_left / 60)}분)` : '';
    title.textContent = job.state === 'posted'
      ? (job.verified ? '게시 완료 · 확인됨' : '게시 완료 · 확인 못 함')
      : job.state === 'failed' ? '게시 실패' : `${where} · ${STATE_WORDS[job.state] || job.state_label}`;
    desc.textContent = `${job.profile} · ${job.message}${left}`;
  } else {
    const [t, d] = idleTitle(state, video, blocker);
    title.textContent = t;
    desc.textContent = d;
  }

  // 아래 한 줄: 연습 모드/실제 유튜브 안내 · 작업 결과
  const dot = $('job-dot');
  dot.classList.remove('is-ok', 'is-bad', 'is-wait', 'is-off');
  let tone = 'is-ok';
  let text = modeNote(target, autoPost(state, target));
  if (job && job.state === 'failed') { tone = 'is-bad'; text = `${targetName(job.target)} · 실패`; }
  else if (job && job.state === 'posted') text = `${targetName(job.target)} · 게시 완료${job.verified ? '' : '(확인 못 함)'}`;
  else if (running(job)) { tone = 'is-wait'; text = modeNote(job.mode === 'sandbox' ? 'sandbox' : 'youtube', job.mode === 'auto'); }
  else if (!state.browser) tone = 'is-wait';
  else if (!state.browser.chrome_found) tone = 'is-bad';
  dot.classList.add(tone);
  $('job-status').textContent = text;
}

export function initJob() {
  $('job-primary').addEventListener('click', onPrimary);
  $('job-copy').addEventListener('click', copyDraft);
  $('job-not-posted').addEventListener('click', () => {
    const { job } = getState();
    if (job) act(() => api.confirmJob(job.id, false));
  });
  $('job-cancel').addEventListener('click', () => {
    const { job } = getState();
    if (job) act(() => api.cancelJob(job.id));
  });
  subscribe(paint);
  // 화면을 새로 고쳐도 진행 중인 작업을 이어 본다(GET /api/status의 browser.active_job_id)
  let resumed = false;
  subscribe((state) => {
    if (resumed || !state.browser) return;
    resumed = true;
    const id = state.browser.active_job_id;
    if (id && !state.job) startPolling(id);
  });
  // 글을 고치면 검사 결과가 낡으므로 큰 단추도 바로 다시 본다
  $('draft-text').addEventListener('input', () => paint(getState()));
}

