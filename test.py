import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
import time
import os
import pandas as pd
import re
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime
import json

# 🛠 Chrome WebDriver 경로 설정
CHROMEDRIVER_PATH = os.path.join(os.getcwd(), "chromedriver.exe")  # Windows용 경로

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
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    return options

# API 모드 확인
def is_api_mode():
    query_params = st.experimental_get_query_params()
    return 'api_request' in query_params

# 결과를 JSON으로 변환하는 함수
def convert_results_to_json(df):
    if df is not None and not df.empty:
        # 날짜 형식 변환
        df['접수일자'] = pd.to_datetime(df['접수일자']).dt.strftime('%Y-%m-%d')
        # 숫자 형식 변환
        for col in ['현금_수표_지급금액', '초과지급금액']:
            df[col] = df[col].astype(float)
        for col in ['현금_수표_비중', '초과지급비중']:
            df[col] = df[col].astype(float)
        
        result = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_count": len(df),
            "data": df.to_dict('records')
        }
        return result
    return {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "total_count": 0, "data": []}

# Streamlit 제목
if not is_api_mode():
    st.title("📄 DART 보고서 크롤링 AI Agent")
    st.subheader("DART 보고서를 자동으로 크롤링합니다.")

# ChromeDriver 존재 여부 확인
if not os.path.exists(CHROMEDRIVER_PATH):
    st.error("❌ ChromeDriver가 설치되지 않았습니다. 'chromedriver.exe'를 현재 폴더에 설치해주세요.")
    st.stop()

# 검색 설정
target_report = "지급수단별ㆍ지급기간별지급금액및분쟁조정기구에관한사항"

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

# 세션 상태 초기화
if 'found_reports' not in st.session_state:
    st.session_state.found_reports = None
if 'extracted_data' not in st.session_state:
    st.session_state.extracted_data = {}

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
        
        # 디버깅: 전체 페이지 텍스트 출력
        page_text = driver.find_element(By.TAG_NAME, "body").text
        st.text("페이지 텍스트:")
        st.code(page_text[:2000])
        
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
            st.warning(f"현금 및 수표 데이터 추출 중 오류: {str(e)}")
        
        # 2. (제2호) 60일 초과 데이터 추출
        try:
            # 지급기간별 지급금액 테이블 찾기
            tables = driver.find_elements(By.XPATH, "//p[contains(text(), '2. (제2호) 지급기간별 지급금액')]/following::table[contains(@border, '1')]")
            if tables:
                table = tables[0]
                rows = table.find_elements(By.TAG_NAME, "tr")
                
                # 지급금액 행 찾기 (첫 번째 데이터 행)
                for row in rows:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 6 and "지급금액" in cells[0].text:
                        # 60일 초과 열은 마지막 열
                        amount_text = cells[-1].text.strip()
                        if amount_text and amount_text != "-":
                            numbers = re.findall(r'\d{1,3}(?:,\d{3})*(?:\.\d+)?', amount_text)
                            if numbers:
                                data["초과지급금액"] = numbers[0].replace(",", "")
                
                # 비중 행 찾기 (두 번째 데이터 행)
                for row in rows:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 6 and "비중" in cells[0].text:
                        # 60일 초과 열은 마지막 열
                        ratio_text = cells[-1].text.strip()
                        if ratio_text and ratio_text != "-":
                            ratio_text = ratio_text.replace("%", "").strip()
                            numbers = re.findall(r'\d+\.\d+|\d+', ratio_text)
                            if numbers:
                                data["초과지급비중"] = numbers[0]
        except Exception as e:
            st.warning(f"60일 초과 데이터 추출 중 오류: {str(e)}")
        
        # 3. (제3호) 분쟁조정기구 설치 여부
        try:
            tables = driver.find_elements(By.XPATH, "//p[contains(text(), '3. (제3호) 분쟁조정기구')]/following::table")
            installed = False
            
            for table in tables:
                # 더 정확한 XPath 선택자 사용
                rows = table.find_elements(By.XPATH, ".//tr[.//td[contains(text(), '분쟁조정기구 설치 여부')] or .//th[contains(text(), '분쟁조정기구 설치 여부')]]")
                if rows:
                    cells = rows[0].find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 2:
                        status = cells[1].text.strip()
                        # 더 엄격한 텍스트 정규화 및 비교
                        normalized_status = status.upper().replace(" ", "")
                        if any(mark in normalized_status for mark in ["O", "○", "◯", "0"]):
                            installed = True
                            break
                        elif "X" in normalized_status:
                            installed = False
                            break
            
            if installed:
                data["분쟁조정기구"] = "설치"
            else:
                data["분쟁조정기구"] = "미설치"
        
        except Exception as e:
            st.warning(f"분쟁조정기구 데이터 추출 중 오류: {str(e)}")
        
        return data
        
    except Exception as e:
        st.error(f"보고서 조회 중 오류 발생: {str(e)}")
        return None

