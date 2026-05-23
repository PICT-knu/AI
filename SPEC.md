# AI Server Specification

## 1. 개요

Python FastAPI 기반의 **복합 AI 플랫폼 서버**. 이력서 최적화·초안 생성·소재 추출·챗봇 교정·채용공고 매칭을 핵심 기능으로 하며, 다층 할루시네이션 방지 파이프라인을 내장한다. BE1(Spring)이 HTTP로 호출하는 내부 전용 서버이다.

- **메인 LLM**: Groq API (`llama-3.3-70b-versatile`) — 이력서 생성·교정·매칭
- **소재 추출 LLM**: OpenRouter (`anthropic/claude-opus-4`) — PDF 파싱 지원 필요로 별도 프로바이더 사용
- **오케스트레이션**: LangChain (직접 `ainvoke` 호출 방식, LangGraph 미사용)
- **BE1(Spring)** 이 HTTP로 호출 → AI 처리 후 JSON 반환

---

## 2. 핵심 파이프라인

### 2.1 이력서 자동 최적화 파이프라인 (Default Mode — Stateless)

- **엔드포인트**: `POST /resume/fix`
- **구현 파일**: `services/resume_service_v2.py` (`fix_resume_v2`)
- **Temperature**: 메인 LLM 0.6 / Planner(경량 LLM) 0.1 / 검증 LLM 0.0

실제 실행 파이프라인 (v2):

| 단계 | 설명 |
|------|------|
| **① 팩트 추출** | 소재에서 날짜·수치·고유명사를 추출해 `{F1: "삼성SDS", F2: "2023.03", ...}` 맵 생성 (경량 LLM) |
| **② 팩트 마스킹** | 소재 내 팩트 값을 `[F1]`, `[F2]` 기호로 치환 |
| **③ Planner** | 마스킹 소재 + 공고 분석 → 섹션 순서·강조점·문체 스타일 포함 이력서 구성안(JSON) 생성 (경량 LLM) |
| **④ Generator ×2** | JOB_FIT·ACHIEVEMENT 두 버전을 `asyncio.gather`로 병렬 생성 (메인 LLM). `[F숫자]` 기호 그대로 유지 |
| **⑤ 언마스킹** | 각 버전의 `[F1]` 기호를 원본 팩트 값으로 복원 |
| **⑤-a 팩트 검사** | Python으로 모든 팩트 값이 최종 텍스트에 존재하는지 확인 (LLM 호출 없음) |
| **⑤-b 날조 검사** | 검증 LLM으로 소재에 없는 내용이 추가됐는지 교차 판정 (버전별 독립 실행) |
| **재시도** | 검증 실패 시 이슈 명시 후 1회 재시도. 재시도도 비어있으면 1차 결과 반환 |
| **⑥ 스코어링** | 각 버전의 공고 키워드 커버리지를 LLM으로 0~100 정수 산출 |
| **⑦ 추천 결정** | `matching_score`가 높은 버전을 `recommended_type`으로 지정 |

- JOB_FIT: 공고 요구사항 직접 매핑, 직무 키워드 강조
- ACHIEVEMENT: 수치·성과 중심, 임팩트 있는 표현
- 응답: `ResumeFixResponse { generated_at, recommended_type, versions: [JOB_FIT, ACHIEVEMENT] }`
- 각 버전의 `body`는 `ResumeBody { about, experience: [...], skills: [...] }` JSON 구조
- 각 요청은 **무상태(stateless)**. 대화 이력 불필요.
- 최종 이력서 데이터는 AI 서버가 아닌 **백엔드 DB에서 영속 관리**.

### 2.2 챗봇 교정 모드 (Chatbot Mode — Session-based)

- **엔드포인트**: `POST /resume/chat`
- **구현 파일**: `services/resume_service.py` (`chat_resume`)
- **Temperature**: 0.6

