# PICT AI Server — API 명세서

> **대상 독자**: BE1(Spring) 백엔드 팀  
> **Base URL**: `http://<ai-server-host>:8000`  
> **Content-Type**: `application/json` (별도 표기 없으면 요청/응답 모두)

---

## 공통 사항

### 공통 오류 응답

모든 엔드포인트는 아래 오류 형식을 반환할 수 있습니다.

#### 422 Unprocessable Entity — 요청 데이터 유효성 오류

FastAPI/Pydantic이 요청 Body의 필드 타입·필수값 등을 검증하지 못할 때 자동 반환합니다.

```json
{
  "detail": [
    {
      "loc": ["string", 0],
      "msg": "string",
      "type": "string",
      "input": "string",
      "ctx": {}
    }
  ]
}
```

| 필드 | 설명 |
|------|------|
| `detail` | 오류 목록. 복수 필드에서 오류가 날 경우 여러 개가 반환됨 |
| `detail[].loc` | 오류가 발생한 위치 경로. 첫 번째 값은 항상 `"body"`. 이후 값은 중첩된 필드명 또는 배열 인덱스(숫자) |
| `detail[].msg` | 사람이 읽을 수 있는 오류 메시지 (예: `"Field required"`, `"Input should be a valid string"`) |
| `detail[].input` | 검증에 실패한 실제 입력값 |
| `detail[].ctx` | 추가 오류 컨텍스트 (예: 허용 범위, 패턴 등). 오류 유형에 따라 비어있을 수 있음 |

> **loc 예시 해석**  
> `["body", "resume_materials", 0, "content"]` → 요청 Body의 `resume_materials` 배열 첫 번째 요소의 `content` 필드에서 오류 발생

#### 500 Internal Server Error — AI 처리 오류

```json
{
  "detail": "오류 메시지 문자열"
}
```

| 필드 | 설명 |
|------|------|
| `detail` | 서버 내부 예외 메시지. LLM 호출 실패, JSON 파싱 실패 등이 원인 |

---

## 공통 재사용 모델

### ExtractedMaterial

소재 추출 API(`/resume/pdf/extract`, `/resume/text/extract`)의 응답 단위.

```json
{
  "title": "삼성SDS 백엔드 개발",
  "summary": "Java/Spring Boot 기반 MSA 개발 담당. 월 500만 건 트래픽 처리 시스템 운영.",
  "material_type": "EXPERIENCE"
}
```

| 필드 | 설명 |
|------|------|
| `title` | 소재 제목 (30자 이내) |
| `summary` | 핵심 내용 2~4문장 요약. 없으면 `null` |
| `material_type` | 소재 유형. 값: `"EXPERIENCE"`, `"PROJECT"`, `"SKILL"`, `"EDUCATION"`, `"OTHER"` |

---

### ManualExtractedMaterial

수동 입력 전용 추출 API(`/resume/manual/extract`)의 응답 단위. `summary` 외에 원문 발췌(`content`)를 함께 반환.

```json
{
  "title": "삼성SDS 백엔드 개발",
  "content": "삼성SDS 클라우드 사업부에서 Java/Spring Boot로 백엔드 개발을 3년간 담당했습니다. 월 500만 건 트래픽을 처리하는 시스템을 설계·운영하였으며, Jenkins + Docker 기반 배포 자동화로 배포 시간을 70% 단축했습니다.",
  "summary": "Java/Spring Boot 기반 MSA 개발 담당. 월 500만 건 트래픽 처리 시스템 운영. 배포 자동화로 배포 시간 70% 단축.",
  "material_type": "EXPERIENCE"
}
```

| 필드 | 설명 |
|------|------|
| `title` | 소재 제목 (30자 이내) |
| `content` | 해당 소재에 해당하는 원문 발췌 |
| `summary` | 핵심 내용 2~4문장 요약. 없으면 `null` |
| `material_type` | 소재 유형. 값: `"EXPERIENCE"`, `"PROJECT"`, `"SKILL"`, `"EDUCATION"`, `"OTHER"` |

> **BE1 처리 안내**: DB에 `content`(원문)와 `summary`(요약) 둘 다 저장하세요.  
> `/resume/fix`, `/resume/chat`, `/resume/generate` 호출 시 `resume_materials[].content`에는 **`"{title} — {summary}"` 형식으로 합쳐서** 전달하세요.  
> 예: `"삼성SDS 백엔드 개발 — Java/Spring Boot 기반 MSA 개발 담당. 월 500만 건 트래픽 처리."`

---

### ResumeMaterial

이력서 소재 단위. BE1이 DB에서 조회한 소재를 그대로 배열로 전달합니다.

