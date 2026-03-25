# slack-bot TASKS

- [x] 봇 멘션 응답 테스트 (2026-03-25)
- [x] PM2로 운영 환경 배포 (ecosystem.config.js 기반) (2026-03-25)
- [x] Windows 작업 스케줄러에 PM2 등록 (로그인 시 자동 시작) (2026-03-25)
- [ ] 에러 로그 모니터링 설정
- [x] 프로젝트 구조 설계 (Plan.md 작성) (2026-03-24)
- [x] md_collector.py 구현 (2026-03-24)
- [x] github_collector.py 구현 (2026-03-24)
- [x] claude.py 구현 (2026-03-24)
- [x] block_kit.py 구현 (2026-03-24)
- [x] md_collector - 모든 .md 재귀 탐색 → TASKS.md 단일 파일만 읽도록 변경 (2026-03-25)
- [x] ecosystem.config.js - Windows 경로 수정 (venv/bin → venv/Scripts) (2026-03-25)
- [x] claude.py - 모델 변경 (claude-sonnet → claude-haiku-4-5-20251001) (2026-03-25)
- [x] claude.py - 브리핑/일반 질문 구분 시스템 프롬프트 작성 (2026-03-25)
- [x] briefing.py - 브리핑 키워드 감지 (is_briefing 플래그) (2026-03-25)
- [x] briefing.py - 사용자 질문 텍스트를 Claude 프롬프트에 전달 (2026-03-25)
- [x] block_kit.py - is_briefing=False 시 프로젝트 현황 섹션 제거 (2026-03-25)
- [x] briefing.py - 스킬 키워드 감지 시 CLAUDE.md 읽어 봇 소개 응답 (2026-03-25)