- 사용자 추가 요청("특정 스타일로 고쳐줘" 등)을 실시간 반영.
- **응답**: `ResumeChatResponse { reason: str, suggested_body: ResumeBody }` — 수정 이유와 전체 이력서 본문 JSON 반환.
- **세션 단위 서버 상태** 유지: 세션별 대화 이력을 `InMemorySessionStore`에 보관.
  - BE1이 자체 관리하는 숫자 문자열 `session_id`(예: `"200"`)를 그대로 수신.
  - `session_id`가 없으면 서버가 UUID로 새 세션 생성.
  - AI 서버 자체는 세션 단위까지만 관리; 장기 이력은 백엔드 DB 책임.
- **Lazy Create (세션 자동 복원)**: 세션 만료 후 동일 `session_id` + `current_body` 재전송 시 `current_body` + `resume_materials`로 컨텍스트를 재구성하여 대화 맥락 복원.
- **컨텍스트 윈도우 초과 방지**: 히스토리 20개 초과 시 앞부분을 LLM으로 요약 후 최근 6개 메시지만 유지.
- **할루시네이션 검증**: 생성된 `suggested_body` 전체를 검증 LLM으로 소재 원문과 교차 검사. 경고 로그만 기록 (응답은 반환).

### 2.3 소재 추출 파이프라인 (Material Extraction — Stateless)

- **엔드포인트**: `POST /resume/pdf/extract`, `POST /resume/text/extract`, `POST /resume/manual/extract`
- **구현 파일**: `services/pdf_service.py`
- **LLM**: OpenRouter (`anthropic/claude-opus-4` 기본값) — PDF 파싱 지원을 위해 Groq 미사용
- **Temperature**: 0.1

| 엔드포인트 | 입력 | 가드 로직 | 반환 추가 필드 |
|---|---|---|---|
| `/pdf/extract` | PDF 파일 (multipart) | 없음 | — |
| `/text/extract` | 자유 텍스트 (JSON) | 있음 (회의록·피드백·코드 덤프 등 필터) | — |
| `/manual/extract` | 사용자 직접 입력 (JSON) | 없음 | `content` (원문 발췌) |

- OpenRouter `file-parser` 플러그인 + `response_format` JSON Schema 강제로 파싱 실패 없음.
- 소재 유형: `"EXPERIENCE"`, `"PROJECT"`, `"SKILL"`, `"EDUCATION"`, `"OTHER"`

### 2.4 이력서 초안 생성 (Generate — Stateless)

- **엔드포인트**: `POST /resume/generate` (v1), `POST /resume/generate-v2` (v2 파이프라인)
- **구현 파일**: `services/resume_service.py` (v1) / `services/resume_service_v2.py` (v2)
- v2는 2.1과 동일한 팩트 마스킹+Planner+Generator+Verifier 파이프라인 사용. Generator 프롬프트에 `user_profile` 추가.

### 2.5 채용공고 매칭 (Matching — Stateless)

- **엔드포인트**: `POST /match/top10`
- **구현 파일**: `services/matching_service.py`

3단계 파이프라인:

| 단계 | 방법 | 설명 |
|---|---|---|
| **① 사전 필터** | Python (0ms) | `avoidance_options` 키워드 + 자유 텍스트 + 지역 필터로 부적합 공고 제거 |
| **② 임베딩 유사도** | OpenRouter `text-embedding-3-small` | 소재 전체 vs 각 공고 코사인 유사도 → 상위 25개 추출 |
| **③ LLM 스코어링** | asyncio 병렬 처리 (temperature 0.1) | 10개씩 배치, 경력·기술스택·선호도 반영 0~100점 계산 |

- 지역 필터 결과 < 10이면 지역 필터 해제 후 전체 공고 대상으로 임베딩 재시도.

---

## 3. 파이프라인 구성 관리

- 파이프라인은 `services/` 내 Python 코드로 구현 (LangChain 직접 `ainvoke` 호출 방식, LangGraph 미사용).
- 변경 시 재배포 필요 (Git으로 이력 관리).
- 시스템 프롬프트는 코드 파일에 하드코딩. 수정 시 재배포 수반.
- Groq 호출: LangChain `ChatGroq` 클라이언트. OpenRouter 소재 추출: httpx 직접 호출.

