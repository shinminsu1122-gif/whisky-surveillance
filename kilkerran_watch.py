#!/usr/bin/env python3
"""
tyndrumwhisky.com 의 Glengyle(Kilkerran) 증류소 페이지를 감시해서
'Kilkerran 16 ... 2026' 관련 신상품이 뜨면 이메일로 알려주는 스크립트.

사용법:
1) 아래 CONFIG 값들을 본인 환경에 맞게 채운다.
2) `pip install requests beautifulsoup4` 로 필요한 패키지 설치.
3) cron / 작업 스케줄러 / GitHub Actions 등으로 이 스크립트를
   원하는 주기(예: 1시간마다)로 실행되게 등록한다.

동작 방식:
- 감시 대상 페이지를 매번 새로 받아서, 상품 링크 목록을 뽑는다.
- 그 중 KEYWORDS 에 있는 단어를 전부 포함하는 링크가 있고,
  그게 이전에 알림을 보낸 적 없는 새 링크라면 이메일을 보낸다.
- 이미 알림 보낸 링크는 seen_links.json 에 기록해서 중복 알림을 막는다.
"""

import json
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from pathlib import Path

import cloudscraper
from bs4 import BeautifulSoup

# ========== CONFIG: 본인 환경에 맞게 채우세요 ==========

WATCH_URL = "https://www.tyndrumwhisky.com/glengyle-distillery.html"

# 신상품 링크의 텍스트/URL 안에 이 단어들이 "전부" 들어있으면 알림 대상으로 판단.
# 소문자 기준으로 비교하니 소문자로 적어두면 됨.
KEYWORDS = ["kilkerran", "16", "2026"]

# 이메일 발송 설정 (Gmail 기준 예시)
# GitHub Actions의 Secrets 값(환경변수)이 있으면 그걸 우선 쓰고,
# 없으면(=내 컴퓨터에서 직접 실행할 때) 아래 기본값을 씀.
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "your_gmail_address@gmail.com")
SENDER_APP_PASSWORD = os.environ.get("SENDER_APP_PASSWORD", "xxxx xxxx xxxx xxxx")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL", "your_receiver_address@example.com")

# 이미 알림 보낸 링크를 기록해두는 파일 (스크립트와 같은 폴더에 생성됨)
STATE_FILE = Path(__file__).parent / "seen_links.json"

# =======================================================


def fetch_product_links(url: str) -> dict[str, str]:
    """페이지에서 상품으로 보이는 링크들을 {url: 텍스트} 형태로 뽑아온다."""
    # cloudscraper 는 Cloudflare 등 봇 차단을 우회하도록 만들어진
    # requests 의 확장판이라, 일반 requests 보다 성공 확률이 높다.
    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "darwin", "mobile": False}
    )
    resp = scraper.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    links = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        # 상품 상세 페이지로 보이는 .html 링크만 대상으로 (메뉴/카테고리 링크 대충 제외)
        if href.endswith(".html") and "tyndrumwhisky.com" in href:
            links[href] = text
    return links


def load_seen() -> set[str]:
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    return set()


def save_seen(seen: set[str]) -> None:
    STATE_FILE.write_text(
        json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def matches_keywords(url: str, text: str) -> bool:
    haystack = (url + " " + text).lower()
    return all(kw.lower() in haystack for kw in KEYWORDS)


def send_email(subject: str, body: str) -> None:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
        server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, [RECEIVER_EMAIL], msg.as_string())


def main() -> None:
    seen = load_seen()
    links = fetch_product_links(WATCH_URL)

    new_matches = {
        url: text
        for url, text in links.items()
        if matches_keywords(url, text) and url not in seen
    }

    if not new_matches:
        print("새로운 매칭 상품 없음.")
        return

    for url, text in new_matches.items():
        subject = f"[재입고 알림] {text or 'Kilkerran 16 (2026)'}"
        body = (
            f"tyndrumwhisky.com 에 새 상품이 발견되었습니다.\n\n"
            f"상품명: {text}\n"
            f"링크: {url}\n"
        )
        try:
            send_email(subject, body)
            print(f"알림 발송 완료: {url}")
        except Exception as e:
            print(f"이메일 발송 실패 ({url}): {e}")
            continue  # 실패하면 seen 에 기록하지 않고 다음에 재시도

        seen.add(url)

    save_seen(seen)


if __name__ == "__main__":
    main()
