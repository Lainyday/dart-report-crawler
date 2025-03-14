import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
import time
import pandas as pd
import numpy as np
import re
from datetime import datetime
import json
import requests

# 웹훅으로 데이터 전송하는 함수
def send_to_webhook(data, webhook_url="https://hook.eu2.make.com/2r7gjnxaq0sf0i3cj8adt0lew6sg3k4o"):
    try:
        # 디버깅을 위한 로그 추가
        print(f"웹훅 전송 시도: {webhook_url}")
        print(f"전송 데이터: {json.dumps(data, ensure_ascii=False)}")
        
        response = requests.post(webhook_url, json=data)
        
        # 응답 상태 코드 및 내용 로깅
        print(f"웹훅 응답 상태 코드: {response.status_code}")
        print(f"웹훅 응답 내용: {response.text}")
        
        return response.status_code == 200
    except Exception as e:
        print(f"웹훅 전송 중 오류 발생: {str(e)}")
        if not is_api_mode():
            st.error(f"웹훅 전송 중 오류: {str(e)}")
        return False

# 검색 설정
target_report = "지급수단별ㆍ지급기간별지급금액및분쟁조정기구에관한사항"

# Chrome WebDriver 설정 수정
def setup_chrome_options():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920x1080")
    options.add_argument("--start-maximized")
    # Streamlit Cloud 환경을 위한 추가 설정
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--remote-debugging-port=9222")
    options.binary_location = "/usr/bin/chromium"  # Debian의 chromium 경로로 수정
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    return options

# API 모드 확인
def is_api_mode():
    return 'api_request' in st.query_params and st.query_params['api_request'] == 'true'

def verify_api_key():
    api_key = st.query_params.get('api_key', None)
    return api_key == 'dart_api_2024_secure_key_9x8q2w'

# 결과를 JSON으로 변환하는 함수
def convert_results_to_json(df):
    if df is not None and not df.empty:
        # 날짜 형식 변환
        df['접수일자'] = pd.to_datetime(df['접수일자']).dt.strftime('%Y-%m-%d')
        
        # 데이터프레임 복사
        df_clean = df.copy()
        
        # NaN 값을 None으로 변환
        df_clean = df_clean.replace({float('nan'): None, float('inf'): None, float('-inf'): None})
        
        # 숫자 형식 변환 및 특수 값 처리
        for col in ['현금_수표_지급금액', '초과지급금액']:
            # 문자열을 숫자로 변환
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
            # NaN 값을 None으로 변환
            df_clean[col] = df_clean[col].where(df_clean[col].notna(), None)
            
        for col in ['현금_수표_비중', '초과지급비중']:
            # 문자열을 숫자로 변환
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
            # NaN 값을 None으로 변환
            df_clean[col] = df_clean[col].where(df_clean[col].notna(), None)
        
        # 영문 필드명으로 변환
        df_eng = df_clean.copy()
        df_eng.columns = [
            'company',
            'report_date',
            'cash_check_amount',
            'cash_check_ratio',
            'excess_amount',
            'excess_ratio',
            'dispute_resolution'
        ]
        
        # 딕셔너리로 변환 시 NaN 값을 None으로 처리
        records = []
        for _, row in df_eng.iterrows():
            record = {}
            for col in df_eng.columns:
                val = row[col]
                # NaN, Infinity 값 처리 (numpy 사용)
                if isinstance(val, float) and (pd.isna(val) or np.isinf(val)):
                    record[col] = None
                else:
                    record[col] = val
            records.append(record)
        
        result = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_count": len(df),
            "data": records
        }
        return result
    return {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "total_count": 0, "data": []}

# 결과 데이터프레임 초기화
if 'result_df' not in st.session_state:
    st.session_state.result_df = pd.DataFrame(columns=[
        '공시대상회사', '접수일자', '현금_수표_지급금액', '현금_수표_비중',
        '초과지급금액', '초과지급비중', '분쟁조정기구'
    ])

