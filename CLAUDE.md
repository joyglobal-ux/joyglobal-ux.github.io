# Polaris — Jay's Investing Hub

이 repo는 **https://joyglobal-ux.github.io/** (GitHub Pages 루트 사이트)다.
어느 기기에서 작업하든(개인 맥북, 회사 맥북, claude.ai/code) 이 문서의 규칙을 따른다.
`main`에 push하면 자동 배포된다.

## 이 repo에 있는 것 / 없는 것

| 경로 | 내용 |
|---|---|
| `index.html` | 허브 랜딩 (다크 테마 + 북극성 컨셉, 단일 파일) |
| `research/*.html` | 산업별 리서치 노트 (파일 하나 = 산업 하나) |
| `liquidity/` | 유동성 대시보드 (data.json + refresh.py) |
| `capex-gate/` | CAPEX 게이트 워치 (게이트 판정·팩트 로그는 수동 HTML append-only, 크레딧 레이어는 refresh.py 자동) |
| `briefing/` | 뉴스레터 브리핑 (영어 뉴스레터 핵심 인사이트 일일 누적, append-only. 개인 맥북 예약작업 `newsletter-briefing`이 매일 07:30 추가. 포지션 연결·Gmail 링크 금지) |

**여기 없는 것**: portfolio-tracker, rs-screener, semiconductor-cycle, etf-tracker는
**각각 별도 repo**다 (GitHub Pages 프로젝트 사이트로 `/도구이름/` 경로에 붙음).
그 도구들을 고치려면 해당 repo로 가야 한다. 이 repo에서는 index.html의 링크 카드만 관리한다.

## 리서치 노트 워크플로우 (가장 흔한 작업)

다른 대화에서 나온 산업·기업 스터디를 노트로 적재하는 작업. 규칙:

1. **핵심만 요약** — 대화 전체가 아니라 투자 결정에 영향 주는 정수만
   (테제 · 기술 · 병목 · 경쟁 · 타임라인 · 판정).
2. **append-only** — 기존 노트는 수정·삭제하지 않는다. 새 `<article class="note" data-id="YYYYMMDD-slug">`를
   해당 산업 파일의 `<!-- 새 노트는 이 줄 바로 아래에 추가 (최신순) -->` 주석 바로 아래에 추가 (최신순).
3. **노트 구조** — 기존 노트의 마크업을 그대로 따른다:
   `.nmeta`(날짜 YYYY.MM.DD + 티커 `.tk` + 태그 `.tag`) → `.ntitle` → `.nlede`(한 줄 요약, `<b>한 줄:</b>` 시작)
   → **`.nbody`** 래퍼 안에 `.sec` 섹션들(`.sech`에 번호 `.sn` 01, 02… + 소제목) + `.disc`.
   `.nbody`를 빼먹어도 JS가 자동 래핑하지만, 새 노트는 명시하는 게 원칙.
4. **index.html 카드 동기화** — 노트를 추가하면 해당 카테고리 카드의 카운트 갱신
   (`노트 N · 열기 →`). 카테고리에 **첫 노트**가 생기면 `<div class="cat">`(노트 준비 중)을
   `<a class="cat" href="/research/파일.html">`로 바꾸고 활성 스타일(기존 활성 카드의 인라인 style 복사) 적용.
   **여기가 유일한 수동 동기화 지점이다.**
5. **새 산업 파일** — 기존 `research/*.html` 하나를 복제해 헤더(아이콘·제목·hsub)만 바꾸고 노트를 넣는다.
   `.toc`/`.fold` CSS 블록과 하단 `<script>`(누적 레이어)는 **반드시 같이 복사**한다. index.html 카드도 추가.

### 인사이트 인박스 (`_inbox/insights.md`, 2026-10-10)

WSJ 등 **기사 1건마다 노트를 만들지 않는다.** 기사를 요약하면 건당 1~3줄 인사이트만
인박스에 최신순으로 쌓는다. **같은 테마가 3~5건 모이면** 종합 노트를 Jay에게 제안한다.
노트로 소화한 항목은 지우지 않고 `→ 반영: …` 표시만 단다. `_` 폴더라 사이트에는 배포되지 않지만
repo가 public이라 보유 종목·매매 계획은 적지 않는다.

### 누적 레이어 (자동 — 손대지 말 것)

각 `research/*.html` 하단의 `<script>`가 DOM을 읽어 **목차 · 태그 필터 · 접기 · 딥링크 앵커**를
전부 자동 생성한다. 노트를 하나 붙이면 목차 줄, 태그 칩, `#앵커`가 알아서 늘어난다.

- **노트 ID** = `data-id` 값. 없으면 `날짜+제목slug`로 자동 생성.
  제목은 append-only라 ID가 안 변하므로 **딥링크가 영구적**이다.
  → `/research/robotics.html#20260822-humanoid-map` 형태로 다른 문서·노션에서 특정 노트를 바로 걸 수 있다.
