// 숫자·시간 표시 도우미.

export function formatViews(n) {
  if (n === null || n === undefined) return '조회수 비공개';
  if (n >= 1e8) return `조회수 ${trim(n / 1e8)}억회`;
  if (n >= 1e4) return `조회수 ${trim(n / 1e4)}만회`;
  return `조회수 ${n.toLocaleString('ko-KR')}회`;
}

function trim(x) {
  return x >= 10 ? Math.floor(x).toString() : (Math.floor(x * 10) / 10).toString();
}

export function formatDuration(seconds) {
  if (!seconds) return '';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const mm = h ? String(m).padStart(2, '0') : String(m);
  return `${h ? `${h}:` : ''}${mm}:${String(s).padStart(2, '0')}`;
}

export function formatAgo(iso, now = Date.now()) {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return '';
  const sec = Math.max(0, Math.round((now - t) / 1000));
  if (sec < 60) return '방금 전';
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}분 전`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}시간 전`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day}일 전`;
  if (day < 30) return `${Math.floor(day / 7)}주 전`;
  if (day < 365) return `${Math.floor(day / 30)}개월 전`;
  return `${Math.floor(day / 365)}년 전`;
}

// 올린 날짜(한국 시각) 「11.17」. 올해가 아니면 「2025.11.17」
export function formatDay(iso, now = Date.now()) {
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return '';
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' })
      .formatToParts(t).map((p) => [p.type, p.value]),
  );
  const thisYear = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric' })
    .formatToParts(new Date(now)).find((p) => p.type === 'year').value;
  return `${parts.year === thisYear ? '' : `${parts.year}.`}${parts.month}.${parts.day}`;
}

// 화면의 대상 이름: 연습 모드(sandbox)는 「연습」, 실제 유튜브는 「유튜브」
export function targetName(target) {
  if (target === 'sandbox') return '연습';
  if (target === 'youtube') return '유튜브';
  return '';
}

export function formatDate(iso) {
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return '';
  return t.toLocaleString('ko-KR', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

// 영상 제목 끝에 줄줄이 붙은 #태그를 나눈다(2026-11-17). 화면에서 태그만 흐리게 그려 제목 본문이
// 먼저 읽히게 한다. 제목 원문은 바꾸지 않는다: 두 조각을 이으면 원문 그대로다.
// 제목이 태그뿐이거나 태그가 없으면 { main: 원문, tags: '' }.
const TRAILING_TAGS = /(?:\s*#[^\s#]+)+\s*$/u;
export function splitTitleTags(title) {
  const text = String(title ?? '');
  const found = TRAILING_TAGS.exec(text);
  if (!found || !text.slice(0, found.index).trim()) return { main: text, tags: '' };
  return { main: text.slice(0, found.index), tags: text.slice(found.index) };
}

// 제목 한 덩어리: 본문 + 흐린 태그. 전체 원문은 부르는 쪽이 title 속성에 둔다
export function titleNode(title, className = 'video-title') {
  const { main, tags } = splitTitleTags(title);
  if (!tags) return el('span', { class: className, text: main });
  return el('span', { class: className }, [main, el('span', { class: 'title-tags', text: tags })]);
}

// 썸네일 + 길이 표시. 바깥 글은 textContent로만 넣는다.
// 그림을 못 불러오면 img를 떼어 내 주소가 없을 때와 같은 빈 자리(배경색)만 남긴다.
export function thumbnail(video) {
  const duration = formatDuration(video.duration_seconds);
  let img = null;
  if (video.thumbnail_url) {
    img = el('img', { src: video.thumbnail_url, alt: '', loading: 'lazy', referrerpolicy: 'no-referrer' });
    img.addEventListener('error', () => img.remove(), { once: true });
  }
  return el('span', { class: 'thumb' }, [
    img,
    duration ? el('span', { class: 'duration', text: duration }) : null,
  ]);
}