# 종목코드가 있는 회사
stock_codes = {
    "028260": "삼성물산",
    "000720": "현대건설",
    "047040": "대우건설",
    "375500": "DL이앤씨",
    "006360": "GS건설",
    "294870": "HDC현대산업개발"
}

# 종목코드가 없는 회사 (회사명으로 검색)
company_names = [
    "포스코이앤씨",
    "롯데건설",
    "에스케이에코플랜트",
    "현대엔지니어링"
]

def extract_report_data(driver, rcpNo):
    try:
        viewer_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcpNo}"
        driver.get(viewer_url)
        time.sleep(3)
        
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "ifrm")))
            frame = driver.find_element(By.ID, "ifrm")
            driver.switch_to.frame(frame)
        except:
            pass
        
        data = {
            "현금_수표_지급금액": None,
            "현금_수표_비중": None,
            "초과지급금액": None,
            "초과지급비중": None,
            "분쟁조정기구": None
        }
        
        # 1. (제1호) 현금 및 수표 데이터 추출
        try:
            tables = driver.find_elements(By.XPATH, "//p[contains(text(), '1. (제1호) 지급수단별 지급금액')]/following::table[contains(@border, '1')]")
            if len(tables) >= 1:
                table = tables[0]
                rows = table.find_elements(By.XPATH, ".//tbody/tr")
                if len(rows) >= 1:
                    cells = rows[0].find_elements(By.TAG_NAME, "td")
                    if len(cells) > 1:
                        amount_text = cells[1].text.strip()
                        if amount_text and amount_text != "-":
                            numbers = re.findall(r'\d{1,3}(?:,\d{3})*(?:\.\d+)?', amount_text)
                            if numbers:
                                data["현금_수표_지급금액"] = numbers[0].replace(",", "")
                if len(rows) >= 2:
                    cells = rows[1].find_elements(By.TAG_NAME, "td")
                    if len(cells) > 1:
                        ratio_text = cells[1].text.strip()
                        if ratio_text and ratio_text != "-":
                            ratio_text = ratio_text.replace("①", "").replace("%", "").strip()
                            numbers = re.findall(r'\d+\.\d+|\d+', ratio_text)
                            if numbers:
                                data["현금_수표_비중"] = numbers[0]
        except Exception as e:
            if not is_api_mode():
                st.warning(f"현금 및 수표 데이터 추출 중 오류: {str(e)}")
        
        # 2. (제2호) 60일 초과 데이터 추출
        try:
            tables = driver.find_elements(By.XPATH, "//p[contains(text(), '2. (제2호) 지급기간별 지급금액')]/following::table[contains(@border, '1')]")
            if tables:
                table = tables[0]
                rows = table.find_elements(By.TAG_NAME, "tr")
                
                for row in rows:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 6 and "지급금액" in cells[0].text:
                        amount_text = cells[-1].text.strip()
                        if amount_text and amount_text != "-":
                            numbers = re.findall(r'\d{1,3}(?:,\d{3})*(?:\.\d+)?', amount_text)
                            if numbers:
                                data["초과지급금액"] = numbers[0].replace(",", "")
                    
                    if len(cells) >= 6 and "비중" in cells[0].text:
                        ratio_text = cells[-1].text.strip()
                        if ratio_text and ratio_text != "-":
                            ratio_text = ratio_text.replace("%", "").strip()
                            numbers = re.findall(r'\d+\.\d+|\d+', ratio_text)
                            if numbers:
                                data["초과지급비중"] = numbers[0]
        except Exception as e:
            if not is_api_mode():
                st.warning(f"60일 초과 데이터 추출 중 오류: {str(e)}")
        
        # 3. (제3호) 분쟁조정기구 설치 여부
        try:
            tables = driver.find_elements(By.XPATH, "//p[contains(text(), '3. (제3호) 분쟁조정기구')]/following::table")
            installed = False
            
            for table in tables:
                rows = table.find_elements(By.XPATH, ".//tr[.//td[contains(text(), '분쟁조정기구 설치 여부')] or .//th[contains(text(), '분쟁조정기구 설치 여부')]]")
                if rows:
                    cells = rows[0].find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 2:
                        status = cells[1].text.strip()
                        normalized_status = status.upper().replace(" ", "")
                        if any(mark in normalized_status for mark in ["O", "○", "◯", "0"]):
                            installed = True
                            break
                        elif "X" in normalized_status:
                            installed = False
                            break
            
            data["분쟁조정기구"] = "설치" if installed else "미설치"
        
        except Exception as e:
            if not is_api_mode():
                st.warning(f"분쟁조정기구 데이터 추출 중 오류: {str(e)}")
        
        return data
        
    except Exception as e:
        if not is_api_mode():
            st.error(f"보고서 조회 중 오류 발생: {str(e)}")
        return None