- **접기** — 최신 노트만 펼침, 나머지는 자동 접힘. 노트가 쌓여도 스크롤이 안 터진다.
- **태그 필터** — `.nmeta`의 `.tk`·`.tag`가 곧 필터 칩. **태그를 성의 있게 달수록 나중에 검색이 된다.**
- 이 스크립트를 수정할 일이 생기면 **5개 파일 전부 동일하게** 반영할 것 (복붙 공유 중).

### 리포트 원문 도표 인용 (그래프·표 스크린샷)

리서치 원문의 그래프·표는 **말로 옮기지 말고 그대로 캡처해 붙인다.** 숫자를 다시 타이핑하면
오류가 끼고, 원본 형태가 주는 정보(곡선 모양, 격차, 빈 칸)가 사라진다.

- 엔진: `../.claude/tools/pdf_shot.py` (PyMuPDF). 절차는
  ① `pages` 로 후보 페이지를 dpi 90~95 썸네일로 뽑아 **눈으로 보고**
  ② `clip` 으로 0~1 비율 좌표를 지정해 dpi 170으로 잘라낸다.
- 저장 위치: **`research/assets/<산업>/<YYYYMMDD>-<slug>.png`** (repo 안에 둔다. 외부 raw URL 금지).
- 마크업:
  ```html
  <figure class="fig">            <!-- 표처럼 가로가 길면 class="fig wide" -->
    <div class="fw"><img src="assets/<산업>/<날짜>-<slug>.png" alt="…" loading="lazy"></div>
    <figcaption><b>그림 N.</b> 무엇인지 — <b>왜 중요한지 한 줄</b>. 자료: …</figcaption>
  </figure>
  ```
  두 장을 나란히 놓을 땐 `<div class="figs2">`로 감싼다.
- **figcaption에 반드시 "왜 이 도표를 넣었는지"를 쓴다.** 도표만 있고 해석이 없으면 나중에 안 읽는다.
- 흰 배경 원문이 다크 테마 위에 뜨는 건 의도된 디자인(`.fw`가 종이 카드처럼 감싼다).

### 컴포넌트 팔레트 (새 CSS 추가 전에 여기부터)

노트마다 새 CSS를 추가하면 파일이 무한히 커진다. 아래 조립만으로 대부분 커버된다:

| 클래스 | 용도 |
|---|---|
| `.sec` / `.sech` + `.sn` | 노트 안 번호 섹션 |
| `.p` / `.hl` | 본문 문단 / 강조 |
| `.rows` + `.r` + `.r.verdict` | 라벨-값 행, 금색 판정 박스 |
| `.tbl` (+ `.scrollx` 래퍼) | 표 |
| `.tl` + `.ev.done/.future` | 타임라인 |
| `.quad` / `.lanes` / `.chn` | 4카드 / 3레인 / 화살표 체인 |
| `.bn` + `.lay.sys/.comp` + `.pill` | 병목·대비 레이어 |
| `.why` / `.fix` | 파란 보충 박스 / 빨간 경고·정정 박스 |
| `.fig` / `.fig.wide` / `.figs2` | 원문 도표 캡처 |

정말 새 CSS가 필요하면 `/* ── <노트명> 전용 ── */` 주석을 달아 나중에 지울 수 있게 한다.

### 파일이 커지면

노트 **12개** 또는 파일 **400KB**를 넘으면 연도별로 분리한다
(`robotics.html` → `robotics.html`(현재연도) + `robotics-2026.html`(아카이브)).
index.html 카드에는 현재 파일을 걸고, 파일 상단에 이전 연도 링크를 남긴다.
이미지 자산은 `research/assets/<산업>/`에 그대로 누적(파일명이 날짜로 시작하므로 정렬됨).

## CAPEX 게이트 워치 (`capex-gate/`)

2026-07-31 노션에서 이관. **노션 페이지는 아카이브 — 거기 새로 쓰지 않는다.**

- **팩트 로그**는 리서치 노트와 같은 append-only 규칙: `<!-- 새 엔트리는 이 줄 바로 아래에 추가 (최신순) -->`
  주석 바로 아래에 `<div class="entry">`(판정 영향 시 `entry alert`) 추가. 기존 엔트리 수정·삭제 금지.
- 게이트 상태가 바뀌면 상단 `.gates` 카드의 `.st` 배지 문구·색도 함께 갱신.
- 미확인 보도는 `<span class="tag">미확인</span>`. 증권사 리포트는 1차 소스와 크로스체크.
- **숫자 레이어(`refresh.py`, `data.js`)는 Actions가 평일 자동 갱신 — 손대지 않는다.**
  단 실제 CDS 실측치를 새로 입수하면 `refresh.py`의 `CDS_ANCHOR`·`ANCHOR_DATE`를 갱신할 것
  (크레딧 프록시의 캘리브레이션 앵커. 실제 CDS는 무료 소스가 없어 변동성 프록시로 대체 중).

## 앱(PWA) 껍데기 (2026-11-02)

Polaris는 폰 홈 화면에 설치해 쓰는 PWA다. 루트(이 repo)가 같은 오리진의 프로젝트 사이트(rs-screener·semiconductor-cycle·portfolio-tracker·etf-tracker)까지 함께 담당한다.

