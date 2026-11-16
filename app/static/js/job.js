// 03 작업 상자(8단계): 큰 버튼, 진행 단계 6개, 승인·복사·확인 단추, 실패 사유와 화면 캡처, [댓글 보기].
// - 큰 버튼은 승인한 초안 + 그 대상에서 댓글 안 단 영상 + 오늘 남은 횟수가 있을 때만 켠다.
// - 작업 방식이 「테스트 페이지 자동 실행」(sandbox)이면 통제된 테스트 페이지에서만 자동 입력·게시한다.
//   「수동 승인 후 게시」(실제 유튜브, assist)는 크롬을 프로필과 영상 주소로 열기만 한다. 붙여넣기와 게시는 사람.
// - 진행 중에는 GET /api/jobs/{id}를 0.5초마다 물어 온다. 끝나면 오늘 통계·작업 기록·01칸 「댓글 단 영상」을 바로 고친다.
// - 큰 버튼 하나가 상태에 따라 [브라우저에서 영상 열기] → [게시 승인](sandbox) / [게시했어요](assist)로 바뀐다
//   (단추를 늘려 03칸이 길어지지 않게). 바깥 글은 textContent로만 넣는다.
import { api } from './api.js';
import { isApproved } from './draft.js';
import { refreshOps } from './ops.js';
import { getState, selectedVideo, setState, subscribe } from './state.js';
import { refreshStatus } from './topbar.js';

const $ = (id) => document.getElementById(id);
const POLL_MS = 500;
const OPEN_TEXT = '브라우저에서 영상 열기 ↗';
const GOAL = '게시 여부는 로그인된 사용자 본인이 결정합니다.';

let timer = null;
let lastFinishedId = null;

const running = (job) => Boolean(job && !job.finished);
const apiTarget = (target) => (target === 'youtube' ? 'assist' : 'sandbox');

function modeNote(target) {
  return target === 'sandbox'
    ? '통제된 테스트 페이지에서 실행 · 실제 유튜브가 아닙니다'
    : '실제 유튜브는 크롬으로 열기만 합니다 · 붙여넣기와 게시는 직접';
}