def search_dart_for_company(driver, wait, company_name, stock_code=None):
    found_company_reports = []
    
    try:
        driver.get("https://dart.fss.or.kr/dsab007/main.do?option=report")
        time.sleep(3)
        
        try:
            report_input = wait.until(EC.presence_of_element_located((By.ID, "reportName")))
            report_input.clear()
            report_input.send_keys(target_report)
            time.sleep(2)

            company_input = wait.until(EC.presence_of_element_located((By.ID, "textCrpNm2")))
            company_input.clear()
            company_input.send_keys(stock_code if stock_code else company_name)
            time.sleep(1)
            company_input.send_keys(Keys.RETURN)
            time.sleep(2)
            
            driver.execute_script("search(1, 'btn');")
            time.sleep(3)
            
            try:
                table = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.tbList")))
                rows = table.find_elements(By.TAG_NAME, "tr")
                
                if len(rows) <= 1 or "조회 결과가 없습니다" in table.text:
                    return []
                
                for row in rows[1:]:
                    try:
                        cols = row.find_elements(By.TAG_NAME, "td")
                        if len(cols) >= 6:
                            company_td = cols[1]
                            found_company = company_td.find_element(By.TAG_NAME, "a").text.strip()
                            report_td = cols[2]
                            report_link = report_td.find_element(By.TAG_NAME, "a")
                            report_title = report_link.text.strip()
                            report_href = report_link.get_attribute("href")
                            date_td = cols[4]
                            report_date = date_td.text.strip()
                            
                            if target_report in report_title and report_href and isinstance(report_href, str):
                                try:
                                    # rcpNo 추출 로직 개선
                                    if "rcpNo=" not in report_href:
                                        continue
                                        
                                    rcpNo = report_href.split("rcpNo=")[-1]
                                    if "&" in rcpNo:
                                        rcpNo = rcpNo.split("&")[0]
                                        
                                    if not rcpNo:  # rcpNo가 빈 문자열인 경우
                                        continue
                                        
                                    found_company_reports.append({
                                        "공시대상회사": found_company,
                                        "접수일자": report_date,
                                        "보고서명": report_title,
                                        "rcpNo": rcpNo
                                    })
                                except Exception as e:
                                    if not is_api_mode():
                                        st.warning(f"보고서 번호 추출 중 오류: {str(e)}")
                                    continue
                    except Exception:
                        continue
                
            except Exception as e:
                if not is_api_mode():
                    st.warning(f"{company_name} 결과 처리 중 오류: {str(e)}")
                
        except Exception as e:
            if not is_api_mode():
                st.warning(f"{company_name} 검색 양식 입력 중 오류: {str(e)}")
        
    except Exception as e:
        if not is_api_mode():
            st.error(f"{company_name} 검색 과정 중 오류: {str(e)}")
    
    return found_company_reports

