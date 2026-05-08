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

### ResumeMaterial

이력서 소재 단위. BE1이 DB에서 조회한 소재를 그대로 배열로 전달합니다.

```json
{
  "material_type": "string",
  "content": "string",
  "material_id": "string"
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `material_type` | **필수** | 소재 유형. 자유 문자열이지만 권장값: `"experience"` (경력), `"project"` (프로젝트), `"skill"` (기술), `"education"` (학력), `"certificate"` (자격증) |
| `content` | **필수** | 소재 내용 전문. AI가 이 텍스트만을 참조해 이력서를 생성하므로 정보가 충분해야 함 |
| `material_id` | 선택 | 소재의 고유 ID. 챗봇 응답의 `changes[].material_id`와 대응됨. `null`이면 AI가 출처 추적 불가 |

---

### JobPost

채용 공고 정보. AI가 이력서를 공고에 맞춰 최적화하는 데 사용합니다.

```json
{
  "job_id": "string",
  "description": "string",
  "experience_text": "string",
  "education_text": "string",
  "employment_type": "string"
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `job_id` | 선택 | 공고 ID. `/resume/fix`, `/resume/chat`에서는 사용하지 않음. `/match/top10`에서는 **사실상 필수** (응답에서 해당 값을 그대로 반환하므로) |
| `description` | **필수** | 공고 전문(JD). AI의 메인 분석 대상. 충분한 공고 내용을 포함해야 매칭 품질이 높아짐 |
| `experience_text` | **필수** | 공고의 경력 요건 (예: `"신입 가능"`, `"3년 이상"`) |
| `education_text` | **필수** | 공고의 학력 요건 (예: `"대졸 이상"`, `"무관"`) |
| `employment_type` | **필수** | 고용 형태 (예: `"정규직"`, `"계약직"`, `"인턴"`) |

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

사용자의 소재들을 기반으로 채용 공고에 최적화된 이력서 전문을 자동 생성합니다.  
세션 없이 요청 1회로 완결됩니다.

> 이력서 소재(resume_materials)만 있으면 됩니다. 이력서가 이미 존재하는 경우에 사용하세요.

#### 요청 Body

```json
{
  "resume_materials": [
    {
      "material_type": "string",
      "content": "string",
      "material_id": "string"
    }
  ],
  "job_post": {
    "job_id": "string",
    "description": "string",
    "experience_text": "string",
    "education_text": "string",
    "employment_type": "string"
  }
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `resume_materials` | **필수** | 이력서 소재 목록. 1개 이상 필요. 배열이 비어 있으면 할루시네이션 방지 로직이 작동하지 않음 |
| `job_post` | **필수** | 타겟 채용 공고. AI가 이 공고에 맞춰 이력서를 조정함 |

#### 응답 200 OK

```json
{
  "revised_resume": "string"
}
```

| 필드 | 설명 |
|------|------|
| `revised_resume` | AI가 생성한 이력서 전문. 줄바꿈(`\n`) 포함 텍스트. BE1이 받아서 DB에 저장 |

#### 처리 흐름

1. 소재 키워드 추출 → 공고 최적화 이력서 생성 (LLM temperature: 0.6)
2. 생성 결과를 소재 원문과 대조해 할루시네이션 검증 (검증 모델: `gemma2-9b-it`, temperature: 0.0)
3. 검증 실패 시 1회 재시도 (실패 사유를 프롬프트에 포함)
4. 재시도도 실패 시 소재 텍스트 단순 연결 결과를 폴백으로 반환

---

### `POST /resume/chat`

**이력서 챗봇 교정 모드 (Chatbot Mode, 세션 기반)**

사용자가 자연어로 수정 요청을 보내면 AI가 구체적인 수정 제안을 반환합니다.  
세션을 통해 대화 맥락이 유지됩니다.

#### 요청 Body

```json
{
  "session_id": "string",
  "user_message": "string",
  "resume_materials": [
    {
      "material_type": "string",
      "content": "string",
      "material_id": "string"
    }
  ],
  "job_post": {
    "job_id": "string",
    "description": "string",
    "experience_text": "string",
    "education_text": "string",
    "employment_type": "string"
  }
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `session_id` | 선택 | 세션 식별자. **첫 요청 시 `null` 또는 생략** → 서버가 새 세션을 생성하고 응답으로 반환. 이후 요청에는 이전 응답의 `session_id`를 그대로 재사용 |
| `user_message` | **필수** | 사용자의 수정 요청 자연어 메시지 |
| `resume_materials` | **필수** | 현재 이력서 소재 목록. 매 요청마다 최신 소재를 전달. 할루시네이션 검증에 사용 |
| `job_post` | 선택 | 타겟 공고. 공고 없이 일반 교정도 가능. `null`이면 공고 최적화 없이 소재 기반으로만 수정 |

#### 응답 200 OK

```json
{
  "session_id": "string",
  "changes": [
    {
      "original": "string",
      "suggested": "string",
      "reason": "string",
      "material_id": "string"
    }
  ]
}
```

| 필드 | 설명 |
|------|------|
| `session_id` | 현재 세션 ID. **다음 요청에 반드시 이 값을 그대로 전달해야 대화 맥락이 유지됨.** UUID v4 형식 |
| `changes` | AI가 제안하는 수정 사항 목록. 할루시네이션 검증을 통과한 항목만 포함. 빈 배열(`[]`)일 수 있음 |
| `changes[].original` | 수정 전 원본 텍스트 |
| `changes[].suggested` | AI가 제안하는 수정 텍스트 |
| `changes[].reason` | 이 수정을 제안한 이유. 사용자에게 그대로 표시 가능 |
| `changes[].material_id` | 이 수정의 근거가 된 소재의 `material_id`. 사용한 소재가 불명확하면 `null` |

**응답 헤더**

| 헤더 | 설명 |
|------|------|
| `X-Session-Id` | 응답 Body의 `session_id`와 동일한 값. 클라이언트가 헤더에서도 읽을 수 있도록 이중 제공 |

#### 세션 관리

- 세션 TTL: **1시간** (마지막 요청 기준으로 갱신)
- 세션 만료 후 `session_id`를 재사용하면 새 세션이 자동 생성됨
- 대화 이력이 20개 메시지를 초과하면 서버가 자동으로 이전 내용을 요약 압축 (클라이언트 투명)

---

### `POST /resume/generate`

**원클릭 이력서 초안 생성 (이력서 없는 신규 사용자용, 무상태)**

기본 프로필 + 소재만으로 이력서 초안을 처음부터 생성합니다.  
기존 이력서가 없는 사용자에게 사용하세요.

> `/resume/fix`와의 차이: `fix`는 기존 이력서를 다듬는 것, `generate`는 처음부터 초안을 작성하는 것.

#### 요청 Body

```json
{
  "user_profile": "string",
  "resume_materials": [
    {
      "material_type": "string",
      "content": "string",
      "material_id": "string"
    }
  ],
  "job_post": {
    "job_id": "string",
    "description": "string",
    "experience_text": "string",
    "education_text": "string",
    "employment_type": "string"
  }
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `user_profile` | **필수** | 사용자 기본 정보 텍스트. 이름, 연락처, 학력 등 구조화되지 않은 자유 형식도 가능. AI가 파싱해서 이력서 헤더로 사용 |
| `resume_materials` | **필수** | 이력서 소재 목록. 1개 이상 필요 |
| `job_post` | **필수** | 타겟 채용 공고. 초안 방향성을 결정함 |

#### 응답 200 OK

```json
{
  "generated_resume": "string"
}
```

| 필드 | 설명 |
|------|------|
| `generated_resume` | AI가 처음부터 생성한 이력서 초안 전문. 자기소개, 경험/프로젝트, 기술 스택 섹션 포함. 줄바꿈(`\n`) 포함 텍스트 |

#### 처리 흐름

`/resume/fix`와 동일한 할루시네이션 검증 + 재시도 + 폴백 로직 적용.

---

### `POST /match/top10`

**채용 공고 TOP 10 추천 + 적합도 점수 계산**

사용자 이력서 소재와 여러 채용 공고를 비교해 상위 10개를 선별하고 점수를 반환합니다.

#### 요청 Body

```json
{
  "resume_materials": [
    {
      "material_type": "string",
      "content": "string",
      "material_id": "string"
    }
  ],
  "job_posts": [
    {
      "job_id": "string",
      "description": "string",
      "experience_text": "string",
      "education_text": "string",
      "employment_type": "string"
    }
  ]
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `resume_materials` | **필수** | 사용자 이력서 소재 목록. 적합도 점수 계산의 기준이 됨 |
| `job_posts` | **필수** | 점수를 계산할 채용 공고 목록. 제한 없음. 내부적으로 10개씩 배치 처리 |
| `job_posts[].job_id` | **사실상 필수** | 공고 식별자. 응답의 `recommendations[].job_id`에 그대로 반환되므로 반드시 포함 권장. `null`이면 응답에서 해당 공고를 식별 불가 |

#### 응답 200 OK

```json
{
  "recommendations": [
    {
      "job_id": "string",
      "match_score": 0,
      "reason_text": "string"
    }
  ]
}
```

| 필드 | 설명 |
|------|------|
| `recommendations` | 상위 10개 공고 목록. `match_score` 내림차순 정렬. 입력 공고가 10개 미만이면 그만큼만 반환 |
| `recommendations[].job_id` | 요청 시 전달한 공고의 `job_id` |
| `recommendations[].match_score` | 적합도 점수. 범위: `0.0 ~ 100.0`. 소수점 2자리. 점수가 높을수록 적합 |
| `recommendations[].reason_text` | 점수 산정 근거 요약. 형식 예시: `"경력:90, 기술스택:80, 복지:75"`. 사용자에게 그대로 표시 가능 |

#### 처리 흐름

1. 공고 목록을 10개 단위 배치로 분할
2. 배치별 LLM 점수 계산 (temperature: 0.1 — 일관성 최우선)
3. 모든 배치 결과 집계 → 상위 10개 반환
4. 특정 배치 실패 시 해당 배치는 건너뛰고 나머지 배치 결과만 반환 (부분 성공 가능)

---

## 상태 코드 요약

| 코드 | 설명 | 발생 시점 |
|------|------|-----------|
| `200 OK` | 성공 | 정상 처리 완료 |
| `422 Unprocessable Entity` | 요청 유효성 오류 | 필드 누락, 타입 불일치 등 |
| `500 Internal Server Error` | 서버 오류 | LLM 호출 실패, 파싱 오류 등 |

---

## 엔드포인트 요약

| 메서드 | 경로 | 기능 | 상태 |
|--------|------|------|------|
| `GET` | `/health` | 서버 헬스체크 | 운영 중 |
| `POST` | `/resume/fix` | 이력서 자동 최적화 (무상태) | 운영 중 |
| `POST` | `/resume/chat` | 이력서 챗봇 교정 (세션 기반) | 운영 중 |
| `POST` | `/resume/generate` | 이력서 초안 생성 (무상태) | 운영 중 |
| `POST` | `/match/top10` | 공고 TOP 10 추천 | 운영 중 |
