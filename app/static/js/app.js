// 대시보드 시작점. 2단계: 위 줄 상태와 01칸. 3단계: 02칸 자막 출처·자막 붙여넣기. 03은 선택한 영상만 따라 바뀐다.
import { initAnalysis } from './analysis.js';
import { initContext } from './context.js';
import { initDiscover } from './discover.js';
import { initFlow } from './flow.js';
import { initTopbar } from './topbar.js';

initTopbar();
initDiscover();
initAnalysis();
initContext();
initFlow();
