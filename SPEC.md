# AI Server Specification

## 1. 개요

Python FastAPI 기반의 **복합 AI 플랫폼 서버**. 이력서 수정(Resume Tailoring)과 챗봇 교정 모드를 핵심 기능으로 하며, RAG 파이프라인·AI 에이전트·멀티 LLM 프로바이더 오케스트레이션을 지원한다. 복수의 내부 팀/서비스가 호출하는 내부 전용 서버이다.

---

## 2. 핵심 파이프라인

### 2.1 이력서 자동 생성 파이프라인 (Default Mode — Stateless)

| 단계 | 설명 |
|------|------|
| **1. Extraction** | 사용자 소재(PDF, Notion 링크 등)를 텍스트로 파싱 후 `resume_materials` 테이블의 `material_type`(경험·프로젝트·기술 등)에 따라 분류·저장 |
| **2. JD Matching** | `job_posts` 에서 채용 공고 요구 역량·기술스택 추출 → `resume_materials`와 비교해 최적 소재 선별 |
| **3. Filling & Tailoring** | 선별 소재를 기반으로 공고 최적화된 이력서 전문 자동 생성 |
| **4. Human-in-the-Loop** | AI 수정 제안을 `Original` vs `Suggested` 형식으로 반환 → 사용자 승인 시 `resume_suggestions` 상태 업데이트 |

- 각 요청은 **무상태(stateless)**. 대화 이력 불필요.
- 최종 이력서 데이터는 AI 서버가 아닌 **백엔드 DB에서 영속 관리**.

### 2.2 챗봇 교정 모드 (Chatbot Mode — Session-based)

- 사용자 추가 요청("특정 스타일로 고쳐줘" 등)을 실시간 반영.
- **세션 단위 서버 상태** 유지: 세션별 대화 이력을 서버(Redis 등)에 보관.
  - 클라이언트는 `session_id`만 전달.
  - AI 서버 자체는 세션 단위까지만 관리; 장기 이력은 백엔드 DB 책임.
- **컨텍스트 윈도우 초과 방지**: 토큰 예산 기반 요약(token-budget summarization).
  - 잔여 토큰이 임계값 이하로 떨어지면 이전 메시지를 자동 요약 후 컨텍스트에 포함.
  - 요약 전 원본은 세션 스토어에 보존.

---

## 3. 파이프라인 구성 관리

- 파이프라인 정의(단계, 사용 모델, 프롬프트 참조 등)는 **YAML/코드 파일에 정적 선언**.
- 런타임에 설정 파일을 로드하여 파이프라인 객체를 동적으로 조립.
- 변경 시 재배포 필요 (Git 이력로 변경 관리).
- 시스템 프롬프트는 같은 YAML/코드 파일에 하드코딩. 수정 시 재배포 수반.

> **미래 개선 포인트**: 프롬프트를 DB에 저장하면 재배포 없이 수정 가능. 현재는 단순성 우선.

---

## 4. LLM 프로바이더

### 4.1 지원 프로바이더

- Claude (Anthropic)
- OpenAI (GPT 계열)
- 로컬 모델(Ollama 등) — 선택적

### 4.2 라우팅 전략

- **파이프라인별 고정 모델**: 각 파이프라인 설정 파일에 사용 모델을 명시.
- 런타임 동적 라우팅 없음(비용/속도 기반 자동 선택 불필요).

### 4.3 오류 처리 및 폴백

| 오류 유형 | 동작 |
|-----------|------|
| 타임아웃 | 지수 백오프(exponential backoff) 자동 재시도 |
| Rate Limit (429) | 재시도 간격을 `Retry-After` 헤더 또는 고정 대기로 조절 |
| 유해 콘텐츠 거부 (400) | 폴백 모델로 전환 → 그래도 실패 시 에러 반환 |
| 프로바이더 장애 | 설정된 폴백 체인 순서로 다음 프로바이더 시도 |

- 폴백은 **클라이언트에 투명하게** 처리 (폴백 발생 여부는 로그에만 기록).
- 재시도/폴백 최대 횟수는 파이프라인 설정에서 지정.

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

