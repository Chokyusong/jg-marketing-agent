---
description: 형식 검사와 테스트(scripts/verify.ps1)를 돌리고 결과를 보고한다
---

1. PowerShell에서 `.\scripts\verify.ps1`을 실행한다(ruff check → pytest -q). `$ARGUMENTS`가 있으면 pytest 인수로 넘긴다.
2. 추적 파일 전체 비밀값 검사도 돌린다: `.\.venv\Scripts\python.exe scripts\check_secrets.py --all`.
3. 결과를 그대로 보고한다: 각 단계 통과/실패, pytest 요약 줄(통과·건너뜀·실패 수), 건너뛴 테스트와 이유.
4. 실패하면 원인을 짚고 고칠 방법을 제안한다. 사용자가 고치라고 하기 전에는 테스트를 지우거나 건너뛰게 바꾸지 않는다.