- `manifest.webmanifest` + `icons/`(북극성 모티프 PNG, 재생성은 `python3 _pwa/mkicons.py icons`) + `sw.js`(scope `/`).
- **서비스워커 전략**: HTML = network-first(3.5초) → 오프라인/5xx면 캐시 · 데이터(*.json, data*.js, series-*.js) = network-first → 캐시(쿼리 떼고 경로당 1개) · 큰 파일(setups·events·series·data-us/kr)은 최근 8개만 · 아이콘/이미지/Chart.js = stale-while-revalidate.
  캐시 구조나 전략을 바꾸면 `sw.js`의 `VERSION`을 올린다(이전 캐시 자동 삭제).
- **모든 페이지 `<head>`에 공용 스니펫**(`<!-- polaris-app:start -->` ~ `end`): manifest·theme-color·apple 메타·서비스워커 등록·standalone 전용 하단 탭바(홈/포트폴리오/배분판/종목 리스트/리서치).
  원본은 `_pwa/snippet.html` 하나. 고칠 땐 원본만 고치고 `python3 _pwa/inject.py <페이지들>`로 일괄 반영(블록 교체 + viewport-fit=cover).
  **새 페이지·새 산업 파일**은 복제하면 스니펫이 따라오니 그대로 둔다. 다른 repo 페이지도 같은 명령으로(etf-tracker는 생성기 `kosdaq_etf_tracker.py`에 넣으면 f-string 이스케이프 자동).
- 폰 폭 CSS는 각 페이지 미디어쿼리(≤640~820px) 안에만 둔다 — 데스크톱 레이아웃은 건드리지 않는다.
- 로컬 검증: `.claude/launch.json`의 **`polaris-all`**(:8100, 루트+프로젝트 사이트를 한 오리진에 마운트)에서 `?pwa=1`을 붙이면 브라우저에서도 탭바가 보인다(세션 동안 유지).
  `.claude/polaris-all.OFFLINE` 파일을 만들면 서버가 전부 503 → 오프라인 캐시 확인. 금고 풀린 화면은 `TEST_VAULT=<테스트 비밀번호로 만든 임시 vault.json>` env로 대체해 확인(실제 비밀번호 사용 금지, 확인 후 임시 파일 삭제).

## 스타일 규칙

- 모든 페이지는 **의존성 없는 단일 HTML 파일** (외부 JS/CSS/폰트 CDN 금지).
- 색은 반드시 기존 CSS 변수(`--bg`, `--panel`, `--accent`, `--gold` 등) 사용. 다크 테마 고정.
- 언어는 한국어, 필요한 곳만 영어 병기.
- 서브페이지는 상단에 `← Polaris 허브` back 링크 필수.
- 히어로의 "최종 업데이트"는 `document.lastModified` 기반 **자동**이다. 수동으로 날짜를 박지 말 것.

## 검증 (필수)

output을 만들면 반드시 검증한다:
- HTML 수정 후 브라우저로 **렌더링 확인** — 특히 한글 깨짐, 레이아웃, 가로 오버플로우.
- **이미지가 있는 노트는 `file://`로 열면 안 된다** (상대경로 이미지가 안 뜬다).
  `.claude/launch.json`의 **`polaris-live`** 프리뷰(`node .claude/static-server.js`, :8099)로 확인할 것.
  브라우저 캐시 때문에 수정이 반영 안 되면 `?v=2` 같은 쿼리를 붙여 강제 로드.
- 수치를 적었다면 원본 소스와 교차 확인.
- push 후에는 라이브 URL이 반영됐는지까지는 안 봐도 되지만, push 전 로컬 확인은 생략 금지.

## 커밋

- 작업 단위로 커밋하고 `main`에 push (별도 브랜치 불필요).
- 커밋 메시지는 한국어 한 줄이면 충분 (예: `리서치: 반도체 — 삼성전기 Si-Cap 노트 추가`).

## 하지 말 것

- 기존 노트 내용 수정/삭제 (append-only).
- 허브에 포트폴리오 원화 금액·계좌 수치 노출 (금액은 지수화 원칙 — portfolio-tracker 참조).
- 다른 도구 repo의 내용을 여기로 복사해오는 것 (링크 카드로만 연결).

## 공개 범위·개인정보 (2026-11-01 점검 후)

- 모든 페이지 `<head>`에 `<meta name="robots" content="noindex, nofollow">` 유지 — 새 페이지·새 산업 파일도 복제 시 그대로 둘 것.
- 커밋 작성자는 repo 로컬 설정의 GitHub noreply 주소를 쓴다. `git -c user.email=개인메일`로 덮어쓰지 말 것.
- 서술 필드·노트에 **주수, 원화 금액, 계좌·대출·신용의 금액이나 일정**을 쓰지 않는다(portfolio-tracker README 규칙과 동일).
- 다른 사이트(ironpal 등)와 이 repo를 서로 링크·언급하지 않는다.
