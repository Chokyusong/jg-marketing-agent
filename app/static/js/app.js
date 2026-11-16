// 화면 시작점(R1 프로그램형 화면, UI_SPEC 4판).
// 왼쪽 줄·위 줄·아래 줄과 화면 바꾸기(topbar.js), 작업 화면 세 칸:
//   ① 영상 불러오기(discover.js) → ② 영상 선택(analysis.js 요약, context.js 자막, report.js 자동 분석·초안,
//   draft.js 글 상자와 규칙 검사) → ③ 댓글 달기(ops.js 설정·기록, job.js [댓글 달기] 한 번에 게시까지).
// 기록·프로필·설정 화면(screens.js). 진행 단계(flow.js), 다음 행동 하나만 금색(next.js, 맨 마지막).
import { initAnalysis } from './analysis.js';
import { initContext } from './context.js';
import { initDiscover } from './discover.js';
import { initDraft } from './draft.js';
import { initFlow } from './flow.js';
import { initJob } from './job.js';
import { initLayout } from './layout.js';
import { initNext } from './next.js';
import { initOps } from './ops.js';
import { initReport } from './report.js';
import { initScreens } from './screens.js';
import { initTopbar } from './topbar.js';

initTopbar();
initDiscover();
initAnalysis();
initContext();
initDraft();
initReport();
initFlow();
initOps();
initJob();
initScreens();
initLayout();
initNext(); // 다른 칸이 단추를 다 그린 뒤에 다음 행동을 고른다(맨 마지막)
