// ③ 댓글 달기(8단계, R1·R3): 큰 단추 [댓글 달기] 한 번 → 고친 글 저장 → 초안 승인 → 게시 작업 시작.
// - 화면에 보이는 초안이 규칙 검사를 통과했을 때만 눌린다. 못 누르면 단추 아래에 이유를 쓴다(startBlocker).
// - 연습 모드(끔, 기본)면 실제 유튜브: 고른 프로필의 크롬으로 그 영상 페이지를 열어 한 글자씩 입력하고
//   「댓글」을 누르고 내 댓글을 확인한다(어떤 영상이든). 켜면 프로그램 안의 연습 페이지에 같은 순서로 단다.
// - 설정 「게시 직전 확인」을 켠 경우에만 입력 뒤 멈추고 큰 단추가 금색 [게시]로 바뀐다. 끄면(기본) 한 번으로 끝까지.
// - 진행 중에는 GET /api/jobs/{id}를 0.5초마다 물어 온다. 끝나면 오늘 숫자·기록·①의 「댓글 달았음」을 바로 고친다.
// - 바깥 글은 textContent로만 넣는다.
import { api } from './api.js';
import { draftText } from './draft.js';
import { targetName, withTopic } from './format.js';
import { refreshOps } from './ops.js';
import { focusProfile } from './profiles.js';
import { ensureApproved, isRunning } from './report.js';
import { getState, selectedVideo, setState, subscribe } from './state.js';
import { refreshStatus } from './topbar.js';

const $ = (id) => document.getElementById(id);
const POLL_MS = 500;

let timer = null;
let lastFinishedId = null;

const running = (job) => Boolean(job && !job.finished);
// 연습 모드 → API 대상: 켬 = 연습 페이지(sandbox), 끔 = 실제 게시(youtube)
const apiTarget = (target) => (target === 'sandbox' ? 'sandbox' : 'youtube');

// 진행 상태 말(UI_SPEC 0절: 프로필 여는 중 → 입력 중 → 게시 완료)
export const STATE_WORDS = {
  queued: '준비 중',
  launching: '프로필 여는 중',
  typing: '입력 중',
  awaiting_approval: '게시 대기',
  posting: '게시 중',
  verifying: '내 댓글 확인 중',
  posted: '게시 완료',
  failed: '실패',
};

// 서버의 진행 칸(0~6) → 화면의 세 칸(과제 문구 그대로: 프로필 여는 중 → 입력 중 → 게시 완료).
// 게시 대기·게시 중·내 댓글 확인 중은 3번 칸을 반만 채우고(아직 켜지지 않음), 확인까지 끝나야 켠다(4 = 모두 지남)
const PHASE_OF_STEP = [0, 1, 2, 3, 3, 3, 4];
export const LAST_PHASE = 3;

// 설정 「게시 직전 확인」: GET /api/status로 바로 바뀐 값을 받고, 오기 전에는 화면에 넣어 둔 처음 값
export function confirmBeforePost(state) {
  if (state.browser && typeof state.browser.confirm_before_post === 'boolean') return state.browser.confirm_before_post;
  const box = document.querySelector('.exec-settings');
  return Boolean(box && box.dataset.confirm === 'true');
}

export function modeNote(target, confirm = false) {
  if (target === 'sandbox') return '연습 모드 · 실제 유튜브가 아니라 프로그램 안의 연습 페이지에 답니다';
  return confirm
    ? '실제 유튜브 · 입력을 마치면 멈춥니다. 크롬 창의 글을 보고 [게시]를 눌러 주세요'
    : '실제 유튜브 · [댓글 달기]를 누르면 입력하고 바로 게시합니다';
}

// 최근 로그인 확인에서 「로그인 안 됨」으로 나온 프로필(서버의 시작 전 확인과 같은 기준)
function signedOutRecently(p, browser) {
  if (!p || p.signed_in !== false || !p.checked_at) return false;
  const at = Date.parse(p.checked_at);
  const trust = (browser && browser.login_trust_seconds) || 3600;
  return !Number.isNaN(at) && Date.now() - at < trust * 1000;
}

function loginBlocker(state) {
  const b = state.browser;
  const ops = state.ops;
  if (!b || !b.profiles || !b.profiles.length) return null;
  if (ops && ops.profile) {
    const p = b.profiles.find((x) => x.name === ops.profile);
    return signedOutRecently(p, b)
      ? `${ops.profile} 프로필이 유튜브에 로그인돼 있지 않습니다. 프로필 화면에서 [로그인하기]를 눌러 주세요.`
      : null;
  }
  return b.profiles.every((p) => signedOutRecently(p, b))
    ? '로그인된 프로필이 없습니다. 프로필 화면에서 [로그인하기]를 눌러 주세요.'
    : null;
}

