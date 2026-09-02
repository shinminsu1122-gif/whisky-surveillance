#!/usr/bin/env python3
"""
sites.json 에 등록된 여러 위스키 사이트를 감시해서,
Springbank / Kilkerran 16 (2026) 관련 신상품이 뜨면 이메일로 알려주는 스크립트.

사용법:
1) sites.json 에서 감시할 사이트/페이지 목록과 keyword_sets 를 원하는 대로 수정.
2) 이 스크립트와 sites.json 을 같은 폴더에 둔다.
3) `pip install requests beautifulsoup4 cloudscraper` 로 필요한 패키지 설치.
4) cron / GitHub Actions 등으로 주기 실행되게 등록.

동작 방식:
- sites.json 의 사이트들을 하나씩 방문해서 상품 링크 목록을 뽑는다.
- keyword_sets 안의 키워드 묶음 중 하나라도 링크 텍스트/URL에 전부 포함되면
  "매칭"으로 판단한다. (예: ["springbank"] 만 있으면 springbank 가 들어간
  모든 링크가 매칭됨. ["kilkerran", "16", "2026"] 처럼 여러 단어를 넣으면
  그 단어들이 다 있어야 매칭됨)
- 이전에 알림 보낸 적 없는 새 매칭 링크만 이메일로 발송.
- 이미 알림 보낸 링크는 seen_links.json 에 사이트별로 기록해서 중복 알림 방지.
"""

import json
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from pathlib import Path

import cloudscraper
from bs4 import BeautifulSoup

# ========== CONFIG ==========

SITES_FILE = Path(__file__).parent / "sites.json"
STATE_FILE = Path(__file__).parent / "seen_links.json"

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "your_gmail_address@gmail.com")
SENDER_APP_PASSWORD = os.environ.get("SENDER_APP_PASSWORD", "xxxx xxxx xxxx xxxx")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL", "your_receiver_address@example.com")

# =============================


def load_config() -> dict:
    return json.loads(SITES_FILE.read_text(encoding="utf-8"))


def load_seen() -> set[str]:
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    return set()


def save_seen(seen: set[str]) -> None:
    STATE_FILE.write_text(
        json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def fetch_product_links(url: str, domain_hint: str) -> dict[str, str]:
    """페이지에서 상품으로 보이는 링크들을 {url: 텍스트} 형태로 뽑아온다."""
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
        if domain_hint in href and len(text) > 3:
            links[href] = text
    return links


def matches_any_keyword_set(url: str, text: str, keyword_sets: list[list[str]]) -> bool:
    haystack = (url + " " + text).lower()
    for keywords in keyword_sets:
        if all(kw.lower() in haystack for kw in keywords):
            return True
    return False


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
    config = load_config()
    sites = config["sites"]
    keyword_sets = config["keyword_sets"]

    seen = load_seen()
    total_new = 0

    for site in sites:
        name = site["name"]
        url = site["url"]
        domain_hint = site["domain_hint"]

        print(f"[확인 중] {name} ({url})")
        try:
            links = fetch_product_links(url, domain_hint)
        except Exception as e:
            print(f"  -> 접속 실패: {e}")
            continue

        new_matches = {
            link_url: text
            for link_url, text in links.items()
            if matches_any_keyword_set(link_url, text, keyword_sets)
            and link_url not in seen
        }

        if not new_matches:
            print("  -> 새로운 매칭 상품 없음.")
            continue

        for link_url, text in new_matches.items():
            subject = f"[재입고/신상품 알림] {text or name}"
            body = (
                f"{name} 에서 새 상품이 발견되었습니다.\n\n"
                f"상품명: {text}\n"
                f"링크: {link_url}\n"
            )
            try:
                send_email(subject, body)
                print(f"  -> 알림 발송 완료: {link_url}")
            except Exception as e:
                print(f"  -> 이메일 발송 실패 ({link_url}): {e}")
                continue

            seen.add(link_url)
            total_new += 1

    if total_new:
        save_seen(seen)
    print(f"\n완료. 새로 발송한 알림 개수: {total_new}")


if __name__ == "__main__":
    main()
