// 통제된 테스트 페이지(8단계, DESIGN 6.1). 실제 유튜브가 아니다.
// - 댓글 상자의 입력 이벤트 수를 세어 저장할 때 함께 보낸다(한 글자씩 입력됐는지 확인용).
// - 저장은 이 앱의 /sandbox/api/comments에만 한다. 바깥 글은 textContent로만 넣는다.
const body = document.body;
const videoId = body.dataset.video;
const profile = body.dataset.profile || '';
const fail = body.dataset.fail || '';

const $ = (id) => document.getElementById(id);
const input = $('comment-input');
const submit = $('comment-submit'); // fail=hide_button이면 없다
const status = $('post-status');
let inputEvents = 0;

function setStatus(text, tone = '') {
  status.textContent = text;
  status.dataset.tone = tone;
}

function syncButton() {
  if (submit) submit.disabled = !input.value.trim();
}

function item(c) {
  const li = document.createElement('li');
  li.className = 'c-item';
  const meta = document.createElement('p');
  meta.className = 'c-meta';
  meta.textContent = `${c.profile || '프로필 없음'} · ${new Date(c.created_at).toLocaleString('ko-KR')}`;
  const text = document.createElement('p');
  text.className = 'c-body';
  text.textContent = c.body;
  li.append(meta, text);
  return li;
}

async function loadComments() {
  const res = await fetch(`/sandbox/api/comments?v=${encodeURIComponent(videoId)}`);
  if (!res.ok) return;
  const data = await res.json();
  $('comment-list').replaceChildren(...data.items.map(item));
  $('comment-count').textContent = String(data.items.length);
}

input.addEventListener('input', () => {
  inputEvents += 1;
  input.dataset.inputEvents = String(inputEvents);
  syncButton();
});

$('comment-cancel').addEventListener('click', () => {
  input.value = '';
  inputEvents = 0;
  input.dataset.inputEvents = '0';
  setStatus('');
  syncButton();
});

$('comment-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const text = input.value;
  if (!text.trim() || !submit) return;
  submit.disabled = true;
  setStatus('게시 중…', 'busy');
  body.dataset.state = 'posting';
  try {
    const res = await fetch('/sandbox/api/comments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ video_id: videoId, body: text, profile, input_events: inputEvents, fail }),
    });
    if (!res.ok) {
      let message = `저장하지 못했습니다(HTTP ${res.status}).`;
      try {
        const data = await res.json();
        if (data && data.error && data.error.message) message = data.error.message;
      } catch { /* 본문 없음 */ }
      setStatus(message, 'bad');
      body.dataset.state = 'error';
      syncButton();
      return;
    }
    input.value = '';
    inputEvents = 0;
    input.dataset.inputEvents = '0';
    setStatus('댓글을 달았습니다.', 'ok');
    body.dataset.state = 'posted';
    await loadComments();
  } catch {
    setStatus('서버에 연결하지 못했습니다.', 'bad');
    body.dataset.state = 'error';
  }
  syncButton();
});

loadComments();