// 큰 버튼을 켤 수 있는지와, 못 켜면 그 이유
export function startBlocker(state) {
  const video = selectedVideo();
  const ops = state.ops;
  const target = ops ? ops.target : 'sandbox';
  if (running(state.job)) return '다른 작업이 진행 중입니다.';
  if (!video) return '01에서 영상을 고르세요.';
  if (!isApproved(state)) return '02에서 규칙 검사를 통과한 초안을 승인해야 열 수 있습니다.';
  if (video.commented && video.commented[target]) return '이미 댓글을 단 영상입니다. 영상 하나에는 댓글을 하나만 답니다.';
  if (ops && ops.stats && ops.stats.remaining <= 0) return '오늘 상한을 다 썼습니다. 한국 시각 자정이 지나면 다시 됩니다.';
  const b = state.browser;
  if (b && !b.chrome_found) return '크롬을 찾지 못했습니다. 크롬을 설치하거나 config.yaml의 browser.chrome_path를 적어 주세요.';
  if (b && target === 'sandbox' && !b.playwright_ready) return 'Playwright가 없어 테스트 페이지 자동 실행을 못 합니다.';
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

// 끝난 작업: 통계·기록을 다시 받고, 게시됐으면 01칸 목록에 「댓글 단 영상」을 바로 붙인다
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

function start() {
  const state = getState();
  if (startBlocker(state)) return;
  const ops = state.ops;
  act(() => api.startJob({
    videoId: state.selectedId,
    draftId: state.draft.id,
    profile: ops.profile,
    target: apiTarget(ops.target),
    dailyLimit: ops.dailyLimit,
  }));
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
  setTimeout(() => { button.textContent = '초안 복사'; }, 1500);
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
  for (const li of $('job-steps').querySelectorAll('li')) {
    const n = Number(li.dataset.step);
    const failed = job && job.state === 'failed' && n === job.step;
    li.classList.toggle('is-done', Boolean(job) && !failed && n < job.step);
    li.classList.toggle('is-current', Boolean(job) && !job.finished && n === job.step);
    li.classList.toggle('is-failed', failed);
  }
}

function paint(state) {
  const job = shownJob(state);
  const video = selectedVideo();
  const target = state.ops ? state.ops.target : 'sandbox';
  const box = $('job-box');
  const primary = $('job-primary');
  const title = $('exec-title');
  const desc = $('exec-desc');
  box.dataset.state = job ? job.state : 'idle';
  paintSteps(job);

  // 큰 버튼
  if (job && job.waiting_for === 'approve') {
    primary.textContent = '게시 승인 — 「댓글」 누르기';
    primary.disabled = state.jobBusy;
  } else if (job && job.waiting_for === 'confirm') {
    primary.textContent = '게시했어요';
    primary.disabled = state.jobBusy;
  } else if (running(job)) {
    primary.textContent = `진행 중 · ${job.state_label}`;
    primary.disabled = true;
  } else {
    primary.textContent = OPEN_TEXT;
    primary.disabled = state.jobBusy || Boolean(startBlocker(state));
  }

  // 작은 단추 줄: 필요한 것만
  const waitingConfirm = Boolean(job && job.waiting_for === 'confirm');
  show('job-copy', waitingConfirm);
  show('job-not-posted', waitingConfirm);
  show('job-cancel', running(job));
  const view = show('job-view', Boolean(job && job.state === 'posted'));
  if (job) view.href = job.view_url;
  const shot = show('job-shot', Boolean(job && job.has_screenshot));
  if (job && job.screenshot_url) shot.href = job.screenshot_url;
  $('job-actions').hidden = ![...$('job-actions').children].some((n) => !n.hidden);

  // 오류(시작·승인 거절)와 실패 사유
  const err = $('job-error');
  const problem = state.jobError
    ? `${state.jobError.message} ${state.jobError.action || ''}`.trim()
    : job && job.state === 'failed' ? `실패 · ${job.reason}` : '';
  err.textContent = problem;
  err.hidden = !problem;

  // 제목·설명(승인 전 단계의 문구는 flow.js가 쓴다)
  if (job) {
    const where = job.mode === 'sandbox' ? '테스트 페이지' : '실제 유튜브';
    const left = job.seconds_left !== null && job.seconds_left !== undefined ? ` (남은 시간 ${Math.ceil(job.seconds_left / 60)}분)` : '';
    title.textContent = job.state === 'posted'
      ? (job.verified ? '게시 완료 · 확인됨' : '게시됨 · 확인 못 함')
      : job.state === 'failed' ? '게시 실패' : `${where} · ${job.state_label}`;
    desc.textContent = `${job.profile} · ${job.message}${left}`;
  } else if (video && isApproved(state)) {
    const blocker = startBlocker(state);
    title.textContent = blocker ? '초안 승인 완료 · 열 수 없음' : '작업 준비 완료';
    desc.textContent = blocker ? `${blocker} ${GOAL}` : `선택: ${video.title} — [브라우저에서 영상 열기]를 누르면 시작합니다. ${GOAL}`;
  }

  // 아래 한 줄: 작업 방식 안내 / 작업 상태
  const dot = $('job-dot');
  dot.classList.remove('is-ok', 'is-bad', 'is-wait', 'is-off');
  let tone = 'is-ok';
  let line = modeNote(target);
  if (job && job.state === 'failed') { tone = 'is-bad'; line = `${job.target_label} · 실패`; }
  else if (job && job.state === 'posted') line = `${job.target_label} · 게시 완료${job.verified ? '' : '(확인 못 함)'}`;
  else if (running(job)) { tone = 'is-wait'; line = modeNote(job.mode === 'sandbox' ? 'sandbox' : 'youtube'); }
  else if (!state.browser) tone = 'is-wait';
  else if (!state.browser.chrome_found) tone = 'is-bad';
  dot.classList.add(tone);
  $('job-status').textContent = line;
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
  // 글을 고치면 승인 표시가 내려가므로 큰 버튼도 바로 다시 본다
  $('draft-text').addEventListener('input', () => paint(getState()));
}
