// 대시보드 시작점. 2단계: 위 줄 상태와 01칸. 3단계: 02칸 자막 출처·자막 붙여넣기.
// 6단계: 02칸 댓글 초안 글 상자와 규칙 검사. 5단계: 02칸 분석·AI 초안·승인(report.js).
// 03은 선택한 영상과 승인 여부를 따라 바뀐다.
// 7단계: 오늘 통계·03칸 설정·작업 기록(ops.js), 01칸 「댓글 단 영상」 표시.
// 8단계: 03칸 게시 작업(job.js) — 큰 버튼, 진행 단계, 승인·복사·확인, 위 줄 BROWSER.
// 9단계: 다음 행동 하나만 강조(next.js), 겹침 패널 SETTINGS·VIEW ALL(panels.js), 칸 높이 맞추기(layout.js).
import { initAnalysis } from './analysis.js';
import { initContext } from './context.js';
import { initDiscover } from './discover.js';
import { initDraft } from './draft.js';
import { initFlow } from './flow.js';
import { initJob } from './job.js';
import { initLayout } from './layout.js';
import { initNext } from './next.js';
import { initOps } from './ops.js';
import { initPanels } from './panels.js';
import { initReport } from './report.js';
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
initPanels();
initLayout();
initNext(); // 다른 칸이 단추를 다 그린 뒤에 다음 행동을 고른다(맨 마지막)
