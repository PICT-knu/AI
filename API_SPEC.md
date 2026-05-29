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
  ├─ PDF 업로드     → POST /resume/pdf/extract  → title + summary 반환 → DB 저장
  └─ Notion/직접입력 → POST /resume/text/extract → title + summary 반환 → DB 저장
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
| `resume_materials` | **필수** | 이력서 소재 목록. **1개 이상 필수** (빈 배열 시 422 반환) |
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
      "body": { "about": "...", "experience": [...], "skills": [...] },
      "matching_score": 82,
      "summary": "..."
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
| `message` | **필수** | 사용자의 수정 요청 자연어 메시지. **빈 문자열 불가** (빈 값 시 422 반환) |
| `current_body` | 선택 | 현재 이력서 본문 (ResumeBody 구조). 세션이 만료된 경우 이 값으로 컨텍스트를 복원함. **세션 만료에 대비해 항상 전달을 권장** |
| `resume_materials` | **필수** | 현재 이력서 소재 목록. **1개 이상 필수** (빈 배열 시 422 반환). 매 요청마다 최신 소재를 전달. 할루시네이션 검증에 사용 |
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

> **세션**: TTL 1시간 (마지막 요청 기준 갱신). 만료 후 동일 `session_id` + `current_body` 재전송 시 자동 복원. 대화 이력 20개 초과 시 서버가 자동 요약.

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

**요청 필드**

| 필드 | 필수 | 설명 |
|------|------|------|
| `user_profile` | **필수** | 사용자 기본 프로필. 모든 하위 필드는 선택 (없으면 `""` 또는 생략) |
| `user_profile.career_level` | 선택 | 경력 단계. 예: `"신입"`, `"1-3년"` |
| `user_profile.degree_type` | 선택 | 대학 유형. 예: `"4년제"`, `"2/3년제"` |
| `user_profile.graduation_status` | 선택 | 졸업 여부. 예: `"졸업"`, `"재학중"`, `"졸업예정"` |
| `user_profile.school_name` | 선택 | 학교명. 예: `"국립공주대학교"` |
| `user_profile.major` | 선택 | 전공. 예: `"컴퓨터공학"` |
| `user_profile.enrollment_year` | 선택 | 입학년도. 예: `"2022"` |
| `user_profile.graduation_year` | 선택 | 졸업(예정)년도. 예: `"2026"` |
| `resume_materials` | **필수** | 이력서 소재 목록. **1개 이상 필수** (빈 배열 시 422 반환) |
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

**Notion/직접 입력 텍스트에서 소재 추출**

Notion 페이지 본문 또는 사용자가 직접 작성한 텍스트를 소재 카드로 변환합니다.  
회의록, 받은 피드백, 코드 덤프 등 본인 작업으로 단정할 수 없는 내용은 자동으로 걸러집니다.

#### 요청 Body

```json
{
  "text": "Notion 페이지 본문 전문"
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `text` | **필수** | Notion 페이지 본문 또는 직접 작성 텍스트. 빈 문자열이면 LLM 호출 없이 빈 배열 반환 |

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
    "avoidance_options": ["계약직 제외", "주말 근무 제외"],
    "preferred_locations": ["서울", "경기"],
    "experience_level": "경력",
    "preferred_company_sizes": ["대기업", "중견기업"],
    "preferred_benefits": ["재택근무", "유연근무"]
  }
}
```

**user_preferences 필드**

| 필드 | 필수 | 설명 |
|------|------|------|
| `avoidance_options` | 선택 | 기피 조건 고정 선택지 목록. 허용값: `"계약직 제외"`, `"경력직만 채용 제외"`, `"주말 근무 제외"`, `"교대/야간 근무 제외"`, `"잦은 출장 제외"`, `"포트폴리오 필수 제외"`, `"사전 과제 있음 제외"`, `"고객 응대 중심 제외"` |
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

---

### `POST /jobs/detail-analysis`

**채용 공고 상세 분석 (공고 상세 페이지용, 무상태)**

채용 공고 원문(`description`)을 분석해 **주요 업무 / 자격 요건 / 복지·혜택** 세 가지 섹션의 문장 배열로 정리합니다.  
공고 상세 조회 페이지의 요약 카드 렌더링에 사용합니다.

#### 요청 Body