> **미래 개선 포인트**: 프롬프트를 DB에 저장하면 재배포 없이 수정 가능. 현재는 단순성 우선.

---

## 4. LLM 프로바이더

### 4.1 현재 프로바이더

**Groq (기본 — 이력서 생성·교정·매칭)**
- 메인 모델: `llama-3.3-70b-versatile` (temperature 0.6)
- 경량 모델: `llama-3.3-70b-versatile` (Planner용, temperature 0.1 / `GROQ_LIGHT_MODEL`로 교체 가능)
- 검증 모델: `llama-3.1-8b-instant` (temperature 0.0 / `VERIFY_MODEL`로 교체 가능)
- LangChain `ChatGroq` 클라이언트 사용.
- 환경변수 `GROQ_API_KEY` 필수.

**OpenRouter (소재 추출·임베딩 전용)**
- 소재 추출: `anthropic/claude-opus-4` 기본값 — PDF `file-parser` 플러그인 지원 필요로 Groq 미사용
- 임베딩: `openai/text-embedding-3-small` — 매칭 파이프라인 2단계에서 사용
- LangChain `ChatOpenAI` (base_url 오버라이드) 또는 httpx 직접 호출.
- 환경변수 `OPENROUTER_API_KEY` 필수 (소재 추출·매칭 기능 사용 시).

### 4.2 클라이언트 함수 (`services/llm_client.py`)

| 함수 | 용도 | 기본 temperature |
|---|---|---|
| `get_llm_client(temperature)` | 이력서 생성·교정·매칭 스코어링 | 0.6 |
| `get_light_llm_client(temperature)` | Planner 등 창의성 불필요 단계 | 0.1 |

`LLM_PROVIDER` 환경변수로 `"groq"` / `"openrouter"` 전환. 미설정 시 `"groq"`.  
프로바이더 전환은 `services/llm_client.py` 하나만 수정하면 됨. 서비스 코드 변경 불필요.

### 4.3 오류 처리 및 폴백

- LLM 검증 실패: 이슈 명시 후 1회 재시도. 재시도도 실패 시 1차 결과 반환.
- 매칭 배치 실패: 해당 배치 건너뛰고 나머지 결과만 반환 (부분 성공 가능).

---

## 5. 스트리밍

- `stream=true` 쿼리 파라미터(또는 헤더)로 선택.
- 스트리밍: **SSE(Server-Sent Events)** 방식으로 토큰 단위 실시간 전달.
- 비스트리밍: 전체 응답 완성 후 JSON 반환.
- 스트리밍 중 연결 끊김 발생 시 이미 생성된 텍스트를 세션에 임시 저장(챗봇 모드) 또는 폐기(무상태 모드).

---

## 6. 외부 도구 / 에이전트 툴 호출

에이전트가 호출 가능한 도구:

| 도구 | 설명 |
|------|------|
| `internal_db_query` | 내부 PostgreSQL 등에 쿼리 실행 (읽기 전용 권장) |
| `internal_rest_api` | 사내 다른 마이크로서비스 HTTP 호출 |

- 도구 정의는 LangGraph 노드 또는 LangChain Tool로 선언.
- 도구 실행 결과는 LLM 컨텍스트에 삽입 후 다음 추론 단계 진행.
- 코드 실행·외부 SaaS 호출은 현재 범위 외.

---

## 7. RAG 파이프라인

### 7.1 설계 원칙: DB 직접 접근 없음

AI 서버는 **DB에 직접 접근하지 않는다.** 모든 데이터는 BE1(Spring 백엔드)이 조회하여 요청 페이로드에 포함해서 전달한다.

```
[사용자] → [BE1 (Spring)] → (DB 조회 후 materials 포함) → [AI 서버]
```

RAG는 벡터 검색 대신 **BE1이 전달한 `materials` 리스트를 컨텍스트로 직접 주입**하는 방식으로 구현한다.

### 7.2 할루시네이션 방지 목적

