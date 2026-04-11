# CLAUDE.md

## Project Overview
PICT (Personalized Intelligent Career Tuning) — 맞춤형 취업 AI Agent 프로젝트의 AI 서버 레포.
국립공주대학교 SW중심대학사업 산학캡스톤디자인 (2026.03 ~ 2026.06).
이 레포는 이력서 수정 및 공고 매칭 AI 기능을 담당한다.

## Commands
- `uvicorn main:app --reload` — 개발 서버 실행 (포트 8000)
- `pip install -r requirements.txt --break-system-packages` — 의존성 설치
- 가상환경은 ../knu_python/.venv에 위치, 실행 전 반드시 활성화

## Tech Stack
- Python FastAPI — AI 서버 본체
- Groq API (llama-3.3-70b-versatile) — AI 모델
- LangChain / LangGraph — Agent 오케스트레이션
- Pydantic — 요청/응답 데이터 검증
- python-dotenv — 환경변수 관리

## Architecture
FastAPI 기반 AI 서버. BE1(Spring)이 HTTP로 호출하면 Groq API를 통해 AI 처리 후 JSON 반환.
AI 서버는 DB에 직접 접근하지 않으며, 모든 데이터는 BE1을 통해 주고받는다.

### AI 기능 구조
- 이력서 수정 AI (temperature 0.5~0.7): 디폴트 모드, 챗봇 교정 모드
- 매칭 AI (temperature 0.1~0.3): 공고 TOP 10 추천, 적합도 점수 계산

### Directory Structure
- `main.py` — FastAPI 앱 진입점, 라우터 등록
- `routers/` — 엔드포인트 정의 (resume.py, matching.py)
- `services/` — AI 로직 (groq 호출, 프롬프트 처리)
- `models/` — Pydantic 요청/응답 모델
- `utils/` — 팩트체크, 검증 유틸

## API 규칙
- 모든 엔드포인트는 async 함수로 작성
- 모든 AI 응답은 JSON 형식으로 반환
- 엔드포인트 네이밍: /resume/fix, /resume/chat, /match/top10

## 이력서 수정 반환 형식
### 디폴트 모드 (수정된 이력서 전문 반환)
```json
{
  "revised_resume": "수정된 이력서 전문"
}
```
### 챗봇 교정 모드
```json
{
  "changes": [
    {
      "original": "원본 텍스트",
      "suggested": "수정 텍스트",
      "reason": "수정 이유",
      "material_id": "사용한 소재 id"
    }
  ]
}
```
### 매칭 AI
```json
{
  "recommendations": [
    {
      "job_id": "공고 ID",
      "match_score": 87.50,
      "reason_text": "경력:90, 기술스택:80, 복지:75"
    }
  ]
}
```

## Hallucination 방지 규칙
- BE1이 전달한 resume_materials 배열을 시스템 프롬프트의 Context로 주입하여 할루시네이션을 방지한다.

## 매칭 AI에서 사용할 job_posts 필드
- description: 공고 전문 (메인 분석 대상)
- experience_text: 경력 조건
- education_text: 학력 조건
- employment_type: 고용 형태

## 환경변수 (.env)
- GROQ_API_KEY — Groq API 키 (절대 코드에 직접 작성 금지)
