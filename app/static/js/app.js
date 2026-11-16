// 대시보드 시작점. 2단계: 위 줄 상태와 01칸. 3단계: 02칸 자막 출처·자막 붙여넣기.
// 6단계: 02칸 댓글 초안 글 상자와 규칙 검사. 5단계: 02칸 분석·AI 초안·승인(report.js).
// 03은 선택한 영상과 승인 여부만 따라 바뀐다(실행은 8단계).
import { initAnalysis } from './analysis.js';
import { initContext } from './context.js';
import { initDiscover } from './discover.js';
import { initDraft } from './draft.js';
import { initFlow } from './flow.js';
import { initReport } from './report.js';
import { initTopbar } from './topbar.js';

initTopbar();
initDiscover();
initAnalysis();
initContext();
initDraft();
initReport();
initFlow();