- LLM이 `materials`에 없는 내용을 지어내는 것을 방지하기 위해 RAG를 사용.
- 프롬프트에 **"제공된 materials 이외의 내용을 추가하지 말 것"** 을 명시.
- 코드 레벨 검증: LLM 응답의 `suggested` 텍스트가 `materials` 원문에서 유래했는지 대조 후 필터링.

### 7.3 요청 페이로드 구조

BE1이 AI 서버에 전달하는 materials 예시:

```json
{
  "resume_materials": [
    {
      "material_type": "EXPERIENCE",
      "content": "2023.03 ~ 현재, ABC회사, 백엔드 개발자, Java/Spring 기반 서비스 개발"
    },
    {
      "material_type": "PROJECT",
      "content": "실시간 알림 시스템 구축, Kafka 활용, DAU 10만 처리"
    },
    {
      "material_type": "SKILL",
      "content": "Java, Spring Boot, Kafka, PostgreSQL, Docker"
    }
  ],
  "job_post": {
    "description": "...",
    "experience_text": "...",
    "education_text": "...",
    "employment_type": "정규직"
  }
}
```

### 7.4 컨텍스트 주입 전략

1. BE1이 전달한 `resume_materials`를 `material_type`별로 그룹화.
2. JD(`job_post`)의 요구 역량과 각 material을 매칭 → 관련도 높은 순으로 정렬.
3. 토큰 예산 내에서 상위 materials를 시스템 프롬프트 컨텍스트 블록에 삽입.
4. LLM은 **주입된 컨텍스트 블록만** 참조해 이력서를 생성.

> **벡터 DB 불필요**: 검색·임베딩 인프라 없이 BE1의 DB 쿼리 결과를 그대로 활용.  
> 향후 materials 양이 토큰 한계를 초과할 경우 임베딩 기반 필터링 도입 검토.

---

## 8. 상태 관리

| 모드 | 상태 저장 위치 | 키 |
|------|--------------|-----|
| 이력서 생성·추출·매칭 | 없음 (stateless) | — |
| 챗봇 교정 | `InMemorySessionStore` (서버 프로세스 내) | `session_id` (BE1 숫자 문자열 또는 서버 생성 UUID) |
| 장기 이력/결과물 | 백엔드 DB (AI 서버 관할 외) | — |

- 세션 TTL: 기본 1시간 (`SESSION_TTL_SECONDS` 환경변수로 변경 가능).
- 마지막 요청 기준으로 TTL 갱신 (접근 시 자동 연장).
- 세션 만료 후 동일 `session_id` + `current_body` 재전송 시 컨텍스트 자동 복원 (lazy create).
- **현재 구현**: 인메모리 (`services/session_store.py` — `InMemorySessionStore`). 서버 재시작 시 세션 초기화.
- **향후**: `SessionStore` 추상 인터페이스로 Redis 교체 가능하도록 설계됨.

---

## 9. 인증 및 팀 식별

- **AI 서버 자체 인증 없음**: 네트워크 게이트웨이(API Gateway, 서비스 메시 등)에 위임.
- 팀/서비스 식별은 요청 헤더(`X-Team-Id`, `X-Service-Name` 등)로 전달.
  - 게이트웨이가 해당 헤더를 주입.
  - AI 서버는 이 헤더를 신뢰하고 로그·비용 추적에 활용.
- 내부 네트워크 격리로 외부 접근 차단 전제.

---

## 10. 관찰 가능성 (Observability)

### 10.1 로깅

| 항목 | 내용 |
|------|------|
| 요청/응답 로그 | `request_id`, `team_id`, `pipeline_id`, 프롬프트 전문, 응답 전문 |
| 개인정보 마스킹 | 이름·연락처 등 PII 필드는 마스킹 후 저장 (설정으로 레벨 조절) |
| 폴백/재시도 이벤트 | 폴백 발생 원인, 전환된 모델명, 재시도 횟수 |

### 10.2 메트릭

