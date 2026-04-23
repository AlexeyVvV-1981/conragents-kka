import logging
import os
import json
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
import gspread
from google.oauth2.service_account import Credentials
 
# ─────────────────────────────────────────────
# Конфигурация
# ─────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8570877997:AAFz7nNS8pVy3a_vdX6ucoazeFRmxxW15ak")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1EhHOJH0bVcQkJxMcMLCGGvCfcV1jOvaHnwvq7ypIXK8")
SHEET_NAME = "Контрагенты"
 
# Столбцы в таблице (порядок важен!)
COLUMNS = ["Название", "Вид", "Товар", "Адрес", "Фото адреса (ссылка)", "Менеджер", "Телефон", "Компания"]
 
# ─────────────────────────────────────────────
# Состояния ConversationHandler
# ─────────────────────────────────────────────
(
    SEARCH,
    ADD_NAME,
    ADD_TYPE,
    ADD_PRODUCT,
    ADD_ADDRESS,
    ADD_PHOTO,
    ADD_MANAGER,
    ADD_PHONE,
    ADD_COMPANY,
    CONFIRM,
) = range(10)
 
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
 
 
# ─────────────────────────────────────────────
# Google Sheets helper
# ─────────────────────────────────────────────
def get_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    creds_info = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    return spreadsheet.sheet1
 
 
def search_contractor(name: str):
    """Ищет контрагента по точному совпадению (без учёта регистра). Возвращает dict или None."""
    sheet = get_sheet()
    records = sheet.get_all_records()
    name_lower = name.strip().lower()
    for row in records:
        if str(row.get("Название", "")).strip().lower() == name_lower:
            return row
    return None
 
 
def search_contractor_partial(name: str):
    """Ищет контрагентов, в названии которых есть подстрока (без учёта регистра)."""
    sheet = get_sheet()
    records = sheet.get_all_records()
    name_lower = name.strip().lower()
    return [row for row in records if name_lower in str(row.get("Название", "")).strip().lower()]
 
 
def add_contractor(data: dict):
    """Добавляет новую строку в таблицу."""
    sheet = get_sheet()
    row = [data.get(col, "") for col in COLUMNS]
    sheet.append_row(row)
 
 
# ─────────────────────────────────────────────
# Форматирование карточки контрагента
# ─────────────────────────────────────────────
def format_contractor(row: dict) -> str:
    lines = ["📋 *Карточка контрагента*\n"]
    emoji_map = {
        "Название": "🏷",
        "Вид": "🔖",
        "Товар": "📦",
        "Адрес": "📍",
        "Фото адреса (ссылка)": "🖼",
        "Менеджер": "👤",
        "Телефон": "📞",
        "Компания": "🏢",
    }
    for col in COLUMNS:
        val = row.get(col, "—") or "—"
        icon = emoji_map.get(col, "•")
        lines.append(f"{icon} *{col}:* {val}")
    return "\n".join(lines)
 
 
# ─────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "👋 Привет! Я бот для работы с базой контрагентов.\n\n"
        "Введите *название* контрагента для поиска, или /cancel для отмены.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return SEARCH
 
 
# ─────────────────────────────────────────────
# Поиск
# ─────────────────────────────────────────────
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.message.text.strip()
    context.user_data["search_query"] = query
 
    await update.message.reply_text("🔍 Ищу...", reply_markup=ReplyKeyboardRemove())
 
    matches = search_contractor_partial(query)
 
    if not matches:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Добавить нового контрагента", callback_data="add_new")],
            [InlineKeyboardButton("🔄 Искать снова", callback_data="search_again")],
        ])
        await update.message.reply_text(
            f"❌ Контрагент *{query}* не найден в базе.\n\nЧто хотите сделать?",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        return SEARCH
 
    if len(matches) == 1:
        await update.message.reply_text(
            format_contractor(matches[0]),
            parse_mode="Markdown",
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Новый поиск", callback_data="search_again")],
            [InlineKeyboardButton("➕ Добавить ещё контрагента", callback_data="add_new")],
        ])
        await update.message.reply_text("Что дальше?", reply_markup=keyboard)
        return SEARCH
 
    # Несколько совпадений
    text = f"🔎 Найдено {len(matches)} контрагентов:\n\n"
    for i, row in enumerate(matches, 1):
        text += f"{i}. {row.get('Название', '—')}\n"
    text += "\nВыберите номер или введите точное название для уточнения."
 
    context.user_data["matches"] = matches
    await update.message.reply_text(text, parse_mode="Markdown")
    return SEARCH
 
 
