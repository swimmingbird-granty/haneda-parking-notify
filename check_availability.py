"""
羽田空港P2・P3駐車場予約サイトの空き状況を監視し、
指定日(デフォルト: 7/26, 7/27)にP3一般車枠の空きが出ていたら
ntfy.sh経由でスマホに通知するスクリプト。

サイトの実際のソースを確認したところ、カレンダーは
  <table id="cal00"></table>  … P2 一般車枠
  <table id="cal10"></table>  … P3 一般車枠
という空のtableにJavaScript(calendar.js/yoyaku_calendar.js)がAJAXで
日付セルを描画する仕組みで、凡例のクラス名は
  tx_ok       … 空車
  tx_konzatsu … 混雑
  tx_full     … 満車
  tx_no       … 期間外
となっている(ログイン後の予約ページのソースより確認)。
この空車状況表示自体はトップページでもログイン不要で見られるため、
このスクリプトはログインせずトップページのみを見に行く。

【使い方】
1. pip install playwright
   playwright install chromium
2. スマホに ntfy アプリ(iOS/Android)をインストールし、
   NTFY_TOPIC で指定するトピック名を購読(Subscribe)しておく
3. 環境変数を設定して実行
   NTFY_TOPIC=haneda-p3-yourname123 python check_availability.py

【判定がうまくいかない場合】
DEBUG_DUMP_HTML を True にして実行すると、カレンダーtableの中身(HTML)を
そのまま標準出力に表示します。それをClaudeに貼ってもらえれば、
セル構造(日付の入れ方)に合わせて判定ロジックを調整できます。
"""

import os
import sys
import urllib.parse
import urllib.request
from playwright.sync_api import sync_playwright

TARGET_URL = "https://hnd-rsv.aeif.or.jp/airport2/app/toppage"
# 監視したい日付(月, 日)のリスト。デフォルトは7/26, 7/27
TARGET_DATES = [(7, 26), (7, 27)]
# P3(第2ターミナル)一般車枠のカレンダーのtable id
TABLE_ID = "cal10"

DEBUG_DUMP_HTML = True  # Trueにするとカレンダーtableのinner HTMLを出力する

# 空車・混雑・満車・期間外に対応するクラス名(サイトの凡例より判明済み)
BOOKABLE_CLASSES = ["tx_ok", "tx_konzatsu"]  # 空車 or 混雑 = 予約可能
UNAVAILABLE_CLASSES = ["tx_full", "tx_no"]   # 満車 or 期間外 = 予約不可

# ntfy.shのトピック名。第三者に推測されないよう、ランダムな文字列を混ぜた
# 名前にすることを推奨(トピック名を知っていれば誰でも購読・投稿できるため)
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh")


def send_ntfy_message(text: str, title: str = "羽田空港P3駐車場") -> None:
    """ntfy.sh経由で通知を送る"""
    if not NTFY_TOPIC:
        print("NTFY_TOPIC が未設定です。通知をスキップします。")
        print("送信予定メッセージ:", text)
        return

    # 日本語をHTTPヘッダーにそのまま入れるとエラーになるため、
    # title/priority/tagsはクエリパラメータで渡す(ntfyはこの方式に対応)
    params = urllib.parse.urlencode({
        "title": title,
        "priority": "high",
        "tags": "car",
    })
    url = f"{NTFY_SERVER}/{NTFY_TOPIC}?{params}"
    req = urllib.request.Request(
        url,
        data=text.encode("utf-8"),
        method="POST",
    )
    with urllib.request.urlopen(req) as res:
        print("ntfy通知送信結果:", res.status)


def find_day_status(page, table_id: str, day: int) -> str:
    """
    指定したtable(P2=cal00 / P3=cal10)・日にちのセル状態を返す。
    戻り値: "bookable"(空車or混雑=予約可能) / "unavailable"(満車or期間外) / "unknown"
    """
    table_selector = f"table#{table_id}"

    # AJAXでの描画完了を待つ(td要素が現れるまで)
    page.wait_for_selector(f"{table_selector} td", timeout=20000)

    # 日付セルはまず番号だけで描画され、空車/混雑/満車の色付け(class付与)は
    # 少し遅れて別処理で行われるようなので、いずれかのtdにclassが付くまで待つ
    try:
        page.wait_for_function(
            """(sel) => {
                const cells = document.querySelectorAll(sel + ' td');
                return Array.from(cells).some(td => td.className && td.className.trim() !== '');
            }""",
            arg=table_selector,
            timeout=20000,
        )
    except Exception:
        pass  # タイムアウトしても、この後の処理で unknown 判定になるだけなので続行する

    # 日にちの数字がテキストに含まれるtdを探す(前後に余分な要素があってもよいよう
    # normalize-spaceで完全一致 or 先頭一致を試す)
    cells = page.locator(f"{table_selector} td")
    count = cells.count()
    target_cell = None
    for i in range(count):
        cell = cells.nth(i)
        text = (cell.inner_text() or "").strip()
        # セル内テキストの先頭行が日にちの数字と一致するかチェック
        first_line = text.splitlines()[0].strip() if text else ""
        if first_line == str(day):
            target_cell = cell
            break

    if target_cell is None:
        return "unknown"  # 該当日が見つからない(月表示がズレている可能性)

    class_name = target_cell.get_attribute("class") or ""

    if any(c in class_name for c in BOOKABLE_CLASSES):
        return "bookable"
    if any(c in class_name for c in UNAVAILABLE_CLASSES):
        return "unavailable"
    return "unknown"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(TARGET_URL, wait_until="networkidle")

        # 色付け(class付与)が非同期で遅れて行われるようなので、少し待つ
        try:
            page.wait_for_function(
                """(sel) => {
                    const cells = document.querySelectorAll(sel + ' td');
                    return Array.from(cells).some(td => td.className && td.className.trim() !== '');
                }""",
                arg=f"table#{TABLE_ID}",
                timeout=20000,
            )
        except Exception:
            print("警告: classが付与されるのを待ちましたがタイムアウトしました。")

        if DEBUG_DUMP_HTML:
            table = page.locator(f"table#{TABLE_ID}")
            print(f"--- table#{TABLE_ID} innerHTML ---")
            print(table.inner_html())
            print("--- end ---")

        results = []
        for month, day in TARGET_DATES:
            status = find_day_status(page, TABLE_ID, day)
            results.append((month, day, status))
            print(f"{month}/{day}: {status}")

        browser.close()

        bookable_days = [f"{m}/{d}" for m, d, s in results if s == "bookable"]
        unknown_days = [f"{m}/{d}" for m, d, s in results if s == "unknown"]

        if unknown_days:
            print(
                f"判定不明の日付があります: {', '.join(unknown_days)}。"
                " DEBUG_DUMP_HTML=True で実行し、出力されたHTMLをClaudeに共有してください。"
            )

        if bookable_days:
            msg = f"羽田空港P3駐車場: {', '.join(bookable_days)} に空きが出ています!\n{TARGET_URL}"
            send_ntfy_message(msg)
        else:
            print("空きなし。通知は送信しません。")


if __name__ == "__main__":
    main()