| 메트릭 | 설명 |
|--------|------|
| `ai_request_latency_ms` | 파이프라인별, 모델별 P50/P95/P99 지연 |
| `ai_token_usage_total` | 팀/파이프라인/모델별 토큰 소모량 (input/output 분리) |
| `ai_cost_usd_total` | 토큰 단가 기반 비용 추산 |
| `ai_error_rate` | 오류 유형별 비율 |
| `ai_fallback_count` | 폴백 발생 횟수 |

- Prometheus 형식으로 `/metrics` 엔드포인트 노출.
- 각 요청에 `request_id` 부여 (분산 추적 기반 마련).

---

## 11. API 설계

### 11.1 기본 규칙

- 인증 헤더: 없음 (게이트웨이 처리)
- 요청/응답 형식: JSON (스트리밍 시 `text/event-stream`)

### 11.2 주요 엔드포인트

```
GET  /health
  - 헬스체크 (liveness)
  - Response: { "status": "ok" }

POST /resume/fix
  - 이력서 자동 최적화 (v2 파이프라인, 무상태)
  - Body: { member_id?, job_posting_id?, resume_materials: [...], job_post: {...} }
  - Response: { generated_at, recommended_type, versions: [{ type, body: ResumeBody, matching_score, summary }] }
  - 항상 JOB_FIT·ACHIEVEMENT 2개 버전 반환

POST /resume/chat
  - 챗봇 교정 모드 (세션 기반)
  - Body: { session_id?: string, tailored_resume_id?, message: string, current_body?: ResumeBody, resume_materials: [...], job_post?: {...} }
  - Response: { reason: string, suggested_body: ResumeBody }
  - session_id는 BE1 숫자 문자열 그대로 수신. 없으면 UUID 신규 생성

POST /resume/generate
  - 1클릭 이력서 초안 생성 (무상태)
  - Body: { user_profile: {...}, resume_materials: [...], job_post: {...} }
  - Response: { generated_resume: "초안 전문" }

POST /resume/generate-v2
  - 1클릭 초안 생성 (v2 파이프라인, 실험용)
  - Body: 동일 /resume/generate

POST /resume/pdf/extract
  - PDF 이력서에서 소재 카드 추출 (multipart/form-data)
  - Body: file=<PDF 파일>
  - Response: { materials: [{ title, summary, material_type }] }
  - 실패 시 502

POST /resume/text/extract
  - Notion 텍스트에서 소재 카드 추출 (JSON)
  - Body: { text: "자유 형식 텍스트" }
  - Response: { materials: [{ title, summary, material_type }] }
  - 가드 로직 있음: 회의록·피드백·코드 덤프 등 필터
  - 실패 시 502

POST /resume/manual/extract
  - 수동 입력 텍스트에서 소재 카드 추출 (JSON)
  - Body: { text: "사용자 직접 입력" }
  - Response: { materials: [{ title, content, summary, material_type }] }
  - 가드 로직 없음 (입력 내용을 무조건 소재로 처리)
  - content(원문 발췌) + summary(요약) 둘 다 반환
  - 실패 시 502

POST /match/top10
  - 공고 TOP 10 추천 + 적합도 점수 (3단계 파이프라인)
  - Body: { resume_materials: [...], job_posts: [...], user_preferences?: {...} }
  - Response: { recommendations: [{ job_posting_id, job_id, match_score, reason_text }] }
```

### 11.3 응답 형식

**이력서 수정 — Default Mode (`/resume/fix`)**
```json
{
  "generated_at": "2026-05-22T10:30:00+00:00",
  "recommended_type": "JOB_FIT",
  "versions": [
    {
      "type": "JOB_FIT",
      "body": {
        "about": "자기소개 문단",
        "experience": [{ "company": "회사명", "period": "기간", "role": "직무", "description": "상세" }],
        "skills": ["Java", "Spring Boot"]
      },
      "matching_score": 88,
      "summary": "자기소개 요약"
    },
    {
      "type": "ACHIEVEMENT",
      "body": { "about": "...", "experience": [...], "skills": [...] },
      "matching_score": 82,
      "summary": "..."
    }
  ]
}
```

