"""
bot.py

Telegram interface for BizLeadBot.

This module contains ONLY Telegram wiring: commands, callback handlers,
and message flow. Business logic lives in scraper.py and database.py.
"""

import asyncio
import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config
import database
from scraper import ScraperError, export_to_csv, scrape

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bizleadbot")

# Simple in-memory state to remember "which URL is this user about to scrape".
# Fine for V1 single-process polling; would move to DB/Redis if this scales out.
_pending_urls: dict[int, str] = {}

# Admin conversation state: what the admin is currently being asked to type.
# e.g. {admin_id: "add_user" | "remove_user" | "check_user"}
_admin_state: dict[int, str] = {}

PAGE_OPTIONS = [1, 3, 5, 10]


# --- Helpers ---------------------------------------------------------------------

def _pages_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(f"📄 {p} page{'s' if p > 1 else ''}", callback_data=f"pages:{p}")
        for p in PAGE_OPTIONS
        if p <= config.MAX_PAGES
    ]
    # Two per row
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)


def _admin_panel_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("➕ Add User", callback_data="admin:add_user"),
            InlineKeyboardButton("➖ Remove User", callback_data="admin:remove_user"),
        ],
        [
            InlineKeyboardButton("👥 Users", callback_data="admin:list_users"),
            InlineKeyboardButton("🔎 Check User", callback_data="admin:check_user"),
        ],
        [InlineKeyboardButton("📊 Statistics", callback_data="admin:stats")],
    ]
    return InlineKeyboardMarkup(rows)


async def _safe_reply(update: Update, text: str, **kwargs) -> None:
    """Reply without ever leaking a stack trace to the user."""
    try:
        if update.message:
            await update.message.reply_text(text, **kwargs)
        elif update.callback_query:
            await update.callback_query.message.reply_text(text, **kwargs)
    except Exception:
        logger.exception("Failed to send reply")


# --- Basic commands ----------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    database.register_or_touch_user(user.id, user.username)

    if database.is_admin(user.id) or database.is_user_active(user.id):
        await update.message.reply_text(
            "👋 مرحباً بك في BizLeadBot.\n\n"
            "أرسل لي رابط صفحة ويب عامة وسأقوم باستخراج البيانات المفيدة منها "
            "وإرسالها لك كملف CSV."
        )
    else:
        await update.message.reply_text(
            "🔒 الوصول مرفوض.\n\n"
            "حسابك على تيليجرام غير مفعّل بعد. "
            f"تواصل مع المسؤول وأرسل له معرفك: `{user.id}`",
            parse_mode=ParseMode.MARKDOWN,
        )


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Small utility so users can find their own Telegram ID to send to the admin."""
    user = update.effective_user
    await update.message.reply_text(f"معرفك على تيليجرام هو: `{user.id}`", parse_mode=ParseMode.MARKDOWN)


# --- Main scraping flow ---------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles plain text messages: either a URL, or admin free-text input."""
    user = update.effective_user
    text = (update.message.text or "").strip()

    # If the admin is mid-flow entering a Telegram ID, route there first.
    if database.is_admin(user.id) and user.id in _admin_state:
        await _handle_admin_text_input(update, context, text)
        return

    if not (database.is_admin(user.id) or database.is_user_active(user.id)):
        await update.message.reply_text(
            "🔒 الوصول مرفوض. حسابك غير مفعّل بعد. استخدم /start لمزيد من المعلومات."
        )
        return

    if not text.lower().startswith(("http://", "https://")) and "." not in text:
        await update.message.reply_text(
            "أرسل رابط صفحة ويب عامة صالح، مثال:\nhttps://example.com"
        )
        return

    _pending_urls[user.id] = text
    await update.message.reply_text(
        "كم عدد الصفحات التي تريد فحصها؟",
        reply_markup=_pages_keyboard(),
    )


