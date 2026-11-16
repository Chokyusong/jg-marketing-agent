// 대시보드 시작점. 2단계: 사이드바 상태와 ①칸만 연결한다. ②는 선택한 영상만 따라 바뀐다.
import { initAnalysis } from './analysis.js';
import { initDiscover } from './discover.js';
import { initSidebar } from './sidebar.js';

initSidebar();
initDiscover();
initAnalysis();
