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
