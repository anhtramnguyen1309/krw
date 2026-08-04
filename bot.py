import re
import asyncio
import requests
import json
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes


BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = 1555474257  # ← Thay bằng Telegram user ID của bạn

USAGE_FILE = 'user_usage.json'
PAID_USERS_FILE = 'paid_users.json'
MAX_FREE_USAGE = 10

# ====== Quản lý dữ liệu ======
def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, 'r') as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f)

# ====== Theo dõi lượt dùng ======
def increment_usage(user_id):
    usage = load_json(USAGE_FILE)
    user_id = str(user_id)
    usage[user_id] = usage.get(user_id, 0) + 1
    save_json(USAGE_FILE, usage)
    return usage[user_id]

from datetime import datetime, timedelta

def is_paid_user(user_id):
    paid_users = load_json(PAID_USERS_FILE)
    user_id = str(user_id)
    if user_id not in paid_users:
        return False
    
    try:
        paid_date = datetime.strptime(paid_users[user_id], "%Y-%m-%d")
        return datetime.now() <= paid_date + timedelta(days=2)
    except:
        return False

from datetime import datetime, timezone, timedelta

def add_paid_user(user_id):
    paid_users = load_json(PAID_USERS_FILE)
    
    # Lấy thời gian hiện tại theo múi giờ Hàn Quốc (UTC+9)
    korea_time = datetime.now(timezone(timedelta(hours=9)))
    
    # Ghi lại ngày theo định dạng YYYY-MM-DD
    paid_users[str(user_id)] = korea_time.strftime("%Y-%m-%d")
    
    save_json(PAID_USERS_FILE, paid_users)


# ------------------- Rate fetching functions -------------------
def get_binance_p2p_usdt_prices():
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type": "application/json"}

    def get_price(trade_type):
        data = {
            "asset": "USDT",
            "fiat": "VND",
            "merchantCheck": False,
            "page": 1,
            "payTypes": [],
            "publisherType": None,
            "rows": 1,
            "tradeType": trade_type,
            "transAmount": "500000000",
        }
        res = requests.post(url, headers=headers, json=data).json()
        return float(res['data'][0]['adv']['price'])

    buy_price = get_price("BUY")
    sell_price = get_price("SELL")
    return buy_price, sell_price

def get_binance_price(symbol):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    return float(requests.get(url).json()['price'])

def get_bithumb_price(symbol):
    url = f"https://api.bithumb.com/public/ticker/{symbol}_KRW"
    return float(requests.get(url).json()['data']['closing_price'])

async def fetch_giacoin_text():
    usdt_buy, usdt_sell = get_binance_p2p_usdt_prices()
    coins = ["USDT", "XRP", "TRX", "BTC", "ETH"]
    result = "#TỶ GIÁ COIN\n\n"

    for coin in coins:
        if coin == "USDT":
            bithumb_price = get_bithumb_price("USDT")
            krw_rate_buy = round(usdt_buy / bithumb_price, 3)
            krw_rate_sell = round(usdt_sell / bithumb_price, 3)
            result += (
                f"{coin}\n"
                f" 💰Buy: {usdt_buy:,.0f} VND\n"
                f" 💸Sell: {usdt_sell:,.0f} VND\n"
                f" 🏦Bithumb: {int(bithumb_price):,} KRW\n"
                f" 💹USDT➜KRW: {krw_rate_buy}\n"
                f" 💹KRW➜USDT: {krw_rate_sell}\n\n"
            )
        else:
            binance_usdt = get_binance_price(f"{coin}USDT")
            bithumb_krw = get_bithumb_price(coin)
            krw_rate_buy = round(usdt_buy / (bithumb_krw / binance_usdt), 2)
            krw_rate_sell = round(usdt_sell / (bithumb_krw / binance_usdt), 2)
            result += (
                f"{coin}\n"
                f" 📊Binance: {binance_usdt:.5f} USDT\n"
                f" 🏦Bithumb: {int(bithumb_krw):,} KRW\n"
                f" 💹USDT➜KRW: {krw_rate_buy}\n"
                f" 💹KRW➜USDT: {krw_rate_sell}\n\n"
            )
    return result

# ------------------- Telegram Command Handler -------------------


async def check_giacoin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    usage_count = increment_usage(user_id)  # ✅ luôn tăng lượt dùng, kể cả user trả phí

    if is_paid_user(user_id):
        # Người dùng đã thanh toán còn hạn -> tiếp tục
        pass
    else:
        if str(user_id) in load_json(PAID_USERS_FILE):
            # Người từng thanh toán nhưng đã hết hạn
            await update.message.reply_text(
                "❌ Gói sử dụng của bạn đã hết hạn sau 30 ngày.\n"
                "👉 Vui lòng thanh toán lại để tiếp tục sử dụng."
            )
            return
        elif usage_count > MAX_FREE_USAGE:
            # Người chưa từng thanh toán, vượt quá 10 lượt
            await update.message.reply_text(
                "❗Bạn đã dùng thử *10 lần miễn phí*.\n"
                "👉 Vui lòng thanh toán để tiếp tục sử dụng:\n"
                "👉 199.000đ / 1 Tháng"
            )
            return

    # ✅ Nếu vượt qua các điều kiện trên thì xử lý bình thường
    msg = await update.message.reply_text("⏳ Đang lấy tỷ giá, vui lòng chờ...")
    try:
        text = await fetch_giacoin_text()
        await msg.edit_text(text)
    except Exception as e:
        await msg.edit_text("❌ Lỗi khi lấy tỷ giá: " + str(e))