```json
{
  "material_type": "EXPERIENCE",
  "title": "삼성SDS 백엔드 개발",
  "content": "삼성SDS 백엔드 개발 — Java/Spring Boot 기반 MSA 개발 담당. 월 500만 건 트래픽 처리.",
  "summary": "Java/Spring Boot 기반 MSA 개발 담당. 월 500만 건 트래픽 처리.",
  "material_id": "mat-001"
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `material_type` | **필수** | 소재 유형. 권장값: `"EXPERIENCE"`, `"PROJECT"`, `"SKILL"`, `"EDUCATION"`, `"OTHER"`. 소재 추출 API 결과를 그대로 사용하면 자동으로 이 값이 들어옴 |
| `title` | 선택 | 소재 제목. 할루시네이션 방지 팩트 추출에 활용됨 |
| `content` | **필수** | 소재 내용 전문. AI가 이 텍스트만을 참조해 이력서를 생성하므로 정보가 충분해야 함 |
| `summary` | 선택 | 소재 요약. 팩트 검증에 활용됨 |
| `material_id` | 선택 | 소재의 고유 ID. `null`이면 AI가 출처 추적 불가 |

---

### JobPost

채용 공고 정보. AI가 이력서를 공고에 맞춰 최적화하는 데 사용합니다.

```json
{
  "job_posting_id": 42,
  "company_name": "삼성SDS",
  "title": "클라우드 백엔드 개발자",
  "job_id": "job-2024-001",
  "description": "클라우드 네이티브 백엔드 개발자 모집. MSA 아키텍처 설계 및 운영 경험 우대.",
  "experience_text": "3년 이상",
  "education_text": "대졸 이상",
  "employment_type": "정규직",
  "location": "서울 강남구"
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `job_posting_id` | 선택 | 채용공고 PK (BE1 DB). `/match/top10` 응답에서 이 값을 그대로 반환 |
| `company_name` | 선택 | 회사명. 이력서 생성 시 컨텍스트로 활용 |
| `title` | 선택 | 공고 제목. 이력서 생성 시 컨텍스트로 활용 |
| `job_id` | 선택 | 공고 ID (하위 호환). `job_posting_id`가 없을 때 사용 |
| `description` | **필수** | 공고 전문(JD). AI의 메인 분석 대상. 충분한 공고 내용을 포함해야 매칭 품질이 높아짐 |
| `experience_text` | **필수** | 공고의 경력 요건 (예: `"신입 가능"`, `"3년 이상"`) |
| `education_text` | **필수** | 공고의 학력 요건 (예: `"대졸 이상"`, `"무관"`) |
| `employment_type` | **필수** | 고용 형태 (예: `"정규직"`, `"계약직"`, `"인턴"`) |
| `location` | 선택 | 근무지 (예: `"서울 강남구"`, `"경기 수원시"`). `/match/top10`의 지역 필터에서 사용 |

> **권장사항**: 엔드포인트별로 필요한 필드가 다르지만, **항상 모든 필드를 전달**하는 것을 권장합니다. 구현이 단순해지고 AI 서버는 불필요한 필드를 자동으로 무시합니다.

---

### ResumeBody

이력서 본문 JSON 구조. `/resume/fix` 응답과 `/resume/chat` 응답에서 공통으로 사용합니다.

```json
{
  "about": "자기소개 문단",
  "experience": [
    {
      "company": "삼성SDS",
      "period": "2020.05 ~ 2023.08",
      "role": "백엔드 개발자",
      "description": "Java/Spring Boot 기반 MSA 설계 및 운영. 월 500만 건 트래픽 처리 시스템 개발."
    }
  ],
  "skills": ["Java", "Spring Boot", "Docker", "Kubernetes", "AWS"]
}
```

| 필드 | 설명 |
|------|------|
| `about` | 자기소개 문단. `null`일 수 있음 |
| `experience` | 경력/프로젝트 항목 목록 |
| `experience[].company` | 회사 또는 프로젝트명 |
| `experience[].period` | 근무 또는 진행 기간 |
| `experience[].role` | 직무 또는 역할 |
| `experience[].description` | 상세 업무 내용 |
| `skills` | 기술 스택 목록 |

---

## 전체 흐름 요약

BE1이 AI 서버를 활용하는 흐름은 크게 두 단계입니다.

**1단계 — 소재 추출 (사용자가 소재를 등록할 때)**

```
사용자 입력
  ├─ PDF 업로드     → POST /resume/pdf/extract    → title + summary 반환 → DB 저장
  ├─ Notion 연동    → POST /resume/text/extract   → title + summary 반환 → DB 저장
  └─ 직접 입력      → POST /resume/manual/extract → title + content + summary 반환 → DB 저장
```

**2단계 — AI 서버 호출 (이력서/매칭 기능 사용 시)**

```
DB에서 소재 조회 ("{title} — {summary}" → content 매핑)
  ├─ 이력서 자동 최적화   → POST /resume/fix
  ├─ 이력서 초안 생성     → POST /resume/generate  (+ user_profile)
  ├─ 챗봇 교정            → POST /resume/chat       (+ session_id, current_body)
  └─ 공고 매칭            → POST /match/top10       (+ job_posts, user_preferences)
```

> **소재 매핑 규칙**: 2단계 호출 시 `resume_materials[].content`에는 `"{title} — {summary}"` 형식으로 합쳐서 전달하세요.  
> 예: `"삼성SDS 백엔드 개발 — Java/Spring Boot 기반 MSA 개발 담당. 월 500만 건 트래픽 처리."`

---

## 엔드포인트

---

### `GET /health`

서버 생존 확인(Liveness Check)용 헬스체크.

**요청**: Body 없음

**응답 200 OK**

```json
{
  "additionalProp1": {}
}
```

---

### `POST /resume/fix`

**이력서 자동 최적화 (Default Mode, 무상태)**

사용자의 소재들을 기반으로 채용 공고에 최적화된 이력서를 **JOB_FIT**, **ACHIEVEMENT** 두 버전으로 자동 생성합니다.  
세션 없이 요청 1회로 완결됩니다.

> 이력서 소재(resume_materials)만 있으면 됩니다.

> ⚠️ **BE1 처리 사항**: 사용자 프로필의 학력·경력 정보를 별도 소재 카드로 변환해서 `resume_materials`에 포함시켜 전달하세요.  
> 예: `{ "material_type": "EDUCATION", "content": "국립공주대학교 컴퓨터공학과 2022~2026 졸업예정", "material_id": "edu-001" }`

#### 요청 Body

```json
{
  "member_id": 101,
  "job_posting_id": 42,
  "resume_materials": [
    {
      "material_type": "EXPERIENCE",
      "title": "삼성SDS 백엔드 개발",
      "content": "삼성SDS 클라우드 사업부 백엔드 개발 (2020.05~2023.08). Java/Spring Boot 기반 마이크로서비스 설계 및 운영. 월 500만 건 트래픽 처리 시스템 개발.",
      "material_id": "mat-001"
    },
    {
      "material_type": "PROJECT",
      "title": "배포 자동화 파이프라인 구축",
      "content": "사내 배포 자동화 파이프라인 구축 (2022.01~2022.06). Jenkins + Docker + Kubernetes 활용. 배포 시간 70% 단축.",
      "material_id": "mat-002"
    },
    {
      "material_type": "SKILL",
      "title": "기술스택",
      "content": "Java, Spring Boot, Python, Kubernetes, Docker, MySQL, Redis, AWS",
      "material_id": "mat-003"
    },
    {
      "material_type": "EDUCATION",
      "title": "국립공주대학교 컴퓨터공학과",
      "content": "국립공주대학교 컴퓨터공학과 2018.03~2022.02 졸업",
      "material_id": "mat-edu"
    }
  ],
  "job_post": {
    "job_posting_id": 42,
    "company_name": "삼성SDS",
    "title": "클라우드 백엔드 개발자",
    "description": "클라우드 네이티브 백엔드 개발자 모집. MSA 아키텍처 설계 및 운영 경험 우대.",
    "experience_text": "3년 이상",
    "education_text": "대졸 이상",
    "employment_type": "정규직",
    "location": "서울 강남구"
  }
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `member_id` | 선택 | 회원 PK (BE1 DB). AI 서버는 저장하지 않음, 로그 추적용 |
| `job_posting_id` | 선택 | 공고 PK (BE1 DB). AI 서버는 저장하지 않음, 로그 추적용 |
| `resume_materials` | **필수** | 이력서 소재 목록. 1개 이상 필요 |
| `job_post` | **필수** | 타겟 채용 공고. AI가 이 공고에 맞춰 이력서를 조정함 |

#### 응답 200 OK

```json
{
  "generated_at": "2026-05-22T10:30:00+00:00",
  "recommended_type": "JOB_FIT",
  "versions": [
    {
      "type": "JOB_FIT",
      "body": {
        "about": "MSA 설계 및 운영 경험을 바탕으로 클라우드 네이티브 백엔드 개발에 기여하겠습니다.",
        "experience": [
          {
            "company": "삼성SDS",
            "period": "2020.05 ~ 2023.08",
            "role": "백엔드 개발자",
            "description": "Java/Spring Boot 기반 MSA 설계 및 운영. 월 500만 건 트래픽 처리 시스템 개발. Jenkins+Docker+Kubernetes 배포 파이프라인 구축으로 배포 시간 70% 단축."
          }
        ],
        "skills": ["Java", "Spring Boot", "Kubernetes", "Docker", "MySQL", "Redis", "AWS"]
      },
      "matching_score": 88,
      "summary": "MSA 설계 및 운영 경험을 바탕으로 클라우드 네이티브 백엔드 개발에 기여하겠습니다."
    },
    {
      "type": "ACHIEVEMENT",
      "body": {
        "about": "월 500만 건 트래픽 처리 시스템 설계, 배포 자동화로 배포 시간 70% 단축 등 수치화된 성과를 보유한 백엔드 개발자입니다.",
        "experience": [
          {
            "company": "삼성SDS",
            "period": "2020.05 ~ 2023.08",
            "role": "백엔드 개발자",
            "description": "월 500만 건 트래픽 처리 시스템 설계·운영. Jenkins+Docker+Kubernetes 도입으로 배포 시간 70% 단축. 마이크로서비스 7개 모듈 설계 리드."
          }
        ],
        "skills": ["Java", "Spring Boot", "Kubernetes", "Docker", "MySQL", "Redis", "AWS"]
      },
      "matching_score": 82,
      "summary": "월 500만 건 트래픽 처리 시스템 설계, 배포 자동화로 배포 시간 70% 단축 등 수치화된 성과를 보유한 백엔드 개발자입니다."
    }
  ]
}
```

| 필드 | 설명 |
|------|------|
| `generated_at` | 생성 시각 (ISO 8601) |
| `recommended_type` | AI 추천 버전. `"JOB_FIT"` 또는 `"ACHIEVEMENT"`. `matching_score`가 높은 버전 |
| `versions` | 생성된 이력서 버전 목록. 항상 2개 (JOB_FIT, ACHIEVEMENT) |
| `versions[].type` | 버전 유형: `"JOB_FIT"` (공고 키워드 매핑 최적화) 또는 `"ACHIEVEMENT"` (수치/성과 강조) |
| `versions[].body` | 이력서 본문 JSON (ResumeBody 구조) |
| `versions[].matching_score` | 공고 키워드 대비 커버리지 점수 (0~100 정수). AI가 산출 |
| `versions[].summary` | 이력서 자기소개 요약 (BE1 미리보기용) |

**버전 설명**

| 버전 | 설명 |
|------|------|
| `JOB_FIT` | 공고 요구사항을 직접 매핑하고 직무 키워드를 강조. 채용 담당자가 JD 체크리스트를 보듯 읽을 수 있도록 구성 |
| `ACHIEVEMENT` | 수치와 성과를 중심으로 임팩트 있는 표현. 구체적인 수치(%, 건수, 규모)를 최대한 활용 |

#### 처리 흐름

1. 소재에서 팩트 토큰 추출 → 소재 마스킹 (할루시네이션 방지)
2. Planner LLM이 섹션 구성·강조점·문체 계획 수립
3. JOB_FIT · ACHIEVEMENT 두 버전을 병렬(asyncio.gather) 생성
4. 각 버전: 언마스킹 → 팩트 검증 + LLM 할루시네이션 검증 → 실패 시 1회 재시도
5. 각 버전의 `matching_score` LLM 산출 (0~100)
6. 높은 점수 버전을 `recommended_type`으로 지정

---

### `POST /resume/chat`

**이력서 챗봇 교정 모드 (Chatbot Mode, 세션 기반)**

사용자가 자연어로 수정 요청을 보내면 AI가 수정된 이력서 본문(`suggested_body`)과 수정 이유(`reason`)를 반환합니다.  
세션을 통해 대화 맥락이 유지됩니다.

#### 요청 Body

```json
{
  "session_id": "200",
  "tailored_resume_id": 15,
  "message": "자기소개를 더 간결하게 수정해줘",
  "current_body": {
    "about": "저는 백엔드 개발자로서 다양한 경험을 보유하고 있으며...",
    "experience": [
      {
        "company": "삼성SDS",
        "period": "2020.05 ~ 2023.08",
        "role": "백엔드 개발자",
        "description": "Java/Spring Boot 기반 MSA 개발."
      }
    ],
    "skills": ["Java", "Spring Boot", "Docker"]
  },
  "resume_materials": [
    {
      "material_type": "EXPERIENCE",
      "title": "삼성SDS 백엔드 개발",
      "content": "Java/Spring Boot 기반 MSA 개발 담당. 월 500만 건 트래픽 처리 시스템 운영.",
      "material_id": "mat-001"
    },
    {
      "material_type": "SKILL",
      "title": "기술스택",
      "content": "Java, Spring Boot, Python, Docker, Kubernetes, AWS",
      "material_id": "mat-002"
    }
  ],
  "job_post": {
    "job_posting_id": 42,
    "description": "클라우드 네이티브 백엔드 개발자 모집. MSA 아키텍처 설계 및 운영 경험 우대.",
    "experience_text": "3년 이상",
    "education_text": "대졸 이상",
    "employment_type": "정규직",
    "location": "서울 강남구"
  }
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `session_id` | 선택 | 세션 식별자. **BE1이 관리하는 숫자 문자열(예: `"200"`)을 그대로 전달.** `null` 또는 생략 시 AI 서버가 UUID로 새 세션 생성. 세션 만료 후 동일 `session_id` 재전송 시 `current_body`로 컨텍스트를 재구성하여 자동 복원 |
| `tailored_resume_id` | 선택 | tailored_resume PK (BE1 DB). AI 서버는 저장하지 않음 |
| `message` | **필수** | 사용자의 수정 요청 자연어 메시지 |
| `current_body` | 선택 | 현재 이력서 본문 (ResumeBody 구조). 세션이 만료된 경우 이 값으로 컨텍스트를 복원함. **세션 만료에 대비해 항상 전달을 권장** |
| `resume_materials` | **필수** | 현재 이력서 소재 목록. 매 요청마다 최신 소재를 전달. 할루시네이션 검증에 사용 |
| `job_post` | 선택 | 타겟 공고. `null`이면 공고 최적화 없이 소재 기반으로만 수정 |

#### 응답 200 OK

```json
{
  "reason": "자기소개가 너무 길어 핵심 역량이 묻혔습니다. MSA 경험과 트래픽 처리 수치를 앞세워 간결하게 수정했습니다.",
  "suggested_body": {
    "about": "MSA 설계와 월 500만 건 트래픽 처리 경험을 보유한 백엔드 개발자입니다.",
    "experience": [
      {
        "company": "삼성SDS",
        "period": "2020.05 ~ 2023.08",
        "role": "백엔드 개발자",
        "description": "Java/Spring Boot 기반 MSA 설계 및 운영. 월 500만 건 트래픽 처리 시스템 개발."
      }
    ],
    "skills": ["Java", "Spring Boot", "Docker", "Kubernetes", "AWS"]
  }
}
```

| 필드 | 설명 |
|------|------|
| `reason` | 수정 이유 설명 (255자 이하). BE1 DB 컬럼 길이 제한에 맞춰 자동 절사됨 |
| `suggested_body` | AI가 제안하는 수정된 이력서 본문 (ResumeBody 구조). BE1이 받아서 tailored_resume에 저장 |

#### 세션 관리

- 세션 TTL: **1시간** (마지막 요청 기준으로 갱신)
- 세션 만료 후 `session_id` + `current_body` 재전송 시 `current_body` + `resume_materials`로 컨텍스트를 자동 복원
- `current_body` 없이 만료된 세션을 재전송하면 소재(`resume_materials`)만으로 컨텍스트 재구성
- 대화 이력이 20개 메시지를 초과하면 서버가 자동으로 이전 내용을 요약 압축 (클라이언트 투명)

---

### `POST /resume/generate`

**원클릭 이력서 초안 생성 (이력서 없는 신규 사용자용, 무상태)**

기본 프로필 + 소재만으로 이력서 초안을 처음부터 생성합니다.  
기존 이력서가 없는 사용자에게 사용하세요.

> `/resume/fix`와의 차이: `fix`는 기존 소재를 다듬어 2개 버전을 반환, `generate`는 처음부터 초안(JOB_FIT 단일 버전)을 JSON 문자열로 반환.

#### 요청 Body

```json
{
  "user_profile": {
    "career_level": "신입",
    "degree_type": "4년제",
    "graduation_status": "졸업예정",
    "school_name": "국립공주대학교",
    "major": "컴퓨터공학",
    "enrollment_year": "2022",
    "graduation_year": "2026"
  },
  "resume_materials": [
    {
      "material_type": "PROJECT",
      "title": "PICT 취업 AI 서비스",
      "content": "PICT 취업 AI 서비스 개발 (2025.03~2025.06). FastAPI + LangChain 기반 이력서 자동 최적화 및 공고 매칭 서비스 구현.",
      "material_id": "mat-001"
    },
    {
      "material_type": "SKILL",
      "title": "기술스택",
      "content": "Python, FastAPI, LangChain, Java, Spring Boot, MySQL",
      "material_id": "mat-002"
    }
  ],
  "job_post": {
    "job_posting_id": 10,
    "description": "AI/백엔드 신입 개발자 모집. Python 또는 Java 사용 경험 보유자 우대.",
    "experience_text": "신입 가능",
    "education_text": "대졸 이상",
    "employment_type": "정규직",
    "location": "경기 성남시"
  }
}
```

**UserProfile 필드**

| 필드 | 필수 | 설명 |
|------|------|------|
| `career_level` | 선택 | 경력 단계. 예: `"신입"`, `"1-3년"`, `"3-5년"` |
| `degree_type` | 선택 | 대학 유형. 예: `"4년제"`, `"2/3년제"`, `"대학원"` |
| `graduation_status` | 선택 | 졸업 여부. 예: `"졸업"`, `"재학중"`, `"졸업예정"` |
| `school_name` | 선택 | 학교명. 예: `"국립공주대학교"` |
| `major` | 선택 | 전공. 예: `"컴퓨터공학"` |
| `enrollment_year` | 선택 | 입학년도. 예: `"2022"` |
| `graduation_year` | 선택 | 졸업(예정)년도. 예: `"2026"` |

> 모든 `user_profile` 필드는 선택 항목입니다. 값이 없으면 빈 문자열(`""`)로 전달하거나 생략 가능.

**요청 Body 필드**

| 필드 | 필수 | 설명 |
|------|------|------|
| `user_profile` | **필수** | 사용자 기본 프로필 (학력, 경력 단계 등). 이력서 헤더 및 자기소개 섹션에 반영됨 |
| `resume_materials` | **필수** | 이력서 소재 목록. 빈 배열 가능하나 1개 이상 권장 |
| `job_post` | **필수** | 타겟 채용 공고. 초안 방향성을 결정함 |

#### 응답 200 OK

```json
{
  "generated_resume": "{\"about\": \"...\", \"experience\": [...], \"skills\": [...]}"
}
```

| 필드 | 설명 |
|------|------|
| `generated_resume` | AI가 처음부터 생성한 이력서 초안. ResumeBody JSON 구조를 문자열로 직렬화한 값. 자기소개, 경험/프로젝트, 기술 스택 섹션 포함 |

---

### `POST /resume/pdf/extract`

**PDF 이력서에서 소재 추출**

PDF 파일을 업로드하면 소재 카드 목록을 반환합니다.  
요청은 JSON이 아닌 `multipart/form-data` 형식입니다.

#### 요청

| 파라미터 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `file` | `UploadFile` (form-data) | **필수** | 이력서 PDF 파일 |

#### 응답 200 OK

```json
{
  "materials": [
    {
      "title": "삼성SDS 백엔드 개발",
      "summary": "Java/Spring Boot 기반 MSA 개발 담당. 월 500만 건 트래픽 처리 시스템 운영.",
      "material_type": "EXPERIENCE"
    },
    {
      "title": "기술스택",
      "summary": "Java, Spring Boot, Python, Docker, Kubernetes, AWS",
      "material_type": "SKILL"
    }
  ]
}
```

| 필드 | 설명 |
|------|------|
| `materials` | 추출된 소재 카드 목록. PDF에 소재가 없으면 빈 배열 반환 |
| `materials[].title` | 소재 제목 (30자 이내) |
| `materials[].summary` | AI가 생성한 2~4문장 요약. `null`일 수 있음 |
| `materials[].material_type` | 소재 유형: `"EXPERIENCE"`, `"PROJECT"`, `"SKILL"`, `"EDUCATION"`, `"OTHER"` |

> AI 처리 실패 시 `502` 반환 (외부 AI 서비스 오류).

---

### `POST /resume/text/extract`

**Notion 텍스트에서 소재 추출**

Notion 페이지 본문 등 자유 형식 텍스트를 소재 카드로 변환합니다.  
회의록, 받은 피드백, 코드 덤프 등 본인 작업으로 단정할 수 없는 내용은 자동으로 걸러집니다.

#### 요청 Body

```json
{
  "text": "Notion 페이지 본문 전문"
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `text` | **필수** | Notion 페이지 본문 등 자유 형식 텍스트. 빈 문자열이면 LLM 호출 없이 빈 배열 반환 |

#### 응답 200 OK

`/resume/pdf/extract`와 동일한 형식 반환.

```json
{
  "materials": [
    {
      "title": "오픈소스 기여 — LangChain PR",
      "summary": "LangChain 라이브러리에 한국어 토크나이저 지원 PR 기여. 코드 리뷰 반영 후 머지.",
      "material_type": "PROJECT"
    }
  ]
}
```

> AI 처리 실패 시 `502` 반환. 빈/공백 텍스트는 `200 + 빈 materials` 반환.

---

### `POST /resume/manual/extract`

**수동 입력 텍스트에서 소재 추출**

사용자가 직접 입력한 텍스트를 소재 카드로 변환합니다.  
`/resume/text/extract`(Notion용)와 달리 가드 로직 없이 입력 내용을 무조건 소재로 처리하며,  
원문 발췌(`content`)와 요약(`summary`)을 함께 반환합니다.

#### 요청 Body

```json
{
  "text": "삼성SDS 클라우드 사업부에서 Java/Spring Boot로 백엔드 개발을 3년간 담당했습니다. 월 500만 건 트래픽을 처리하는 시스템을 설계·운영하였으며, Jenkins + Docker 기반 배포 자동화로 배포 시간을 70% 단축했습니다."
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `text` | **필수** | 사용자가 직접 입력한 이력서 소재 텍스트. 여러 소재가 섞여 있어도 자동 분리됨 |

#### 응답 200 OK

```json
{
  "materials": [
    {
      "title": "삼성SDS 백엔드 개발",
      "content": "삼성SDS 클라우드 사업부에서 Java/Spring Boot로 백엔드 개발을 3년간 담당했습니다. 월 500만 건 트래픽을 처리하는 시스템을 설계·운영하였으며, Jenkins + Docker 기반 배포 자동화로 배포 시간을 70% 단축했습니다.",
      "summary": "Java/Spring Boot 기반 MSA 개발 담당. 월 500만 건 트래픽 처리 시스템 운영. 배포 자동화로 배포 시간 70% 단축.",
      "material_type": "EXPERIENCE"
    }
  ]
}
```

| 필드 | 설명 |
|------|------|
| `materials` | 추출된 소재 카드 목록. 빈 텍스트 입력 시 빈 배열 반환 |
| `materials[].content` | 해당 소재에 해당하는 원문 발췌 |
| `materials[].summary` | AI가 생성한 2~4문장 요약. `null`일 수 있음 |
| `materials[].material_type` | 소재 유형: `"EXPERIENCE"`, `"PROJECT"`, `"SKILL"`, `"EDUCATION"`, `"OTHER"` |

#### PDF·NOTION과의 차이

| | `/resume/pdf/extract` | `/resume/text/extract` | `/resume/manual/extract` |
|---|---|---|---|
| 입력 | PDF 파일 | Notion 텍스트 | 사용자 직접 입력 |
| 가드 로직 | 없음 | 있음 (회의록 등 필터) | 없음 |
| 원문 반환 | ❌ | ❌ | ✅ (`content`) |
| 요약 반환 | ✅ | ✅ | ✅ (`summary`) |

---

### `POST /match/top10`

**채용 공고 TOP 10 추천 + 적합도 점수 계산**

사용자 이력서 소재와 여러 채용 공고를 비교해 상위 10개를 선별하고 점수를 반환합니다.

#### 요청 Body

```json
{
  "resume_materials": [
    {
      "material_type": "EXPERIENCE",
      "title": "삼성SDS 백엔드 개발",
      "content": "삼성SDS 클라우드 사업부 백엔드 개발 (2020.05~2023.08). Java/Spring Boot 기반 마이크로서비스 개발.",
      "material_id": "mat-001"
    }
  ],
  "job_posts": [
    {
      "job_posting_id": 1,
      "description": "백엔드 개발자 모집. Java/Spring 경험 우대.",
      "experience_text": "3년 이상",
      "education_text": "대졸 이상",
      "employment_type": "정규직",
      "location": "서울 강남구"
    }
  ],
  "user_preferences": {
    "avoidance_options": ["야근", "주말근무"],
    "avoidance_cert_text": "",
    "avoidance_skill_text": "",
    "preferred_locations": ["서울", "경기"],
    "experience_level": "경력",
    "preferred_job_rank": "대리",
    "preferred_company_sizes": ["대기업", "중견기업"],
    "preferred_benefits": ["재택근무", "유연근무"]
  }
}
```

**user_preferences 필드**

| 필드 | 필수 | 설명 |
|------|------|------|
| `avoidance_options` | 선택 | 기피 조건 키워드 목록. 허용값: `"야근"`, `"주말근무"`, `"교대근무"`, `"해외출장"`, `"잦은출장"` |
| `avoidance_cert_text` | 선택 | 기피할 자격증 요구 조건 자유 텍스트 (예: `"정보처리기사 필수"`) |
| `avoidance_skill_text` | 선택 | 기피할 기술 요구 조건 자유 텍스트 (예: `"COBOL"`) |
| `preferred_locations` | 선택 | 선호 근무 지역 목록 (예: `["서울", "경기"]`) |
| `experience_level` | 선택 | 경력 단계 (예: `"신입"`, `"경력"`) |
| `preferred_job_rank` | 선택 | 선호 직급 (예: `"사원"`, `"대리"`, `"과장"`) |
| `preferred_company_sizes` | 선택 | 선호 기업 규모 목록 (예: `["대기업", "중견기업", "스타트업"]`) |
| `preferred_benefits` | 선택 | 선호 복지 목록 (예: `["재택근무", "유연근무", "스톡옵션"]`) |

> `user_preferences` 전체 생략 또는 빈 객체(`{}`) 전달 시 선호도 필터 없이 소재 기반 점수만 계산합니다.

**요청 Body 필드**

| 필드 | 필수 | 설명 |
|------|------|------|
| `resume_materials` | **필수** | 사용자 이력서 소재 목록. 적합도 점수 계산의 기준이 됨 |
| `job_posts` | **필수** | 점수를 계산할 채용 공고 목록. 제한 없음. 내부적으로 배치 처리 |
| `job_posts[].job_posting_id` | **사실상 필수** | 공고 PK. 응답의 `recommendations[].job_posting_id`에 그대로 반환됨 |
| `user_preferences` | 선택 | 사용자 선호도 및 기피 조건. 생략 시 선호도 필터 없이 처리 |

#### 응답 200 OK

```json
{
  "recommendations": [
    {
      "job_posting_id": 1,
      "job_id": null,
      "match_score": 87.5,
      "reason_text": "경력:90, 기술스택:80, 복지:75"
    }
  ]
}
```

| 필드 | 설명 |
|------|------|
| `recommendations` | 상위 10개 공고 목록. `match_score` 내림차순 정렬. 입력 공고가 10개 미만이면 그만큼만 반환 |
| `recommendations[].job_posting_id` | 요청 시 전달한 공고의 `job_posting_id`. `null`이면 해당 공고에 `job_posting_id`가 없었음 |
| `recommendations[].job_id` | 하위 호환용. `job_posting_id` 사용 권장 |
| `recommendations[].match_score` | 적합도 점수. 범위: `0.0 ~ 100.0`. 소수점 2자리. 점수가 높을수록 적합 |
| `recommendations[].reason_text` | 점수 산정 근거 요약. 형식 예시: `"경력:90, 기술스택:80, 복지:75"`. 사용자에게 그대로 표시 가능 |

#### 처리 흐름

1. `user_preferences.avoidance_options` + `preferred_locations` 기준으로 기피 공고 사전 제거
2. 임베딩 유사도 기반 상위 25개 후보 추출 (temperature: 0.0)
3. 후보 공고를 LLM으로 병렬 점수 계산 (temperature: 0.1 — 일관성 최우선)
4. 점수 내림차순 정렬 후 상위 10개 반환
5. 특정 공고 처리 실패 시 해당 공고는 건너뛰고 나머지 결과만 반환 (부분 성공 가능)

---

## 상태 코드 요약

| 코드 | 설명 | 발생 시점 |
|------|------|-----------|
| `200 OK` | 성공 | 정상 처리 완료 |
| `422 Unprocessable Entity` | 요청 유효성 오류 | 필드 누락, 타입 불일치 등 |
| `500 Internal Server Error` | 서버 오류 | LLM 호출 실패, 파싱 오류 등 |
| `502 Bad Gateway` | 외부 AI 서비스 오류 | 소재 추출 엔드포인트(`/pdf/extract`, `/text/extract`, `/manual/extract`)에서 OpenRouter 호출 실패 시 |

---

## 엔드포인트 요약

| 메서드 | 경로 | 기능 | 상태 |
|--------|------|------|------|
| `GET` | `/health` | 서버 헬스체크 | 운영 중 |
| `POST` | `/resume/fix` | 이력서 자동 최적화 — JOB_FIT·ACHIEVEMENT 2버전 생성 (무상태) | 운영 중 |
| `POST` | `/resume/chat` | 이력서 챗봇 교정 — reason + suggested_body 반환 (세션 기반) | 운영 중 |
| `POST` | `/resume/generate` | 이력서 초안 생성 (무상태) | 운영 중 |
| `POST` | `/resume/pdf/extract` | PDF 이력서 소재 추출 | 운영 중 |
| `POST` | `/resume/text/extract` | Notion 텍스트 소재 추출 | 운영 중 |
| `POST` | `/resume/manual/extract` | 수동 입력 소재 추출 (원문+요약) | 운영 중 |
| `POST` | `/match/top10` | 공고 TOP 10 추천 | 운영 중 |
