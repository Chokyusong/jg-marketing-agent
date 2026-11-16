// 기록 화면(R1). 3판의 겹침 패널(기록 전체 보기)을 화면으로 옮겼다.
// - 화면을 열 때마다 새로 불러온다(topbar.js의 'screen:show'). 작업 화면의 상태는 건드리지 않는다.
// - 기록: GET /api/records?limit=200. 거르기 전체 / 게시 / 실패. 실패 줄에는 이유와 [화면 캡처], 게시 줄에는 [유튜브에서 보기].
// - 프로필 화면은 profiles.js, 설정 화면은 settings.js(R2).
// - 바깥 글은 textContent로만 넣는다.
import { api } from './api.js';
import { el } from './format.js';
import { formatKst, resultText, toneOf, whereText } from './ops.js';
import { showScreen } from './topbar.js';

const $ = (id) => document.getElementById(id);
const ALL_ROWS = 200; // /api/records의 최대

// ---------------------------------------------------------------- 기록 화면

let allRecords = null;

function filterValue() {
  const checked = document.querySelector('input[name="records-filter"]:checked');
  return checked ? checked.value : 'all';
}

function fullRow(r) {
  const tone = toneOf(r);
  const showReason = r.reason && (r.result === 'failure' || r.action === 'draft');
  const status = el('td', { class: `st wrap ${tone}` }, [
    el('b', { text: resultText(r) }),
    showReason ? el('span', { class: 'st-reason', text: ` · ${r.reason}` }) : null,
  ]);
  const links = [];
  if (r.has_screenshot && r.job_id) {
    links.push(el('a', { href: `/api/jobs/${encodeURIComponent(r.job_id)}/screenshot`, target: '_blank', rel: 'noopener', text: '화면 캡처' }));
  }
  if (r.video_url && r.action === 'post' && r.result === 'success' && r.target === 'youtube') {
    links.push(el('a', { href: r.video_url, target: '_blank', rel: 'noopener noreferrer', text: '유튜브에서 보기' }));
  } else if (r.video_url) {
    links.push(el('a', { href: r.video_url, target: '_blank', rel: 'noopener noreferrer', text: '영상 보기' }));
  }
  return el('tr', { class: tone }, [
    el('td', { class: 'nowrap', text: formatKst(r.at), title: r.at }),
    el('td', { class: 'wrap', text: r.video_title || r.video_id || '–' }),
    el('td', { class: 'nowrap', text: whereText(r) || '–' }),
    el('td', { class: 'wrap' }, [
      r.comment_text || (r.action === 'analyze' ? r.reason : '') || '–',
      r.disclosed === false ? el('span', { class: 'rec-mark', text: ' · 광고 표기 없음' }) : null,
    ]),
    status,
    el('td', {}, [el('span', { class: 'links' }, links)]),
  ]);
}

function renderAll() {
  const body = $('records-all-body');
  const meta = $('records-all-meta');
  if (!allRecords) return;
  const filter = filterValue();
  const items = allRecords.items.filter((r) => (filter === 'post' ? r.action === 'post' : filter === 'failure' ? r.result === 'failure' : true));
  const failures = allRecords.items.filter((r) => r.result === 'failure').length;
  const shown = allRecords.items.length < allRecords.total ? ` · 최근 ${allRecords.items.length}건만 보입니다` : '';
  meta.textContent = `전체 ${allRecords.total}건 · 실패 ${failures}건${shown} · 최신이 위`;
  if (!items.length) {
    const text = filter === 'failure' ? '실패한 기록이 없습니다.' : filter === 'post' ? '아직 게시 기록이 없습니다.' : '아직 기록이 없습니다. 초안 만들기와 게시가 여기에 남습니다.';
    body.replaceChildren(el('tr', {}, [el('td', { colspan: '6', class: 'empty-row', text })]));
    return;
  }
  body.replaceChildren(...items.map(fullRow));
}

async function loadRecords() {
  $('records-all-meta').textContent = '불러오는 중…';
  try {
    allRecords = await api.records(ALL_ROWS);
    renderAll();
  } catch (error) {
    allRecords = null;
    $('records-all-meta').textContent = '기록을 불러오지 못했습니다';
    $('records-all-body').replaceChildren(el('tr', {}, [el('td', { colspan: '6', class: 'empty-row', text: `${error.message || ''} ${error.action || ''}`.trim() })]));
  }
}

// ----------------------------------------------------------------

export function initScreens() {
  for (const radio of document.querySelectorAll('input[name="records-filter"]')) radio.addEventListener('change', renderAll);
  $('records-all').addEventListener('click', () => showScreen('records', { focus: true }));
  document.addEventListener('screen:show', (event) => {
    if (event.detail === 'records') loadRecords();
  });
}