**이력서 수정 — Chatbot Mode (`/resume/chat`)**
```json
{
  "reason": "수정 이유 설명 (255자 이하)",
  "suggested_body": {
    "about": "수정된 자기소개",
    "experience": [{ "company": "회사명", "period": "기간", "role": "직무", "description": "상세" }],
    "skills": ["Java", "Spring Boot"]
  }
}
```

**매칭 AI**
```json
{
  "recommendations": [
    {
      "job_posting_id": 1,
      "job_id": null,
      "match_score": 87.50,
      "reason_text": "경력:90, 기술스택:80, 복지:75"
    }
  ]
}
```

> 관찰성 목적의 메타데이터(`request_id`, `usage`, `latency_ms`)는 응답 본문이 아닌 **응답 헤더** 또는 서버 내부 로그에만 기록. 클라이언트(BE1) API 계약 단순성 유지.

---

## 12. 프로젝트 구조

```
.
├── main.py                        # FastAPI 앱 진입점, 라우터 등록, /health
├── routers/
│   ├── __init__.py                # resume_router, matching_router export
│   ├── resume.py                  # /resume/* 엔드포인트 7개 정의
│   └── matching.py                # /match/top10 엔드포인트 정의
├── services/
│   ├── __init__.py                # 서비스 함수 일괄 export
│   ├── llm_client.py              # LLM 프로바이더 추상화 (get_llm_client, get_light_llm_client)
│   ├── session_store.py           # 챗봇 세션 인메모리 관리 (InMemorySessionStore, TTL 기반)
│   ├── resume_service.py          # chat_resume, generate_resume 구현
│   │                              # fix_resume는 resume_service_v2에 위임
│   ├── resume_service_v2.py       # 팩트 마스킹 + Planner + Generator + Verifier 파이프라인
│   │                              # fix_resume_v2, generate_resume_v2
│   ├── matching_service.py        # 3단계 매칭 파이프라인 (사전필터 → 임베딩 → LLM 스코어링)
│   └── pdf_service.py             # PDF·텍스트·수동입력 소재 추출 (OpenRouter httpx 직접 호출)
├── models/
│   ├── __init__.py                # 모든 Pydantic 모델 일괄 export
│   ├── resume.py                  # ResumeMaterial, JobPost, UserProfile, Fix/Chat/Generate 모델
│   ├── matching.py                # UserPreferences, MatchRequest, Recommendation, MatchResponse
│   └── pdf.py                     # MaterialType(Enum), ExtractedMaterial, ManualExtractedMaterial 등
└── utils/
    ├── __init__.py
    └── fact_check.py              # 할루시네이션 방지 유틸
                                   # build_context_block, llm_verify_against_materials
                                   # extract_fact_tokens, mask_materials, unmask_text, verify_facts_present
```

---

## 13. 기술 스택

| 범주 | 선택 | 비고 |
|------|------|------|
| 웹 프레임워크 | FastAPI | |
| 데이터 유효성 검사 | Pydantic v2 (완전한 타입 힌트) | |
| 메인 LLM | Groq API (`llama-3.3-70b-versatile`) | 이력서 생성·교정·매칭 |
| 소재 추출 LLM | OpenRouter (`anthropic/claude-opus-4`) | PDF·텍스트·수동입력 추출 |
| LLM SDK | `langchain-groq` (`ChatGroq`), `langchain-openai` (`ChatOpenAI`) | |
| HTTP 클라이언트 | `httpx` | OpenRouter 직접 호출 |
| 오케스트레이션 | LangChain (직접 ainvoke, LangGraph 미사용) | |
| 환경변수 | `python-dotenv` | |
| 세션 스토어 | `InMemorySessionStore` (현재) / Redis 교체 가능 | 챗봇 모드 |
| 메트릭 | `prometheus-fastapi-instrumentator` | |
| 로깅 | `structlog` (JSON 구조화) | |
| 테스트 | `pytest` + `pytest-asyncio` + `respx` (HTTP 목킹) | |
| 타입 검사 | `mypy` strict 모드 | |
| 린터 | `ruff` | |

