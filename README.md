# Polaris — Investing Hub

Jay의 투자 커맨드 센터. 흩어진 도구와 정예 리서치를 하나의 URL로 묶는 허브 랜딩.

- **포트폴리오 관리** → `/portfolio-tracker/`
- **RS 스크리너** → `/rs-screener/`
- **리서치 노트** → 정예 자료만 append-only로 누적 (카테고리 분류, 보고서는 추후)

## 설계 원칙

- **합치기 X, 허브로 묶기 O.** 기존 도구의 자동 파이프라인(시트 pull·일일 Action)을 건드리지 않고, 위에 랜딩 한 장만 얹는다.
- 단일 파일 정적 사이트 (`index.html`). 외부 의존성 없음.
- 다크 테마는 portfolio-tracker 계승, Polaris(북극성) 모티프.

## 배포

GitHub Pages user site. 리포 이름은 `<username>.github.io`, 루트(`/`) 브랜치 main에서 서빙.