def search_and_extract_data():
    result_data = []
    
    try:
        with st.spinner("🔍 보고서를 검색하고 데이터를 추출 중입니다..."):
            options = setup_chrome_options()
            try:
                # ChromeDriver 설정
                service = Service("/usr/bin/chromedriver")
                driver = webdriver.Chrome(service=service, options=options)
            except Exception as e:
                if not is_api_mode():
                    st.error(f"Chrome 드라이버 초기화 중 오류: {str(e)}")
                return False
            wait = WebDriverWait(driver, 10)
            
            # 종목코드가 있는 회사 먼저 검색
            for stock_code, company_name in stock_codes.items():
                if not is_api_mode():
                    st.info(f"🔍 {company_name}({stock_code}) 검색 중...")
                company_reports = search_dart_for_company(driver, wait, company_name, stock_code)
                if company_reports:
                    for report in company_reports:
                        data = extract_report_data(driver, report['rcpNo'])
                        if data:
                            result_data.append({
                                '공시대상회사': report['공시대상회사'],
                                '접수일자': report['접수일자'],
                                '현금_수표_지급금액': data['현금_수표_지급금액'],
                                '현금_수표_비중': data['현금_수표_비중'],
                                '초과지급금액': data['초과지급금액'],
                                '초과지급비중': data['초과지급비중'],
                                '분쟁조정기구': data['분쟁조정기구']
                            })
                    if not is_api_mode():
                        st.success(f"✅ {company_name}: {len(company_reports)}개 보고서 데이터 추출 완료")
                elif not is_api_mode():
                    st.warning(f"⚠️ {company_name}: 보고서를 찾을 수 없습니다.")
            
            # 종목코드가 없는 회사 검색
            for company_name in company_names:
                if not is_api_mode():
                    st.info(f"🔍 {company_name} 검색 중...")
                company_reports = search_dart_for_company(driver, wait, company_name)
                if company_reports:
                    for report in company_reports:
                        data = extract_report_data(driver, report['rcpNo'])
                        if data:
                            result_data.append({
                                '공시대상회사': report['공시대상회사'],
                                '접수일자': report['접수일자'],
                                '현금_수표_지급금액': data['현금_수표_지급금액'],
                                '현금_수표_비중': data['현금_수표_비중'],
                                '초과지급금액': data['초과지급금액'],
                                '초과지급비중': data['초과지급비중'],
                                '분쟁조정기구': data['분쟁조정기구']
                            })
                    if not is_api_mode():
                        st.success(f"✅ {company_name}: {len(company_reports)}개 보고서 데이터 추출 완료")
                elif not is_api_mode():
                    st.warning(f"⚠️ {company_name}: 보고서를 찾을 수 없습니다.")

            driver.quit()

        if result_data:
            st.session_state.result_df = pd.DataFrame(result_data)
            
            # 데이터 추출 완료 후 자동으로 웹훅으로 데이터 전송
            if not is_api_mode():  # API 모드가 아닐 때만 자동 전송 (API 모드에서는 별도로 처리)
                with st.spinner("🚀 추출된 데이터를 Make.com으로 전송 중..."):
                    result_json = convert_results_to_json(st.session_state.result_df)
                    webhook_success = send_to_webhook(result_json)
                    
                    if webhook_success:
                        st.success("✅ 데이터가 성공적으로 Make.com으로 전송되었습니다!")
                    else:
                        st.error("❌ 데이터 전송에 실패했습니다. 로그를 확인하세요.")
            
            return True
        else:
            if not is_api_mode():
                st.warning("❌ 데이터를 추출할 수 없습니다.")
            return False
                
    except Exception as e:
        if not is_api_mode():
            st.error(f"❌ 오류 발생: {str(e)}")
        return False

