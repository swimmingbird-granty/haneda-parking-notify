"""
羽田空港P3(第2ターミナル)一般車枠の空き状況を監視し、
7/26・7/27のいずれかが「満車」「期間外」以外(=予約可能)になったら
ntfy.sh経由でスマホに通知するスクリプト(requests版・GitHub Actions用)。

サイトが内部で使っているJSON API(/airport2/app/calendar)を直接叩くので、
Playwright(ブラウザ操作)は不要。

【前回の状態の保存について】
GitHub Actionsは実行のたびに環境がまっさらになるため、前回チェック時の
状態を state.json というファイルに書き出し、actions/cache で
ワークフローの前後に保存・復元する(詳細はワークフローファイル側を参照)。
"""

import json
import os
import re
import sys
import urllib.parse

import requests

TOP_URL = "https://hnd-rsv.aeif.or.jp/airport2/app/toppage"
CALENDAR_API_URL = "https://hnd-rsv.aeif.or.jp/airport2/app/calendar"

# P3(第2ターミナル)一般車枠 = area:1, handicapped:0 (サイトのHTML構造・実測から確認済み)
AREA = "1"
HANDICAPPED = "0"

# 監視したい日付(2桁の文字列。1桁の日付を含める場合は "01" のようにゼロ埋めすること)
TARGET_DAYS = ["24", "25", "26", "27", "28", "29", "30", "31"]

STATE_FILE = "state.json"

NTFY_TOPIC = os.environ.get("NTFY_TOPIC")
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh")


def fetch_calendar_status():
    session = requests.Session()
    top_res = session.get(TOP_URL, timeout=20)
    top_res.raise_for_status()

    m = re.search(r'id="token_header_token">([^<]+)<', top_res.text)
    if not m:
        print("CSRFトークンが取得できませんでした。サイトの構造が変わった可能性があります。")
        sys.exit(1)
    csrf_token = m.group(1)

    payload = {"date": "", "area": AREA, "handicapped": HANDICAPPED}
    cal_res = session.post(
        CALENDAR_API_URL,
        json=payload,
        headers={
            "X-CSRF-TOKEN": csrf_token,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": TOP_URL,
        },
        timeout=20,
    )
    cal_res.raise_for_status()
    return cal_res.json()


def send_ntfy_message(text: str, title: str = "羽田空港P3駐車場") -> None:
    if not NTFY_TOPIC:
        print("NTFY_TOPIC が未設定です。通知をスキップします。")
        print("送信予定メッセージ:", text)
        return

    params = urllib.parse.urlencode({"title": title, "priority": "high", "tags": "car"})
    url = f"{NTFY_SERVER}/{NTFY_TOPIC}?{params}"
    res = requests.post(url, data=text.encode("utf-8"), timeout=20)
    print("ntfy通知送信結果:", res.status_code)


def load_previous_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_bookable_days": []}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def main():
    data = fetch_calendar_status()
    month_prefix = data.get("date")  # 例: "2026/07"
    calendar = data.get("yoyakuCalendar", [])

    bookable_days = []
    unknown_days = []

    for day in TARGET_DAYS:
        padded_day = day.zfill(2)
        target_date = f"{month_prefix}/{padded_day}"
        # 「日にちの数字」だけでなく年月を含めた完全一致で照合する
        # (前月・翌月にも同じ日にちの数字が重複して登場するため)
        entry = next((e for e in calendar if e.get("date") == target_date), None)

        if entry is None:
            unknown_days.append(day)
            continue

        status = entry.get("status", "")
        print(f"{day}日: status={status!r}")

        if status not in ("", "full"):
            bookable_days.append(f"{day}日({status})")

    if unknown_days:
        print(f"該当日が見つかりませんでした(月表示がズレている可能性): {', '.join(unknown_days)}")

    prev_state = load_previous_state()
    prev_bookable = prev_state.get("last_bookable_days", [])

    if bookable_days != prev_bookable:
        if bookable_days:
            msg = f"羽田空港P3駐車場: {', '.join(bookable_days)} に空きが出ています!\n{TOP_URL}"
            send_ntfy_message(msg)
        else:
            print(f"空きが無くなりました(前回: {prev_bookable})。通知はしません。")
        save_state({"last_bookable_days": bookable_days})
    else:
        print(f"前回チェック時と状態が同じなので通知はスキップします。現在: {bookable_days}")


if __name__ == "__main__":
    main()