- 도구 정의는 파이프라인 설정 파일에 선언.
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
      "material_type": "experience",
      "content": "2023.03 ~ 현재, ABC회사, 백엔드 개발자, Java/Spring 기반 서비스 개발"
    },
    {
      "material_type": "project",
      "content": "실시간 알림 시스템 구축, Kafka 활용, DAU 10만 처리"
    },
    {
      "material_type": "skill",
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
| 이력서 생성 (default) | 없음 (stateless) | — |
| 챗봇 교정 | Redis (세션 TTL 설정) | `session_id` |
| 장기 이력/결과물 | 백엔드 DB (AI 서버 관할 외) | — |

- Redis 세션 TTL: 기본 1시간 (설정으로 변경 가능).
- 세션 만료 시 클라이언트에 `410 Gone` 반환.

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

- Base path: `/api/v1`
- 인증 헤더: 없음 (게이트웨이 처리)
- 팀 식별 헤더: `X-Team-Id` (필수)
- 요청/응답 형식: JSON (스트리밍 시 `text/event-stream`)

### 11.2 주요 엔드포인트

```
POST   /api/v1/pipelines/{pipeline_id}/run
  - 파이프라인 실행 (비스트리밍)
  - Body: { input: {...}, session_id?: string }

POST   /api/v1/pipelines/{pipeline_id}/stream
  - 파이프라인 실행 (SSE 스트리밍)
  - Body: 동일

POST   /api/v1/sessions
  - 새 챗봇 세션 생성
  - Response: { session_id: string, expires_at: datetime }

DELETE /api/v1/sessions/{session_id}
  - 세션 명시적 종료

GET    /api/v1/pipelines
  - 사용 가능한 파이프라인 목록 조회

GET    /health
  - 헬스체크 (liveness/readiness)

GET    /metrics
  - Prometheus 메트릭
```

### 11.3 공통 응답 형식

```json
{
  "request_id": "uuid",
  "pipeline_id": "resume_tailoring",
  "data": { ... },
  "usage": {
    "model": "claude-3-5-sonnet",
    "input_tokens": 1200,
    "output_tokens": 800,
    "cost_usd": 0.0042
  },
  "latency_ms": 2340
}
```

---

## 12. 프로젝트 구조

```
app/
├── main.py                    # FastAPI 앱 진입점
├── config/
│   ├── settings.py            # 환경변수 기반 전역 설정 (Pydantic Settings)
│   └── pipelines/
│       ├── resume_tailoring.yaml
│       └── chatbot_correction.yaml
├── api/
│   └── v1/
│       ├── routes/
│       │   ├── pipelines.py
│       │   └── sessions.py
│       └── schemas/           # Pydantic v2 요청/응답 모델
├── core/
│   ├── pipeline/
│   │   ├── base.py            # 파이프라인 추상 기반 클래스
│   │   ├── loader.py          # YAML → 파이프라인 객체 조립
│   │   └── executor.py        # 단계별 실행, 스트리밍/비스트리밍 분기
│   ├── llm/
│   │   ├── base.py            # LLM 클라이언트 인터페이스
│   │   ├── anthropic.py
│   │   ├── openai.py
│   │   └── router.py          # 프로바이더 선택, 재시도, 폴백
│   ├── rag/
│   │   ├── embedder.py        # 임베딩 (교체 가능 인터페이스)
│   │   └── retriever.py       # 벡터 검색 (교체 가능 인터페이스)
│   ├── tools/
│   │   ├── base.py
│   │   ├── db_query.py
│   │   └── internal_api.py
│   ├── session/
│   │   └── redis_store.py     # 세션 상태 관리
│   └── context/
│       └── summarizer.py      # 토큰 예산 기반 요약
├── observability/
│   ├── logging.py             # 구조화 로깅 (JSON), PII 마스킹
│   └── metrics.py             # Prometheus 메트릭 정의
└── tests/
    ├── unit/                  # LLM 목킹, 파이프라인 로직 테스트
    └── integration/           # 실제 LLM 호출 E2E 테스트
```

---

## 13. 기술 스택

| 범주 | 선택 |
|------|------|
| 웹 프레임워크 | FastAPI |
| 데이터 유효성 검사 | Pydantic v2 (완전한 타입 힌트) |
| LLM SDK | `anthropic`, `openai` |
| 세션 스토어 | Redis (`redis-py` 비동기) |
| 메트릭 | `prometheus-fastapi-instrumentator` |
| 로깅 | `structlog` (JSON 구조화) |
| 테스트 | `pytest` + `pytest-asyncio` + `respx` (HTTP 목킹) |
| 타입 검사 | `mypy` strict 모드 |
| 린터 | `ruff` |

---

## 14. 동시성 및 배포

- 예상 최대 동시 요청: **50 미만**
- 단일 인스턴스 `uvicorn`(또는 `uvicorn` workers) 로 충분.
- **배포 환경 미확정**: Docker Compose(단일 서버) 또는 Kubernetes 중 추후 결정.
  - 컨테이너화는 기본 전제 (Dockerfile 작성).
  - Redis는 사이드카 또는 외부 관리형 서비스.

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
| 벡터 DB 선택 | 미정 | pgvector(인프라 단순) vs 전용 DB(성능) 트레이드오프 |
| 청킹 전략 | 미정 | 문서 유형(PDF, Notion)별 실험 필요 |
| 배포 환경 | 미정 | 팀 인프라 현황에 따라 Docker Compose → K8s 마이그레이션 가능 |
| PII 마스킹 레벨 | 미정 | 법무/컴플라이언스 요구사항 확인 필요 |
| Redis 세션 TTL | 기본 1시간 | 사용자 패턴 관찰 후 조정 |
| 프롬프트 버전 관리 | Git으로 관리 | 운영 중 빈번한 수정이 필요해지면 DB 저장으로 전환 검토 |
