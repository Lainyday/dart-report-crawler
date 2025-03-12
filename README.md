# DART 보고서 크롤링 자동화

이 프로젝트는 DART(Data Analysis, Retrieval and Transfer System)에서 기업의 지급수단별ㆍ지급기간별 지급금액 및 분쟁조정기구에 관한 보고서를 자동으로 크롤링하는 도구입니다.

## 기능

- 지정된 기업들의 DART 보고서 자동 검색
- 보고서에서 주요 데이터 추출
  - 현금 및 수표 지급금액/비중
  - 60일 초과 지급금액/비중
  - 분쟁조정기구 설치 여부
- 결과를 테이블 형식으로 표시
- CSV 파일 다운로드 지원
- API 엔드포인트 제공

## 설치 방법

1. 필요한 패키지 설치:
```bash
pip install -r requirements.txt
```

2. 실행:
```bash
streamlit run test.py
```

## API 사용 방법

API 모드로 실행하려면 URL에 `api_request` 파라미터를 추가하세요:
```
https://[your-app-url]?api_request=true
```

## 응답 형식

```json
{
    "timestamp": "2024-02-15 09:00:00",
    "total_count": 10,
    "data": [
        {
            "공시대상회사": "회사명",
            "접수일자": "2024-02-15",
            "현금_수표_지급금액": 1000000,
            "현금_수표_비중": 80.5,
            "초과지급금액": 100000,
            "초과지급비중": 10.5,
            "분쟁조정기구": "설치"
        }
    ]
}
```

## 주의사항

- Chrome WebDriver가 자동으로 설치됩니다
- API 요청은 처리 시간이 다소 소요될 수 있습니다
- 결과는 JSON 형식으로 반환됩니다 