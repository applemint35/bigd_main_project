"""
하루 3회(장이 열리는 날 오전 10시/12시/2시) 실행되는 알림 스크립트.
관심종목(watchlist.csv)의 현재가를 네이버 API로 조회해 텔레그램 텍스트 메시지로 보내고,
Turso DB에 쌓아 둔 과거 종가와 오늘 분봉으로 추이 그래프를 종목별로 그려 sendPhoto로 전송한다.

send_price_notification()으로 알림 로직 전체를 함수 하나에 감싸 두었다.
`python notify_stock_price.py`로 직접 실행하면 그 함수가 그대로 실행된다.
"""
import html

from stock_utils import (
    read_watchlist,
    load_price_history,
    fetch_naver_current_price,
    fetch_naver_intraday_minutes,
    send_telegram_message,
    send_telegram_photo,
    describe_price_trend,
    format_rate_badge,
    dedupe_daily_closes,
    resolve_today_price,
    build_price_chart,
)


def send_price_notification() -> bool:
    """관심종목 현재가 텍스트 메시지와 종목별 추이 그래프를 텔레그램으로 전송합니다.

    관심종목을 하나라도 처리했으면 True, 아무것도 하지 못했으면 False를 반환합니다.
    여기서 "아무것도 하지 못했다"에는 조회에 전부 실패한 경우뿐 아니라 조회는 됐는데
    텔레그램 전송이 전부 실패한 경우도 포함됩니다.
    """
    watchlist_codes = read_watchlist()
    if watchlist_codes is None:
        return False

    # 1. 네이버 API로 현재가 조회 후 텔레그램 텍스트 메시지 전송
    print("🚀 관심종목 현재가 조회 시작...")

    current_prices = {}  # code -> fetch_naver_current_price() 결과
    telegram_message = "📊 <b>내 관심종목 현재가</b>"

    for code in watchlist_codes:
        info = fetch_naver_current_price(code)
        if info is None:
            continue

        current_prices[code] = info

    if not current_prices:
        print("❌ 관심종목의 현재가를 하나도 가져오지 못했습니다. 네이버 API 상태를 확인해 주세요.")
        return False

    # 2. DB에 쌓아둔 종가와 오늘 분봉으로 그래프 생성 및 전송
    price_history = load_price_history()
    intraday_by_code = {code: fetch_naver_intraday_minutes(code) for code in current_prices}

    first_code = next(iter(current_prices))
    first_info = current_prices[first_code]
    first_daily_closes = price_history.get(first_code, [])
    first_intraday_minutes = intraday_by_code[first_code]
    first_today_price = resolve_today_price(
        first_info["price"],
        first_info["is_open"],
        first_intraday_minutes,
        first_daily_closes,
    )
    first_daily_closes = dedupe_daily_closes(
        first_daily_closes,
        first_today_price,
        first_intraday_minutes,
    )
    telegram_message += f"\n\n{describe_price_trend(first_daily_closes, first_intraday_minutes)}"

    sent = 0

    if send_telegram_message(telegram_message):
        sent += 1
        print("✅ 현재가 메시지를 텔레그램으로 전송했습니다!")
    else:
        print("❌ 현재가 메시지 전송에 실패했습니다.")

    for code, info in current_prices.items():
        daily_closes = price_history.get(code, [])
        if not daily_closes:
            print(
                f"⚠️ [{code}] 저장된 종가 히스토리가 없어 현재가만으로 그래프를 그립니다. "
                f"collect_daily_close.py가 아직 한 번도 실행되지 않았을 수 있습니다."
            )

        intraday_minutes = intraday_by_code[code]
        today_price = resolve_today_price(
            info["price"],
            info["is_open"],
            intraday_minutes,
            daily_closes,
        )
        chart_buffer = build_price_chart(daily_closes, today_price, intraday_minutes)
        caption = (
            f"📈 <b>{html.escape(info['name'])}</b> ({code})\n"
            f"    {format_rate_badge(info['price'], info['rate'])}"
        )

        if send_telegram_photo(chart_buffer, caption):
            sent += 1
            print(f"🎉 [{code}] 추이 그래프를 텔레그램으로 전송했습니다!")
        else:
            print(f"❌ [{code}] 추이 그래프 전송에 실패했습니다.")

    if sent == 0:
        print("❌ 텔레그램으로 아무것도 전송하지 못했습니다. 봇 토큰과 텔레그램 API 상태를 확인해 주세요.")
        return False

    return True


if __name__ == "__main__":
    send_price_notification()