// 자동 배정이 이번에 쓸 프로필(GET /api/status의 browser.auto_pick, 대상별)
export function autoPick(state) {
  const b = state.browser;
  const target = apiTarget(state.ops ? state.ops.target : 'sandbox');
  return (b && b.auto_pick && b.auto_pick[target]) || null;
}

export function autoOptionText(pick) {
  return pick && pick.name ? `자동 배정 · 이번에는 ${pick.name}` : '자동 배정';
}

// 실제 게시에서 로그인이 확인되지 않은 프로필을 쓰게 될 때 [댓글 달기] 아래에 보일 말과 그 프로필.
// 막지는 않는다(최근 「로그인 안 됨」은 loginBlocker가 막는다). 연습 모드는 로그인이 필요 없다.
export function loginHint(state) {
  const ops = state.ops;
  const b = state.browser;
  if (!ops || ops.target === 'sandbox' || !b || !b.profiles) return null;
  if (ops.profile) {
    const p = b.profiles.find((x) => x.name === ops.profile);
    if (!p || p.signed_in === true) return null;
    const text = p.signed_in === false
      ? `${withTopic(p.name)} 아직 로그인하지 않았습니다`
      : `${withTopic(p.name)} 아직 로그인을 확인하지 않았습니다`;
    return { text, profile: p.name };
  }
  const pick = autoPick(state);
  if (pick && pick.confirmed === false && pick.note) return { text: pick.note, profile: pick.name };
  return null;
}

function checkFor(state) {
  const v = state.validation;
  if (!v || v.videoId !== state.selectedId || v.text !== draftText()) return null;
  return v.result;
}

// [댓글 달기]를 누를 수 있는지와, 못 누르면 그 이유(쉬운 말로)
export const RISING_ONLY = '뜨기 직전 영상은 초안까지만 만듭니다. 댓글을 달려면 같은 영상을 [영상 불러오기]나 링크로 다시 불러오세요.';

export function startBlocker(state) {
  const video = selectedVideo();
  const ops = state.ops;
  const target = ops ? ops.target : 'sandbox';
  if (running(state.job)) return '다른 댓글을 다는 중입니다.';
  if (!video) return '①에서 영상을 고르면 초안이 나옵니다.';
  // R4: 뜨기 직전 목록에서 고른 영상은 초안까지만(서버도 거절한다)
  if (video.source === 'rising') return RISING_ONLY;
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
  if (ops && ops.stats && ops.stats.remaining <= 0) {
    return target === 'sandbox'
      ? '연습 모드로 오늘 올릴 수 있는 댓글을 다 썼습니다. 자정(한국 시각)이 지나면 다시 됩니다.'
      : '오늘 올릴 수 있는 댓글을 다 썼습니다. 자정(한국 시각)이 지나면 다시 됩니다.';
  }
  const b = state.browser;
  if (b && !b.chrome_found) return '이 PC에서 크롬을 찾지 못했습니다. 크롬을 설치해 주세요.';
  if (b && !b.playwright_ready) return '자동 입력 도구가 설치되지 않아 댓글을 달 수 없습니다.';
  if (target !== 'sandbox') {
    const ctx = state.context && state.context.video_id === state.selectedId ? state.context : null;
    if (ctx && ctx.comments_disabled) return '이 영상은 댓글이 막혀 있어 달 수 없습니다. 다른 영상을 골라 주세요.';
    const login = loginBlocker(state);
    if (login) return login;
  }
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
      target: apiTarget(ops.target),
      dailyLimit: ops.dailyLimit,
    });
  });
}