async def handle_pages_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    if not (database.is_admin(user.id) or database.is_user_active(user.id)):
        await query.edit_message_text("🔒 الوصول مرفوض.")
        return

    url = _pending_urls.pop(user.id, None)
    if not url:
        await query.edit_message_text(
            "انتهت صلاحية الطلب. أرسل الرابط من جديد من فضلك."
        )
        return

    try:
        pages = int(query.data.split(":", 1)[1])
    except (IndexError, ValueError):
        pages = 1

    await query.edit_message_text("⏳ جاري المعالجة...\nيرجى الانتظار حتى ينتهي BizLeadBot من فحص الموقع.")

    job_id = database.create_job(user.id, url, pages)

    try:
        result = await asyncio.to_thread(scrape, url, pages)
    except ScraperError as e:
        database.finish_job(job_id, 0, status="failed")
        await _safe_reply(update, f"❌ {e}")
        return
    except Exception:
        logger.exception("Unexpected scraping error")
        database.finish_job(job_id, 0, status="error")
        await _safe_reply(update, "❌ حدث خطأ غير متوقع أثناء المعالجة. حاول مرة أخرى لاحقاً.")
        return

    if not result.leads:
        database.finish_job(job_id, 0, status="empty")
        await _safe_reply(
            update,
            f"⚠️ لم يتم العثور على نتائج.\nالصفحات المفحوصة: {result.pages_scanned}",
        )
        return

    try:
        csv_path = export_to_csv(result, user.id)
    except Exception:
        logger.exception("Failed to write CSV")
        database.finish_job(job_id, len(result.leads), status="export_failed")
        await _safe_reply(update, "❌ تعذر إنشاء ملف CSV. حاول مرة أخرى.")
        return

    database.finish_job(job_id, len(result.leads), status="done")

    await _safe_reply(
        update,
        f"✅ اكتمل!\n\nالصفحات المفحوصة: {result.pages_scanned}\nعدد النتائج: {len(result.leads)}",
    )

    try:
        with open(csv_path, "rb") as f:
            await context.bot.send_document(chat_id=user.id, document=f, filename=os.path.basename(csv_path))
    except Exception:
        logger.exception("Failed to send CSV document")
        await _safe_reply(update, "❌ تعذر إرسال ملف CSV.")


# --- Admin panel -----------------------------------------------------------------

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not database.is_admin(user.id):
        await update.message.reply_text("🔒 هذا الأمر مخصص للمسؤول فقط.")
        return

    await update.message.reply_text(
        "👑 لوحة تحكم BizLeadBot",
        reply_markup=_admin_panel_keyboard(),
    )


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user

    if not database.is_admin(user.id):
        await query.answer("🔒 غير مصرح.", show_alert=True)
        return

    await query.answer()
    action = query.data.split(":", 1)[1]

    if action == "add_user":
        _admin_state[user.id] = "add_user"
        await query.message.reply_text("أرسل معرف تيليجرام (Telegram ID) للمستخدم المراد إضافته:")

    elif action == "remove_user":
        _admin_state[user.id] = "remove_user"
        await query.message.reply_text("أرسل معرف تيليجرام (Telegram ID) للمستخدم المراد إلغاء تفعيله:")

    elif action == "check_user":
        _admin_state[user.id] = "check_user"
        await query.message.reply_text("أرسل معرف تيليجرام (Telegram ID) للتحقق من حالته:")

    elif action == "list_users":
        users = database.list_users(limit=30)
        if not users:
            await query.message.reply_text("لا يوجد مستخدمون بعد.")
            return
        lines = ["👥 المستخدمون (آخر 30):\n"]
        for u in users:
            status = "✅ نشط" if u["is_active"] else "🚫 غير نشط"
            uname = f"@{u['username']}" if u["username"] else "(بدون اسم مستخدم)"
            lines.append(f"{u['telegram_id']} — {uname} — {status}")
        await query.message.reply_text("\n".join(lines))

    elif action == "stats":
        stats = database.count_users()
        await query.message.reply_text(
            f"📊 الإحصائيات\n\nالمستخدمون النشطون: {stats['active']}\nإجمالي المستخدمين: {stats['total']}"
        )


async def _handle_admin_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    user = update.effective_user
    action = _admin_state.pop(user.id, None)

    telegram_id_str = text.strip()
    if not telegram_id_str.isdigit():
        await update.message.reply_text("معرف غير صالح. يجب أن يكون رقماً. حاول مرة أخرى عبر /admin")
        return

    target_id = int(telegram_id_str)

    if action == "add_user":
        database.add_user(target_id)
        await update.message.reply_text(f"✅ تم تفعيل المستخدم {target_id}.")

    elif action == "remove_user":
        found = database.remove_user(target_id)
        if found:
            await update.message.reply_text(f"✅ تم إلغاء تفعيل المستخدم {target_id}.")
        else:
            await update.message.reply_text("⚠️ لم يتم العثور على هذا المستخدم.")

    elif action == "check_user":
        u = database.get_user(target_id)
        if not u:
            await update.message.reply_text("⚠️ لم يتم العثور على هذا المستخدم.")
        else:
            status = "✅ نشط" if u["is_active"] else "🚫 غير نشط"
            await update.message.reply_text(f"المعرف: {u['telegram_id']}\nالحالة: {status}\nالخطة: {u['plan']}")


# --- Error handler -----------------------------------------------------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled exception", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await _safe_reply(update, "❌ حدث خطأ غير متوقع. تم إبلاغ المسؤول.")


# --- Entrypoint ---------------------------------------------------------------------

def main() -> None:
    config.validate_config()
    database.init_db()

    app = Application.builder().token(config.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("whoami", whoami))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(handle_pages_choice, pattern=r"^pages:"))
    app.add_handler(CallbackQueryHandler(handle_admin_callback, pattern=r"^admin:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("BizLeadBot starting (polling mode)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
