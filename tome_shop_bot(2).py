"""
TOME SHOP Telegram Bot
Python 3.11+
Install: pip install "python-telegram-bot>=21,<23"
Run: set BOT_TOKEN and ADMIN_ID environment variables, then python tome_shop_bot.py

Admin commands (admin only):
  /add Name | Price | Stock
  /price ProductID | NewPrice
  /stock ProductID | NewStock
  /orders
  /helpadmin

Customer commands:
  /start
  /shop
  /help
"""
import os
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes
)

DB_PATH = os.getenv("DB_PATH", "tome_shop.sqlite3")
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
except ValueError:
    ADMIN_ID = 0

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price_cents INTEGER NOT NULL CHECK(price_cents >= 0),
                stock INTEGER NOT NULL CHECK(stock >= 0),
                active INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                product_id INTEGER NOT NULL,
                product_name TEXT NOT NULL,
                price_cents INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TEXT NOT NULL
            )
        """)

def is_admin(update: Update) -> bool:
    return bool(update.effective_user and ADMIN_ID and update.effective_user.id == ADMIN_ID)

def money(cents: int) -> str:
    return f"${cents / 100:.2f}"

def parse_price(text: str) -> int:
    try:
        value = Decimal(text.strip().replace("$", ""))
        cents = int(value * 100)
        if value < 0 or value * 100 != cents:
            raise ValueError
        return cents
    except (InvalidOperation, ValueError):
        raise ValueError("តម្លៃមិនត្រឹមត្រូវទេ។ ឧទាហរណ៍៖ 2.50")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 សូមស្វាគមន៍មកកាន់ TOME SHOP!\n\n"
        "🛍️ ចុច /shop ដើម្បីមើលទំនិញ និងតម្លៃ។\n"
        "📋 ចុច /help ដើម្បីមើលជំនួយ។"
    )
    if is_admin(update):
        text += "\n\n👑 អ្នកជា Admin។ ចុច /helpadmin ដើម្បីមើលពាក្យបញ្ជាគ្រប់គ្រង។"
    await update.effective_message.reply_text(text)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "🛍️ មើលទំនិញ៖ /shop\n"
        "បើចង់ទិញ សូមចុចប៊ូតុងនៅក្រោមទំនិញ ហើយរង់ចាំ Admin ទាក់ទងត្រឡប់។"
    )

async def helpadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.effective_message.reply_text("⛔ ពាក្យបញ្ជានេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
        return
    await update.effective_message.reply_text(
        "👑 TOME SHOP — Admin commands\n\n"
        "/add ឈ្មោះទំនិញ | តម្លៃ | ស្តុក\n"
        "ឧទាហរណ៍៖ /add AiMHEAD V5 | 0.20 | 5\n\n"
        "/price លេខទំនិញ | តម្លៃថ្មី\n"
        "ឧទាហរណ៍៖ /price 1 | 0.25\n\n"
        "/stock លេខទំនិញ | ស្តុកថ្មី\n"
        "ឧទាហរណ៍៖ /stock 1 | 10\n\n"
        "/orders — មើលការបញ្ជាទិញ\n"
        "/shop — មើលបញ្ជីទំនិញ"
    )

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with db() as conn:
        products = conn.execute(
            "SELECT id, name, price_cents, stock FROM products WHERE active=1 ORDER BY id"
        ).fetchall()
    if not products:
        await update.effective_message.reply_text(
            "🛍️ TOME SHOP\n\nមិនទាន់មានទំនិញទេ។ សូមត្រឡប់មកពេលក្រោយ។"
        )
        return
    await update.effective_message.reply_text("🛍️ TOME SHOP — បញ្ជីទំនិញ")
    for p in products:
        stock_label = "អស់ស្តុក" if p["stock"] == 0 else f"Stock: {p['stock']}"
        keyboard = None
        if p["stock"] > 0:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🛒 បញ្ជាទិញ", callback_data=f"buy:{p['id']}")
            ]])
        await update.effective_message.reply_text(
            f"📦 {p['name']}\n💵 តម្លៃ៖ {money(p['price_cents'])}\n📊 {stock_label}\n🆔 ID: {p['id']}",
            reply_markup=keyboard
        )

async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split(":", 1)[1])
    user = query.from_user
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        product = conn.execute(
            "SELECT id, name, price_cents, stock FROM products WHERE id=? AND active=1",
            (product_id,)
        ).fetchone()
        if not product or product["stock"] < 1:
            conn.rollback()
            await query.edit_message_text("សូមអភ័យទោស ទំនិញនេះអស់ស្តុកហើយ។")
            return
        conn.execute("UPDATE products SET stock=stock-1 WHERE id=?", (product_id,))
        cur = conn.execute(
            """INSERT INTO orders(user_id, username, product_id, product_name, price_cents, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'PENDING', ?)""",
            (user.id, user.username, product["id"], product["name"], product["price_cents"],
             datetime.now(timezone.utc).isoformat())
        )
        order_id = cur.lastrowid
        conn.commit()
    await query.edit_message_text(
        f"✅ បានទទួលការបញ្ជាទិញ!\n"
        f"លេខបញ្ជាទិញ៖ #{order_id}\n"
        f"ទំនិញ៖ {product['name']}\n"
        f"តម្លៃ៖ {money(product['price_cents'])}\n\n"
        "សូមរង់ចាំ Admin ទាក់ទងបញ្ជាក់ការទូទាត់ និងការផ្តល់ទំនិញ។"
    )
    if ADMIN_ID:
        try:
            username = f"@{user.username}" if user.username else "(គ្មាន username)"
            await context.bot.send_message(
                ADMIN_ID,
                f"🛒 ការបញ្ជាទិញថ្មី #{order_id}\n"
                f"អតិថិជន៖ {username}\n"
                f"User ID៖ {user.id}\n"
                f"ទំនិញ៖ {product['name']}\n"
                f"តម្លៃ៖ {money(product['price_cents'])}\n"
                f"ស្ថានភាព៖ PENDING"
            )
        except Exception:
            pass

async def add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.effective_message.reply_text("⛔ ពាក្យបញ្ជានេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
        return
    raw = " ".join(context.args)
    parts = [x.strip() for x in raw.split("|")]
    if len(parts) != 3 or not parts[0]:
        await update.effective_message.reply_text(
            "របៀបប្រើ៖ /add ឈ្មោះទំនិញ | តម្លៃ | ស្តុក\nឧទាហរណ៍៖ /add AiMHEAD V5 | 0.20 | 5"
        )
        return
    try:
        cents = parse_price(parts[1])
        stock = int(parts[2])
        if stock < 0:
            raise ValueError
    except ValueError as e:
        await update.effective_message.reply_text(str(e) or "ស្តុកត្រូវតែជាលេខ 0 ឬធំជាង 0។")
        return
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO products(name, price_cents, stock) VALUES (?, ?, ?)",
            (parts[0], cents, stock)
        )
        product_id = cur.lastrowid
    await update.effective_message.reply_text(
        f"✅ បានបន្ថែមទំនិញ!\nID: {product_id}\n{parts[0]}\nតម្លៃ: {money(cents)}\nStock: {stock}"
    )

async def set_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.effective_message.reply_text("⛔ ពាក្យបញ្ជានេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
        return
    parts = [x.strip() for x in " ".join(context.args).split("|")]
    if len(parts) != 2:
        await update.effective_message.reply_text("របៀបប្រើ៖ /price លេខទំនិញ | តម្លៃថ្មី")
        return
    try:
        product_id, cents = int(parts[0]), parse_price(parts[1])
    except ValueError:
        await update.effective_message.reply_text("សូមពិនិត្យលេខ ID និងតម្លៃម្ដងទៀត។")
        return
    with db() as conn:
        cur = conn.execute("UPDATE products SET price_cents=? WHERE id=? AND active=1", (cents, product_id))
    if cur.rowcount:
        await update.effective_message.reply_text(f"✅ បានកែតម្លៃទំនិញ ID {product_id} ទៅ {money(cents)}។")
    else:
        await update.effective_message.reply_text("រកមិនឃើញទំនិញ ID នេះទេ។")

async def set_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.effective_message.reply_text("⛔ ពាក្យបញ្ជានេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
        return
    parts = [x.strip() for x in " ".join(context.args).split("|")]
    if len(parts) != 2:
        await update.effective_message.reply_text("របៀបប្រើ៖ /stock លេខទំនិញ | ស្តុកថ្មី")
        return
    try:
        product_id, stock = int(parts[0]), int(parts[1])
        if stock < 0:
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text("ស្តុកត្រូវតែជាលេខ 0 ឬធំជាង 0។")
        return
    with db() as conn:
        cur = conn.execute("UPDATE products SET stock=? WHERE id=? AND active=1", (stock, product_id))
    if cur.rowcount:
        await update.effective_message.reply_text(f"✅ បានកែ Stock ទំនិញ ID {product_id} ទៅ {stock}។")
    else:
        await update.effective_message.reply_text("រកមិនឃើញទំនិញ ID នេះទេ។")

async def orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.effective_message.reply_text("⛔ ពាក្យបញ្ជានេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
        return
    with db() as conn:
        rows = conn.execute(
            "SELECT id, username, user_id, product_name, price_cents, status, created_at FROM orders ORDER BY id DESC LIMIT 20"
        ).fetchall()
    if not rows:
        await update.effective_message.reply_text("មិនទាន់មានការបញ្ជាទិញទេ។")
        return
    lines = ["📋 ការបញ្ជាទិញ 20 ចុងក្រោយ៖"]
    for r in rows:
        who = f"@{r['username']}" if r["username"] else f"User ID {r['user_id']}"
        lines.append(
            f"#{r['id']} · {r['product_name']} · {money(r['price_cents'])}\n"
            f"អតិថិជន៖ {who}\nស្ថានភាព៖ {r['status']}"
        )
    message = "\n\n".join(lines)
    # Telegram message limit safety
    for i in range(0, len(message), 3500):
        await update.effective_message.reply_text(message[i:i+3500])

def main():
    if not BOT_TOKEN:
        raise SystemExit("Set BOT_TOKEN environment variable first.")
    if not ADMIN_ID:
        raise SystemExit("Set ADMIN_ID environment variable to your Telegram numeric user ID.")
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("shop", shop))
    app.add_handler(CommandHandler("helpadmin", helpadmin))
    app.add_handler(CommandHandler("add", add_product))
    app.add_handler(CommandHandler("price", set_price))
    app.add_handler(CommandHandler("stock", set_stock))
    app.add_handler(CommandHandler("orders", orders))
    app.add_handler(CallbackQueryHandler(buy_callback, pattern=r"^buy:\d+$"))
    print("TOME SHOP bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