function onPrimary() {
  const { job } = getState();
  if (job && job.waiting_for === 'approve') act(() => api.approveJob(job.id));
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

export function stepClass(job, n) {
  if (!job) return '';
  const at = PHASE_OF_STEP[Math.min(Math.max(job.step, 0), 6)];
  if (job.state === 'failed') return n === Math.min(Math.max(at, 1), LAST_PHASE) ? 'is-failed' : (n < at ? 'is-done' : '');
  if (job.state === 'posted') return n === LAST_PHASE && !job.verified ? 'is-warn' : 'is-done';
  if (n < at) return 'is-done';
  if (n !== at) return '';
  return n === LAST_PHASE ? 'is-wait' : 'is-current'; // 「게시 완료」는 확인이 끝나야 켜진다
}

function paintSteps(job) {
  for (const li of $('job-steps').querySelectorAll('li')) {
    const cls = stepClass(job, Number(li.dataset.phase));
    for (const name of ['is-done', 'is-current', 'is-failed', 'is-wait', 'is-warn']) li.classList.toggle(name, cls === name);
  }
}

function idleTitle(state, video, blocker) {
  if (!video) return ['영상 선택 대기', '①에서 영상을 고르면 댓글 초안이 나오고, [댓글 달기]를 누르면 끝까지 진행합니다.'];
  if (isRunning(state)) return ['초안 만드는 중', `${video.title} — 초안이 나오면 [댓글 달기]를 누를 수 있습니다.`];
  if (!blocker) return ['댓글 달 준비 완료', `${video.title} — [댓글 달기]를 누르면 프로필을 열고 입력해 게시하고 내 댓글을 확인합니다.`];
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

  // 큰 단추 하나가 상태에 따라 [댓글 달기] → (게시 직전 확인을 켰으면) [게시] → (실패하면) [다시 시도]
  let label = '댓글 달기';
  let disabled = state.jobBusy || Boolean(blocker);
  if (job && job.waiting_for === 'approve') { label = '게시'; disabled = state.jobBusy; }
  else if (running(job)) { label = `${STATE_WORDS[job.state] || job.state_label}…`; disabled = true; }
  else if (state.jobBusy) label = '준비 중…';
  else if (job && job.state === 'failed' && video && job.video_id === video.video_id) label = '다시 시도';
  if (primary.textContent !== label) primary.textContent = label;
  primary.disabled = disabled;
  const why = !job || job.finished ? (state.jobBusy ? '' : blocker || '') : '';
  $('job-why').textContent = why && video && !isRunning(state) ? why : '';

  // 프로필: 「자동 배정 · 이번에는 유튜브2」, 로그인이 확인되지 않은 프로필이면 이유와 프로필 화면으로 가는 길
  const auto = $('profile').querySelector('option[value=""]');
  const autoText = autoOptionText(autoPick(state));
  if (auto && auto.textContent !== autoText) auto.textContent = autoText;
  const hint = running(job) ? null : loginHint(state);
  const loginLine = $('job-login');
  loginLine.hidden = !hint || Boolean(why && why.includes('로그인'));
  if (hint) {
    $('job-login-text').textContent = hint.text;
    $('job-login-btn').dataset.profile = hint.profile;
  }

  // 작은 단추: 필요한 것만([그만두기] · 게시 완료면 제목 옆 [댓글 보기] · 실패면 [화면 캡처 보기])
  show('job-cancel', running(job));
  const view = show('job-view', Boolean(job && job.state === 'posted'));
  if (job) {
    view.href = job.view_url;
    view.title = job.target === 'sandbox' ? '연습 페이지에서 내 댓글 보기' : '유튜브 영상 페이지에서 내 댓글 보기';
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
    // 끝나면 「게시 완료 · [댓글 보기]」(단추는 제목 옆). 확인을 못 했으면 그렇게 적는다
    title.textContent = job.state === 'posted'
      ? (job.verified ? '게시 완료 ·' : '게시됨 · 내 댓글 확인 못 함 ·')
      : job.state === 'failed' ? '게시 실패' : `${where} · ${STATE_WORDS[job.state] || job.state_label}`;
    const mark = job.disclosed === false ? ' · 광고 표기 없음' : '';
    desc.textContent = `${job.profile}${mark} · ${job.message}${left}`;
  } else {
    const [t, d] = idleTitle(state, video, blocker);
    title.textContent = t;
    desc.textContent = d;
  }

  // 아래 한 줄: 연습 모드/실제 유튜브 안내 · 작업 결과
  const dot = $('job-dot');
  dot.classList.remove('is-ok', 'is-bad', 'is-wait', 'is-off');
  let tone = 'is-ok';
  let text = modeNote(target, confirmBeforePost(state));
  if (job && job.state === 'failed') { tone = 'is-bad'; text = `${targetName(job.target)} · 실패`; }
  else if (job && job.state === 'posted') text = `${targetName(job.target)} · 게시 완료${job.verified ? '' : '(확인 못 함)'}`;
  else if (running(job) && job.state === 'verifying') { tone = 'is-wait'; text = `${targetName(job.target)} · 내 댓글 확인 중`; }
  else if (running(job)) { tone = 'is-wait'; text = modeNote(job.mode === 'sandbox' ? 'sandbox' : 'youtube', job.confirm_before_post); }
  else if (!state.browser) tone = 'is-wait';
  else if (!state.browser.chrome_found) tone = 'is-bad';
  dot.classList.add(tone);
  $('job-status').textContent = text;
}

export function initJob() {
  $('job-primary').addEventListener('click', onPrimary);
  $('job-cancel').addEventListener('click', () => {
    const { job } = getState();
    if (job) act(() => api.cancelJob(job.id));
  });
  $('job-login-btn').addEventListener('click', (event) => focusProfile(event.currentTarget.dataset.profile || ''));
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