# 메인 UI 부분
if is_api_mode():
    # API 인증 확인
    if verify_api_key():
        if search_and_extract_data():
            result_json = convert_results_to_json(st.session_state.result_df)
            
            # 웹훅으로 데이터 전송
            webhook_success = send_to_webhook(result_json)
            if webhook_success:
                st.json({"status": "success", "message": "데이터가 성공적으로 전송되었습니다.", "data": result_json})
            else:
                st.json({"status": "warning", "message": "데이터 추출은 성공했으나 웹훅 전송에 실패했습니다.", "data": result_json})
        else:
            st.json({"error": "데이터 추출 실패", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    else:
        st.json({"error": "인증 실패: 유효하지 않은 API 키", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
else:
    st.title("📄 DART 보고서 크롤링 AI Agent")
    st.subheader("DART 보고서를 자동으로 크롤링합니다.")
    
    # 웹훅 테스트 버튼 추가
    if st.button("웹훅 테스트", key="webhook_test"):
        test_data = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_count": 1,
            "data": [
                {
                    "company": "테스트 주식회사",
                    "report_date": "2024-03-13",
                    "cash_check_amount": 1000000,
                    "cash_check_ratio": 80.5,
                    "excess_amount": 200000,
                    "excess_ratio": 20.5,
                    "dispute_resolution": "설치"
                }
            ]
        }
        
        webhook_success = send_to_webhook(test_data)
        if webhook_success:
            st.success("✅ 웹훅 테스트 성공! Make.com에서 데이터를 확인하세요.")
        else:
            st.error("❌ 웹훅 테스트 실패. 로그를 확인하세요.")
    
    if st.button("DART 보고서 검색 및 데이터 추출", key="search_button"):
        if search_and_extract_data():
            st.success(f"✅ 총 {len(st.session_state.result_df)}개의 보고서 데이터를 추출했습니다.")
            
            # 데이터프레임 표시
            st.markdown("### 📊 추출 결과")
            st.dataframe(
                st.session_state.result_df,
                column_config={
                    "현금_수표_지급금액": st.column_config.NumberColumn(
                        "현금 및 수표 지급금액",
                        format="%d",
                        help="단위: 천원"
                    ),
                    "현금_수표_비중": st.column_config.NumberColumn(
                        "현금 및 수표 비중",
                        format="%.2f%%"
                    ),
                    "초과지급금액": st.column_config.NumberColumn(
                        "60일 초과 지급금액",
                        format="%d",
                        help="단위: 천원"
                    ),
                    "초과지급비중": st.column_config.NumberColumn(
                        "60일 초과 비중",
                        format="%.2f%%"
                    )
                }
            )
            
            # CSV 다운로드 버튼
            csv = st.session_state.result_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 CSV 파일 다운로드",
                data=csv,
                file_name="dart_report_data.csv",
                mime="text/csv"
            )
    
    # 이전 결과가 있는 경우 표시
    elif hasattr(st.session_state, 'result_df') and not st.session_state.result_df.empty:
        st.success(f"✅ 총 {len(st.session_state.result_df)}개의 보고서 데이터가 있습니다.")
        
        # 데이터프레임 표시
        st.markdown("### 📊 추출 결과")
        st.dataframe(
            st.session_state.result_df,
            column_config={
                "현금_수표_지급금액": st.column_config.NumberColumn(
                    "현금 및 수표 지급금액",
                    format="%d",
                    help="단위: 천원"
                ),
                "현금_수표_비중": st.column_config.NumberColumn(
                    "현금 및 수표 비중",
                    format="%.2f%%"
                ),
                "초과지급금액": st.column_config.NumberColumn(
                    "60일 초과 지급금액",
                    format="%d",
                    help="단위: 천원"
                ),
                "초과지급비중": st.column_config.NumberColumn(
                    "60일 초과 비중",
                    format="%.2f%%"
                )
            }
        )
        
        # CSV 다운로드 버튼
        csv = st.session_state.result_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 CSV 파일 다운로드",
            data=csv,
            file_name="dart_report_data.csv",
            mime="text/csv"
        ) 