### 환경변수 (.env)

| 변수명 | 필수 | 기본값 | 설명 |
|--------|------|--------|------|
| `GROQ_API_KEY` | **필수** | — | Groq API 키 (절대 코드에 직접 작성 금지) |
| `LLM_PROVIDER` | 선택 | `"groq"` | `"groq"` 또는 `"openrouter"` |
| `GROQ_MODEL` | 선택 | `"llama-3.3-70b-versatile"` | 메인 LLM 모델 |
| `GROQ_LIGHT_MODEL` | 선택 | GROQ_MODEL 값 | Planner용 경량 모델 (미설정 시 메인 모델과 동일) |
| `VERIFY_MODEL` | 선택 | `"llama-3.1-8b-instant"` | 검증 전용 LLM 모델 (Groq) |
| `OPENROUTER_API_KEY` | 선택* | — | OpenRouter API 키 (*소재 추출·매칭 임베딩 사용 시 필수) |
| `OPENROUTER_MODEL` | 선택 | `"anthropic/claude-opus-4"` | OpenRouter 메인 모델 |
| `OPENROUTER_LIGHT_MODEL` | 선택 | OPENROUTER_MODEL 값 | OpenRouter 경량 모델 |
| `PDF_EXTRACT_MODEL` | 선택 | OPENROUTER_MODEL 값 | PDF 추출 전용 모델 |
| `TEXT_EXTRACT_MODEL` | 선택 | PDF_EXTRACT_MODEL 값 | Notion 텍스트 추출 전용 모델 |
| `MANUAL_EXTRACT_MODEL` | 선택 | TEXT_EXTRACT_MODEL 값 | 수동 입력 추출 전용 모델 |
| `SESSION_TTL_SECONDS` | 선택 | `3600` | 챗봇 세션 유지 시간(초) |

> 프로바이더 전환은 `services/llm_client.py` 하나만 수정하면 됨. 나머지 서비스 코드는 변경 불필요.

---

## 14. 동시성 및 배포

- 예상 최대 동시 요청: **50 미만**
- 단일 인스턴스 `uvicorn`(또는 `uvicorn` workers) 로 충분.
- **개발 서버**: `uvicorn main:app --reload` (포트 8000)
- **가상환경 위치**: `../knu_python/.venv` — 실행 전 반드시 활성화
- **배포 환경 미확정**: Docker Compose(단일 서버) 또는 Kubernetes 중 추후 결정.
  - 컨테이너화는 기본 전제 (Dockerfile 작성).
  - 세션 스토어를 Redis로 전환 시 사이드카 또는 외부 관리형 서비스로 운영.

---

## 15. 테스트 전략

| 레벨 | 방식 | 대상 |
|------|------|------|
| 단위 테스트 | LLM 목킹 (`respx` 등) | 파이프라인 로직, 라우팅, 폴백, 요약 |
| 통합 테스트 | 실제 LLM API 호출 | 핵심 파이프라인 E2E, 스트리밍 동작 |
| 환경 분리 | `INTEGRATION_TEST=true` 환경변수로 실제 호출 테스트 게이팅 | CI에서 단위만, 주기적으로 통합 실행 |

---

## 16. 미확정 결정 사항 (Open Decisions)

| 항목 | 현황 | 결정 기준 |
|------|------|-----------|
| 배포 환경 | 미정 | 팀 인프라 현황에 따라 Docker Compose → K8s 마이그레이션 가능 |
| PII 마스킹 레벨 | 미정 | 법무/컴플라이언스 요구사항 확인 필요 |
| 세션 스토어 교체 | InMemorySessionStore (현재) | 운영 환경 안정화 후 Redis 전환 검토 |
| 프롬프트 버전 관리 | Git으로 관리 | 운영 중 빈번한 수정이 필요해지면 DB 저장으로 전환 검토 |
| LLM 프로바이더 전환 시점 | Groq 사용 중 | 성능·비용·기능 필요 시 `llm_client.py` 교체로 전환 |