async def handle_match_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор из списка найденных совпадений."""
    text = update.message.text.strip()
    matches = context.user_data.get("matches", [])
 
    if text.isdigit():
        idx = int(text) - 1
        if 0 <= idx < len(matches):
            await update.message.reply_text(
                format_contractor(matches[idx]),
                parse_mode="Markdown",
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Новый поиск", callback_data="search_again")],
                [InlineKeyboardButton("➕ Добавить контрагента", callback_data="add_new")],
            ])
            await update.message.reply_text("Что дальше?", reply_markup=keyboard)
            return SEARCH
 
    # Иначе — новый поиск
    return await search(update, context)
 
 
# ─────────────────────────────────────────────
# Callback-кнопки
# ─────────────────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
 
    if query.data == "add_new":
        await query.message.reply_text(
            "📝 Начинаем добавление нового контрагента.\n\n"
            "Шаг 1/8 — Введите *название* контрагента:",
            parse_mode="Markdown",
        )
        return ADD_NAME
 
    if query.data == "search_again":
        await query.message.reply_text(
            "🔍 Введите название контрагента для поиска:",
            reply_markup=ReplyKeyboardRemove(),
        )
        return SEARCH
 
    return SEARCH
 
 
# ─────────────────────────────────────────────
# Пошаговое добавление контрагента
# ─────────────────────────────────────────────
async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new"] = {}
    context.user_data["new"]["Название"] = update.message.text.strip()
    keyboard = ReplyKeyboardMarkup(
        [["Клиент", "Поставщик"]], one_time_keyboard=True, resize_keyboard=True
    )
    await update.message.reply_text(
        "Шаг 2/8 — Выберите *вид* контрагента:",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return ADD_TYPE
 
 
async def add_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    val = update.message.text.strip()
    if val not in ("Клиент", "Поставщик"):
        await update.message.reply_text("Пожалуйста, выберите *Клиент* или *Поставщик*.", parse_mode="Markdown")
        return ADD_TYPE
    context.user_data["new"]["Вид"] = val
    keyboard = ReplyKeyboardMarkup(
        [["Трёшка", "Орига"]], one_time_keyboard=True, resize_keyboard=True
    )
    await update.message.reply_text(
        "Шаг 3/8 — Выберите *товар*:",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return ADD_PRODUCT
 
 
async def add_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    val = update.message.text.strip()
    if val not in ("Трёшка", "Орига"):
        await update.message.reply_text("Пожалуйста, выберите *Трёшка* или *Орига*.", parse_mode="Markdown")
        return ADD_PRODUCT
    context.user_data["new"]["Товар"] = val
    await update.message.reply_text(
        "Шаг 4/8 — Введите *адрес*:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ADD_ADDRESS
 
 
async def add_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new"]["Адрес"] = update.message.text.strip()
    keyboard = ReplyKeyboardMarkup(
        [["⏭ Пропустить фото"]], one_time_keyboard=True, resize_keyboard=True
    )
    await update.message.reply_text(
        "Шаг 5/8 — Прикрепите *фото адреса* или нажмите «Пропустить фото»:",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return ADD_PHOTO
 
 
async def add_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        context.user_data["new"]["Фото адреса (ссылка)"] = file.file_path
    else:
        context.user_data["new"]["Фото адреса (ссылка)"] = ""
 
    await update.message.reply_text(
        "Шаг 6/8 — Введите имя *менеджера*:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ADD_MANAGER
 
 
async def add_photo_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new"]["Фото адреса (ссылка)"] = ""
    await update.message.reply_text(
        "Шаг 6/8 — Введите имя *менеджера*:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ADD_MANAGER
 
 
async def add_manager(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new"]["Менеджер"] = update.message.text.strip()
    await update.message.reply_text(
        "Шаг 7/8 — Введите *телефон*:",
        parse_mode="Markdown",
    )
    return ADD_PHONE
 
 
async def add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new"]["Телефон"] = update.message.text.strip()
    keyboard = ReplyKeyboardMarkup(
        [["Карпартс", "КаЗ", "Эверон"]], one_time_keyboard=True, resize_keyboard=True
    )
    await update.message.reply_text(
        "Шаг 8/8 — Выберите *компанию*:",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return ADD_COMPANY
 
 
async def add_company(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    val = update.message.text.strip()
    if val not in ("Карпартс", "КаЗ", "Эверон"):
        await update.message.reply_text(
            "Пожалуйста, выберите *Карпартс*, *КаЗ* или *Эверон*.", parse_mode="Markdown"
        )
        return ADD_COMPANY
    context.user_data["new"]["Компания"] = val
 
    data = context.user_data["new"]
    summary = "✅ *Проверьте данные перед сохранением:*\n\n"
    for col in COLUMNS:
        summary += f"• *{col}:* {data.get(col, '—') or '—'}\n"
 
    keyboard = ReplyKeyboardMarkup(
        [["✅ Сохранить", "❌ Отмена"]], one_time_keyboard=True, resize_keyboard=True
    )
    await update.message.reply_text(
        summary,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return CONFIRM
 
 
async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    choice = update.message.text.strip()
    if choice == "✅ Сохранить":
        try:
            add_contractor(context.user_data["new"])
            await update.message.reply_text(
                "🎉 Контрагент успешно добавлен в базу!",
                reply_markup=ReplyKeyboardRemove(),
            )
        except Exception as e:
            logger.error(f"Ошибка при добавлении: {e}")
            await update.message.reply_text(
                "⚠️ Произошла ошибка при сохранении. Попробуйте позже.",
                reply_markup=ReplyKeyboardRemove(),
            )
    else:
        await update.message.reply_text(
            "❌ Добавление отменено.",
            reply_markup=ReplyKeyboardRemove(),
        )
 
    await update.message.reply_text("Введите название контрагента для нового поиска:")
    return SEARCH
 
 
# ─────────────────────────────────────────────
# /cancel
# ─────────────────────────────────────────────
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🚫 Действие отменено. Введите /start для нового поиска.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END
 
 
# ─────────────────────────────────────────────
# Запуск бота
# ─────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
 
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SEARCH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, search),
                CallbackQueryHandler(button_handler),
            ],
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            ADD_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_type)],
            ADD_PRODUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product)],
            ADD_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_address)],
            ADD_PHOTO: [
                MessageHandler(filters.PHOTO, add_photo),
                MessageHandler(filters.Regex("^⏭ Пропустить фото$"), add_photo_skip),
            ],
            ADD_MANAGER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_manager)],
            ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone)],
            ADD_COMPANY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_company)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
 
    app.add_handler(conv_handler)
 
    logger.info("Бот запущен...")
    app.run_polling()
 
 
if __name__ == "__main__":
    main()