def display_report(row, idx, location):
    rcpNo = row['rcpNo']
    
    with st.container():
        st.markdown("""
        <style>
        .report-container {
            border: 1px solid #ddd;
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
        }
        </style>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns([7, 3])
        
        with col1:
            st.markdown(f"""
            <div class="report-container">
                <p><strong>공시대상회사:</strong> {row['공시대상회사']}</p>
                <p><strong>접수일자:</strong> {row['접수일자']}</p>
                <p><strong>보고서명:</strong> <a href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcpNo}" target="_blank">{row['보고서명']}</a></p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            if rcpNo in st.session_state.extracted_data:
                st.success("✅ 데이터 추출 완료")
                data = st.session_state.extracted_data[rcpNo]
                st.markdown("### 📊 추출 데이터")
                st.markdown(f"""
                **1. 현금 및 수표**
                - 지급금액: {data['현금_수표_지급금액']}
                - 비중: {data['현금_수표_비중']}
                
                **2. 60일 초과**
                - 지급금액: {data['초과지급금액']}
                - 비중: {data['초과지급비중']}
                
                **3. 분쟁조정기구**
                - 설치여부: {data['분쟁조정기구']}
                """)
            else:
                extract_button = st.button("📊 데이터 추출", key=f"extract_{rcpNo}_{idx}_{location}")
                if extract_button:
                    with st.spinner("⏳ 데이터 추출 중..."):
                        options = setup_chrome_options()
                        service = Service(ChromeDriverManager().install())
                        with webdriver.Chrome(service=service, options=options) as driver:
                            data = extract_report_data(driver, rcpNo)
                            if data:
                                st.session_state.extracted_data[rcpNo] = data
                                st.success("✅ 데이터 추출 완료")
                                st.markdown("### 📊 추출 데이터")
                                st.markdown(f"""
                                **1. 현금 및 수표**
                                - 지급금액: {data['현금_수표_지급금액']}
                                - 비중: {data['현금_수표_비중']}
                                
                                **2. 60일 초과**
                                - 지급금액: {data['초과지급금액']}
                                - 비중: {data['초과지급비중']}
                                
                                **3. 분쟁조정기구**
                                - 설치여부: {data['분쟁조정기구']}
                                """)
                            else:
                                st.error("❌ 데이터 추출 실패")

def search_dart_for_company(driver, wait, company_name, stock_code=None):
    """회사별 DART 검색 함수 - 종목코드 우선 검색"""
    found_company_reports = []
    
    try:
        # 검색 페이지 접속
        driver.get("https://dart.fss.or.kr/dsab007/main.do?option=report")
        time.sleep(3)
        
        try:
            # 보고서명 입력
            report_input = wait.until(
                EC.presence_of_element_located((By.ID, "reportName"))
            )
            report_input.clear()
            report_input.send_keys(target_report)
            time.sleep(2)

            if stock_code:  # 종목코드가 있는 경우
                # 회사명/종목코드 입력 필드에 종목코드 입력
                company_input = wait.until(
                    EC.presence_of_element_located((By.ID, "textCrpNm2"))
                )
                company_input.clear()
                company_input.send_keys(stock_code)
                time.sleep(1)
                # 엔터키 입력으로 자동완성 트리거
                company_input.send_keys(Keys.RETURN)
                time.sleep(2)
            else:  # 종목코드가 없는 경우
                # 회사명/종목코드 입력 필드에 회사명 입력
                company_input = wait.until(
                    EC.presence_of_element_located((By.ID, "textCrpNm2"))
                )
                company_input.clear()
                company_input.send_keys(company_name)
                time.sleep(1)
                # 엔터키 입력으로 자동완성 트리거
                company_input.send_keys(Keys.RETURN)
                time.sleep(2)
            
            # JavaScript로 검색 함수 직접 호출
            driver.execute_script("search(1, 'btn');")
            time.sleep(3)
            
            # 결과 테이블 확인
            try:
                table = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table.tbList"))
                )
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
                            
                            if target_report in report_title:
                                rcpNo = report_href.split("rcpNo=")[-1].split("&")[0] if "rcpNo=" in report_href else None
                                found_company_reports.append({
                                    "공시대상회사": found_company,
                                    "접수일자": report_date,
                                    "보고서명": report_title,
                                    "rcpNo": rcpNo
                                })
                    except Exception as inner_e:
                        continue
                
            except Exception as e:
                st.warning(f"{company_name} 결과 처리 중 오류: {str(e)}")
                
        except Exception as e:
            st.warning(f"{company_name} 검색 양식 입력 중 오류: {str(e)}")
        
    except Exception as e:
        st.error(f"{company_name} 검색 과정 중 오류: {str(e)}")
    
    return found_company_reports

def search_and_extract_data():
    found_reports = []
    result_data = []
    
    try:
        with st.spinner("🔍 보고서를 검색하고 데이터를 추출 중입니다..."):
            options = setup_chrome_options()
            # Streamlit Cloud 환경에서 ChromeDriver 설정
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            wait = WebDriverWait(driver, 10)
            
            # 종목코드가 있는 회사 먼저 검색
            for stock_code, company_name in stock_codes.items():
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
                    st.success(f"✅ {company_name}: {len(company_reports)}개 보고서 데이터 추출 완료")
                else:
                    st.warning(f"⚠️ {company_name}: 보고서를 찾을 수 없습니다.")
            
            # 종목코드가 없는 회사 검색
            for company_name in company_names:
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
                    st.success(f"✅ {company_name}: {len(company_reports)}개 보고서 데이터 추출 완료")
        else:
                    st.warning(f"⚠️ {company_name}: 보고서를 찾을 수 없습니다.")

        driver.quit()

        if result_data:
            st.session_state.result_df = pd.DataFrame(result_data)
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
if not is_api_mode():
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

elif hasattr(st.session_state, 'result_df') and not st.session_state.result_df.empty:
    st.success(f"✅ 총 {len(st.session_state.result_df)}개의 보고서 데이터가 있습니다.")
    
    # 저장된 데이터프레임 표시
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

else:
    # API 모드
    if search_and_extract_data():
        result_json = convert_results_to_json(st.session_state.result_df)
        st.json(result_json)
    else:
        st.json({"error": "데이터 추출 실패", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})