from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import CommandHandler, ApplicationBuilder, ContextTypes

from telegram import ReplyKeyboardMarkup

ADMIN_ID = 1555474257  # Thay bằng user_id của bạn

def get_reply_markup(user_id):
    if user_id == ADMIN_ID:
        keyboard = [
            ["/check_giacoin","/log_user"],
            ["/thanhtoan", "/mokhoa"],
            ["/xoa_user"]
        ]
    else:
        keyboard = [
            ["/check_giacoin","/hsd"],
            ["/thanhtoan"],
        ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "Không xác định"
    log_user(user_id, first_name)  # Gọi hàm lưu thông tin user

    increment_usage(user_id)  # ✅ Ghi nhận lượt dùng
    reply_markup = get_reply_markup(user_id)

    await update.message.reply_text(
        "Chào bạn! Chọn chức năng bên dưới:",
        reply_markup=reply_markup
    )

async def thanhtoan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Vui lòng thanh toán:\n\n"
        "💳 *Ngân hàng:* Vietcombank\n"
        "👤 *Chủ tài khoản:* NGUYEN THI THAM\n"
        "🔢 *Số tài khoản:* 2387180867\n\n"
        "Sau khi chuyển khoản, bạn hãy gửi tin nhắn đến *@JoyceNguyenzz* để được kích hoạt."
    )
    await update.message.reply_text(text, parse_mode="Markdown")
from datetime import datetime, timedelta

def is_paid_user(user_id):
    paid_users = load_json(PAID_USERS_FILE)
    date_str = paid_users.get(str(user_id))
    if not date_str:
        return False
    try:
        paid_date = datetime.strptime(date_str, "%Y-%m-%d")
        return datetime.now() - paid_date < timedelta(days=30)
    except:
        return False


async def mokhoa(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Bạn không có quyền sử dụng lệnh này.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("📌 Dùng đúng cú pháp: /mokhoa <user_id>")
        return

    target_id = context.args[0]
    add_paid_user(target_id)
    await update.message.reply_text(f"✅ Đã mở khóa cho user_id: {target_id}")
LOGGED_USERS_FILE = 'logged_users.json'

async def xoa_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Bạn không có quyền sử dụng lệnh này.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("📌 Dùng đúng cú pháp: /xoa_user <user_id>")
        return

    target_id = context.args[0]
    # Xóa khỏi paid_users
    paid_users = load_json(PAID_USERS_FILE)
    if target_id in paid_users:
        del paid_users[target_id]
        save_json(PAID_USERS_FILE, paid_users)

    # Xóa khỏi user_usage
    usage = load_json(USAGE_FILE)
    if target_id in usage:
        del usage[target_id]
        save_json(USAGE_FILE, usage)

    await update.message.reply_text(f"✅ Đã xóa user_id {target_id} khỏi hệ thống.")


from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime

async def log_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = 1555474257  # Thay bằng user_id của bạn
    if update.effective_user.id != admin_id:
        return  # Chỉ admin được phép xem

    usage_data = load_json(USAGE_FILE)
    paid_users = load_json(PAID_USERS_FILE)

    result = "📋 *Danh sách người dùng:*\n\n"
    for user_id_str, usage_count in usage_data.items():
        user_id = int(user_id_str)
        is_paid = "✅" if user_id_str in paid_users else "❌"
        paid_date = paid_users.get(user_id_str, "—")

        try:
            user_info = await context.bot.get_chat(user_id)
            name = user_info.full_name or user_info.username or "Không rõ"
        except:
            name = "Không xác định"

        result += (
            f"👤 [{user_id}](tg://user?id={user_id}) - {name}\n"

            f"   ➤ Dùng: {usage_count} lần | 🗓️: {paid_date}\n\n"
        )

    await update.message.reply_text(result, parse_mode="Markdown")
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

PAID_USERS_FILE = "paid_users.json"

def load_json(path):
    import json, os
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)

async def hsd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    paid_users = load_json(PAID_USERS_FILE)

    if user_id not in paid_users:
        await update.message.reply_text("❌ Bạn chưa thanh toán hoặc đã hết hạn sử dụng.")
        return

    try:
        paid_date = datetime.strptime(paid_users[user_id], "%Y-%m-%d")
        remaining = (paid_date + timedelta(days=30)) - datetime.now()
        days_left = remaining.days

        if days_left < 0:
            await update.message.reply_text("⚠️ Hạn sử dụng của bạn đã hết. Vui lòng thanh toán lại.")
        else:
            await update.message.reply_text(
                f"⏳ Hạn sử dụng còn lại: *{days_left}* ngày (kể từ {paid_date.strftime('%d/%m/%Y')})",
                parse_mode="Markdown"
            )
    except Exception as e:
        await update.message.reply_text("⚠️ Lỗi khi kiểm tra hạn sử dụng.")



# Hàm main
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check_giacoin", check_giacoin))
    app.add_handler(CommandHandler("thanhtoan", thanhtoan))  # ✅ Thêm dòng này
    app.add_handler(CommandHandler("mokhoa", mokhoa))
    app.add_handler(CommandHandler("log_user", log_user))
    app.add_handler(CommandHandler("hsd", hsd))
    app.add_handler(CommandHandler("xoa_user", xoa_user))

    print("✅ Bot đang chạy...")
    app.run_polling()

if __name__ == '__main__':
    main()