```json
{
  "job_posting_id": 123,
  "company_name": "Toss",
  "title": "시니어 프론트엔드 엔지니어",
  "description": "Toss에서 세계 최고 수준의 금융 도구를 함께 만들어갈 시니어 프론트엔드 엔지니어를 찾습니다. Toss 플랫폼의 핵심 사용자 인터페이스를 담당하며 제품 디자이너와 협업하여 차세대 금융 대시보드를 구현합니다. 자격 요건: 5년 이상의 React 및 TypeScript 대규모 서비스 개발 경험, CSS 아키텍처 및 Tailwind CSS에 대한 깊은 이해. 복지: 종합 건강 검진 지원, 400만원 장비 지원."
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `job_posting_id` | 선택 | 채용공고 PK (BE1 DB). AI 서버는 저장하지 않음, 로그 추적용 |
| `company_name` | 선택 | 회사명. 분석 시 컨텍스트로 활용 |
| `title` | 선택 | 공고 제목. 분석 시 컨텍스트로 활용 |
| `description` | **필수** | 채용 공고 원문. AI의 메인 분석 대상. 빈/공백이면 LLM 호출 없이 빈 배열 반환 |

#### 응답 200 OK

```json
{
  "main_tasks": [
    "Toss 플랫폼의 핵심 사용자 인터페이스 담당",
    "제품 디자이너와 협업하여 차세대 금융 대시보드 구현"
  ],
  "qualifications": [
    "5년 이상의 React 및 TypeScript 대규모 서비스 개발 경험",
    "CSS 아키텍처 및 Tailwind CSS에 대한 깊은 이해"
  ],
  "benefits": [
    "종합 건강 검진 지원",
    "400만원 장비 지원"
  ]
}
```

| 필드 | 설명 |
|------|------|
| `main_tasks` | 담당할 주요 업무 문장 배열. 공고에 명시된 내용만 추출, 섹션당 최대 6개. 없으면 빈 배열 |
| `qualifications` | 요구 자격 요건 문장 배열. 섹션당 최대 6개. 없으면 빈 배열 |
| `benefits` | 복지·혜택 문장 배열. 섹션당 최대 6개. 없으면 빈 배열 |

> 공고에 명시된 내용만 추출하며 지어내지 않습니다(할루시네이션 방지). OpenRouter JSON Schema strict 모드로 구조화 출력을 강제합니다.  
> AI 처리 실패 시 `502` 반환 (외부 AI 서비스 오류).

---

## 상태 코드 요약

| 코드 | 설명 | 발생 시점 |
|------|------|-----------|
| `200 OK` | 성공 | 정상 처리 완료 |
| `422 Unprocessable Entity` | 요청 유효성 오류 | 필드 누락, 타입 불일치, 빈 문자열/배열 등 |
| `500 Internal Server Error` | 서버 오류 | LLM 호출 실패, 파싱 오류 등 |
| `502 Bad Gateway` | 외부 AI 서비스 오류 | 소재 추출(`/pdf/extract`, `/text/extract`)·공고 상세 분석(`/jobs/detail-analysis`)에서 OpenRouter 호출 실패 시 |
| `504 Gateway Timeout` | LLM 응답 시간 초과 | LLM 호출이 90초(기본값) 이내 응답하지 않을 때. `LLM_TIMEOUT_SECONDS`로 변경 가능 |

---

## 엔드포인트 요약

| 메서드 | 경로 | 기능 | 상태 |
|--------|------|------|------|
| `GET` | `/health` | 서버 헬스체크 | 운영 중 |
| `POST` | `/resume/fix` | 이력서 자동 최적화 — JOB_FIT·ACHIEVEMENT 2버전 생성 (무상태) | 운영 중 |
| `POST` | `/resume/chat` | 이력서 챗봇 교정 — reason + suggested_body 반환 (세션 기반) | 운영 중 |
| `POST` | `/resume/generate` | 이력서 초안 생성 (무상태) | 운영 중 |
| `POST` | `/resume/pdf/extract` | PDF 이력서 소재 추출 | 운영 중 |
| `POST` | `/resume/text/extract` | Notion/직접입력 텍스트 소재 추출 | 운영 중 |
| `POST` | `/match/top10` | 공고 TOP 10 추천 | 운영 중 |
| `POST` | `/jobs/detail-analysis` | 공고 상세 분석 — 주요 업무·자격 요건·복지 추출 | 운영 중 |
