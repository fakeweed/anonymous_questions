import logging
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes

# ========== CONFIG ==========
BOT_TOKEN = "7100128845:AAH5Q8c0lcOo1LxUgPNB9xvogo9PWVeYBSE"
ADMIN_IDS = [7650388836]
ADMIN_CARD_NUMBER = "2204 3206 6218 7444"
ADMIN_BANK = "ОЗОН БАНК"

# Новые цены
PRICE_1_DAY = 99
PRICE_7_DAYS = 249


# ========== KEYBOARDS ==========
def get_main_keyboard(user_id, db=None):
    """Основная клавиатура для обычных пользователей"""
    keyboard = [
        [KeyboardButton("🔗 Мои ссылки"), KeyboardButton("📊 Статистика")],
        [KeyboardButton("💰 Платные функции"), KeyboardButton("ℹ️ Помощь")],
        [KeyboardButton("🐞 Сообщить об ошибке")]  # Новая кнопка
    ]

    # Добавляем кнопку отслеживания если есть активная подписка
    if db and has_active_tracking_db(db, user_id):
        keyboard.insert(0, [KeyboardButton("👁️ Отслеживание")])

    if user_id in ADMIN_IDS:
        keyboard.append([KeyboardButton("👑 Админ панель")])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def has_active_tracking_db(db, user_id):
    """Проверка активной подписки через базу данных"""
    active_tracking = db.get_active_tracking(user_id)
    return active_tracking is not None


def get_tracking_keyboard():
    """Клавиатура для отслеживания"""
    keyboard = [
        [KeyboardButton("📋 Мои вопросы"), KeyboardButton("👤 Отправители")],
        [KeyboardButton("⏰ Осталось времени"), KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_admin_keyboard():
    """Клавиатура для админа"""
    keyboard = [
        [KeyboardButton("📈 Общая статистика"), KeyboardButton("👥 Все пользователи")],
        [KeyboardButton("👁️ Все вопросы"), KeyboardButton("💰 Активные платежи")],
        [KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_payment_keyboard():
    """Клавиатура платных функций"""
    keyboard = [
        [KeyboardButton("📊 Отслеживание 1 день (99 руб)")],
        [KeyboardButton("📈 Отслеживание 7 дней (249 руб)")],
        [KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# ========== DATABASE ==========
class Database:
    def __init__(self, db_path='anon_bot.db'):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    registration_date TEXT
                )
            ''')
            # Таблица вопросов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS questions (
                    question_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_user_id INTEGER,
                    question_text TEXT,
                    date TEXT,
                    is_answered BOOLEAN DEFAULT FALSE,
                    answer_text TEXT,
                    FOREIGN KEY (target_user_id) REFERENCES users (user_id)
                )
            ''')
            # Таблица связи вопросов с отправителями
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    target_user_id INTEGER,
                    question_id INTEGER,
                    date TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (target_user_id) REFERENCES users (user_id),
                    FOREIGN KEY (question_id) REFERENCES questions (question_id)
                )
            ''')
            # Таблица платежей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    payment_type TEXT,
                    amount INTEGER,
                    status TEXT DEFAULT 'pending',
                    date TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            # Таблица активных подписок на отслеживание
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tracking_subscriptions (
                    subscription_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    days INTEGER,
                    start_date TEXT,
                    end_date TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            conn.commit()

    def add_user(self, user_id, username, full_name):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO users (user_id, username, full_name, registration_date)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, full_name, datetime.now().isoformat()))
            conn.commit()

    def get_question(self, question_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM questions WHERE question_id = ?', (question_id,))
            return cursor.fetchone()

    def add_question(self, target_user_id, question_text):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO questions (target_user_id, question_text, date)
                VALUES (?, ?, ?)
            ''', (target_user_id, question_text, datetime.now().isoformat()))
            conn.commit()
            return cursor.lastrowid

    def answer_question(self, question_id, answer_text):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE questions 
                SET is_answered = TRUE, answer_text = ?
                WHERE question_id = ?
            ''', (answer_text, question_id))
            conn.commit()

    def get_user_stats(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_questions,
                    SUM(CASE WHEN is_answered = TRUE THEN 1 ELSE 0 END) as answered_questions
                FROM questions WHERE target_user_id = ?
            ''', (user_id,))
            result = cursor.fetchone()
            if result and result[0] is not None:
                return result
            else:
                return (0, 0)

    def get_all_users(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users ORDER BY registration_date DESC')
            return cursor.fetchall()

    def get_global_stats(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users')
            total_users = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM questions')
            total_questions = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM questions WHERE is_answered = TRUE')
            answered_questions = cursor.fetchone()[0]

            return total_users, total_questions, answered_questions

    def get_user_questions_with_senders(self, user_id, days=None):
        """Получение вопросов пользователя с информацией об отправителях"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            if days:
                date_filter = f"AND q.date >= datetime('now', '-{days} days')"
            else:
                date_filter = ""

            cursor.execute(f'''
                SELECT 
                    q.question_id,
                    u_sender.user_id as sender_id,
                    u_sender.username as sender_username, 
                    u_sender.full_name as sender_name,
                    q.question_text,
                    q.date,
                    q.is_answered,
                    q.answer_text
                FROM questions q
                JOIN user_questions uq ON q.question_id = uq.question_id
                JOIN users u_sender ON uq.user_id = u_sender.user_id
                WHERE q.target_user_id = ? {date_filter}
                ORDER BY q.date DESC
            ''', (user_id,))
            return cursor.fetchall()

    def add_payment_request(self, user_id, payment_type, amount):
        """Добавление запроса на оплату"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO payments (user_id, payment_type, amount, status, date)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, payment_type, amount, 'pending', datetime.now().isoformat()))
            conn.commit()
            return cursor.lastrowid

    def update_payment_status(self, payment_id, status):
        """Обновление статуса платежа"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE payments SET status = ? WHERE payment_id = ?
            ''', (status, payment_id))
            conn.commit()

    def add_tracking_subscription(self, user_id, days):
        """Добавление подписки на отслеживание"""
        start_date = datetime.now()
        end_date = start_date + timedelta(days=days)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Деактивируем старые подписки
            cursor.execute('''
                UPDATE tracking_subscriptions 
                SET is_active = FALSE 
                WHERE user_id = ?
            ''', (user_id,))

            # Добавляем новую подписку
            cursor.execute('''
                INSERT INTO tracking_subscriptions (user_id, days, start_date, end_date, is_active)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, days, start_date.isoformat(), end_date.isoformat(), True))
            conn.commit()
            return cursor.lastrowid

    def get_active_tracking(self, user_id):
        """Получить активную подписку на отслеживание"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM tracking_subscriptions 
                WHERE user_id = ? AND is_active = TRUE AND end_date > datetime('now')
            ''', (user_id,))
            return cursor.fetchone()

    def get_user_pending_payments(self, user_id):
        """Получить активные платежи пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT payment_id, payment_type, amount, date
                FROM payments 
                WHERE user_id = ? AND status = 'pending'
                ORDER BY date DESC
                LIMIT 5
            ''', (user_id,))
            return cursor.fetchall()

    def get_user_questions_with_senders(self, user_id, days=None):
        """Получение вопросов пользователя с информацией об отправителях"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            if days:
                date_filter = f"AND q.date >= datetime('now', '-{days} days')"
            else:
                date_filter = ""

            cursor.execute(f'''
                SELECT 
                    q.question_id,
                    u_sender.user_id as sender_id,
                    u_sender.username as sender_username, 
                    u_sender.full_name as sender_name,
                    q.question_text,
                    q.date,
                    q.is_answered,
                    q.answer_text
                FROM questions q
                JOIN user_questions uq ON q.question_id = uq.question_id
                JOIN users u_sender ON uq.user_id = u_sender.user_id
                WHERE q.target_user_id = ? {date_filter}
                ORDER BY q.date DESC
            ''', (user_id,))
            return cursor.fetchall()


# ========== UTILS ==========
def generate_deep_link(bot_username: str, user_id: int) -> str:
    return f"https://t.me/{bot_username}?start=user_{user_id}"


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def has_active_tracking(user_id, db=None):
    """Проверка есть ли активная подписка на отслеживание"""
    if db:
        active_tracking = db.get_active_tracking(user_id)
        return active_tracking is not None
    return False

# ========== STATES ==========
AWAITING_QUESTION = 1
AWAITING_ANSWER = 2

# ========== PAYMENT HANDLERS ==========
async def show_payment_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню платных функций"""
    menu_text = (
        "💰 Платные функции\n\n"
        "📊 Отслеживание 1 день - 99 руб\n"
        "• Видите кто вам пишет 24 часа\n"
        "• Полная информация об отправителях\n\n"
        "📈 Отслеживание 7 дней - 249 руб\n"
        "• Видите кто вам пишет 7 дней\n"
        "• Экономия при долгосрочном отслеживании\n\n"
        "💡 Выберите опцию:"
    )

    await update.message.reply_text(
        menu_text,
        reply_markup=get_payment_keyboard()
    )


async def start_1day_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Покупка отслеживания на 1 день"""
    user = update.effective_user
    db = context.bot_data['db']

    # Создаем платеж
    payment_id = db.add_payment_request(user.id, 'tracking_1day', PRICE_1_DAY)
    context.user_data['payment_id'] = payment_id
    context.user_data['payment_type'] = 'tracking_1day'

    await show_payment_instructions(update, context, 'tracking_1day')


async def start_7days_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Покупка отслеживания на 7 дней"""
    user = update.effective_user
    db = context.bot_data['db']

    # Создаем платеж
    payment_id = db.add_payment_request(user.id, 'tracking_7days', PRICE_7_DAYS)
    context.user_data['payment_id'] = payment_id
    context.user_data['payment_type'] = 'tracking_7days'

    await show_payment_instructions(update, context, 'tracking_7days')


async def show_payment_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE, payment_type: str):
    """Показать инструкции по оплате"""
    user = update.effective_user

    if payment_type == 'tracking_1day':
        amount = PRICE_1_DAY
        service = "отслеживание на 1 день"
        days = 1
    else:
        amount = PRICE_7_DAYS
        service = "отслеживание на 7 дней"
        days = 7

    payment_text = (
        f"💳 Оплата услуги\n\n"
        f"📋 Услуга: {service}\n"
        f"⏰ Срок: {days} {'день' if days == 1 else 'дней'}\n"
        f"💵 Сумма: {amount} руб\n\n"
        f"🏦 Реквизиты для оплаты:\n"
        f"• Банк: {ADMIN_BANK}\n"
        f"• Карта: {ADMIN_CARD_NUMBER}\n\n"
        f"📱 Инструкция:\n"
        f"1. Переведите {amount} руб на указанную карту\n"
        f"2. Сделайте скриншот перевода\n"
        f"3. Отправьте скриншот в этот чат\n"
        f"4. Напишите в описании: @TYBAMONEY\n\n"
        f"⚡ После проверки оплаты вы мгновенно получите доступ к отслеживанию!"
    )

    await notify_admin_about_payment_request(context, user, payment_type, amount, context.user_data.get('payment_id'))
    await update.message.reply_text(
        payment_text,
        reply_markup=get_main_keyboard(user.id)
    )


async def notify_admin_about_payment_request(context, user, payment_type, amount, payment_id):
    """Уведомление админа о новой заявке на оплату"""
    admin_text = (
        f"🔄 Новая заявка на оплату\n\n"
        f"👤 Пользователь: {user.full_name} (@{user.username or 'нет'})\n"
        f"🆔 ID: {user.id}\n"
        f"💰 Услуга: {payment_type}\n"
        f"💵 Сумма: {amount} руб\n"
        f"📋 ID платежа: {payment_id}\n\n"
        f"💳 Реквизиты: {ADMIN_CARD_NUMBER} ({ADMIN_BANK})\n"
        f"⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"📋 Для выдачи услуги ответьте:\n"
        f"/complete_payment {payment_id}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=admin_text)
        except Exception as e:
            logging.error(f"Не удалось уведомить админа {admin_id}: {e}")


async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка скриншотов оплаты"""
    user = update.effective_user
    db = context.bot_data['db']

    if update.message.photo:
        payment_id = None
        payment_type = None

        # Пытаемся найти payment_id разными способами:
        # 1. Из user_data (если пользователь только что создал заявку)
        if 'payment_id' in context.user_data:
            payment_id = context.user_data['payment_id']
            payment_type = context.user_data.get('payment_type', 'неизвестно')

        # 2. Из базы данных (поиск последнего активного платежа пользователя)
        if not payment_id:
            pending_payments = db.get_user_pending_payments(user.id)
            if pending_payments:
                latest_payment = pending_payments[0]
                payment_id, payment_type, amount, date = latest_payment
            else:
                await update.message.reply_text(
                    "❌ Не найдено активных заявок на оплату.\n\n"
                    "💡 Сначала выберите услугу в меню платных функций."
                )
                return

        await update.message.reply_text(
            "✅ Скриншот получен!\n\n"
            "🔄 Проверяем оплату...\n"
            "Обычно это занимает 1-5 минут\n\n"
            "⚡ Вы получите доступ сразу после подтверждения!"
        )

        for admin_id in ADMIN_IDS:
            try:
                admin_message = (
                    f"📸 Новый скриншот оплаты!\n\n"
                    f"👤 От: {user.full_name} (@{user.username or 'нет'})\n"
                    f"🆔 ID: {user.id}\n"
                    f"📋 ID платежа: {payment_id}\n"
                    f"💰 Услуга: {payment_type}\n"
                    f"💵 Сумма: {PRICE_1_DAY if payment_type == 'tracking_1day' else PRICE_7_DAYS} руб\n\n"
                    f"📋 Для выдачи услуги ответьте:\n/complete_payment {payment_id}"
                )

                await context.bot.send_message(chat_id=admin_id, text=admin_message)
                await update.message.forward(admin_id)

            except Exception as e:
                logging.error(f"Не удалось отправить скриншот админу: {e}")


# ========== TRACKING HANDLERS ==========
async def show_tracking_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню отслеживания"""
    user = update.effective_user
    db = context.bot_data['db']

    # Проверяем активную подписку
    active_tracking = db.get_active_tracking(user.id)

    if not active_tracking:
        await update.message.reply_text(
            "❌ У вас нет активной подписки на отслеживание.\n\n"
            "💡 Приобретите подписку в разделе '💰 Платные функции'"
        )
        return

    end_date = datetime.fromisoformat(active_tracking[4])
    days_left = (end_date - datetime.now()).days
    hours_left = int((end_date - datetime.now()).seconds / 3600)

    menu_text = (
        f"👁️ Панель отслеживания\n\n"
        f"⏰ Осталось времени: {days_left}д {hours_left}ч\n"
        f"📅 Подписка активна до: {end_date.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"📊 Вы можете просматривать:\n"
        f"• Все вопросы за период подписки\n"
        f"• Информацию об отправителях\n"
        f"• Контактные данные"
    )

    await update.message.reply_text(
        menu_text,
        reply_markup=get_tracking_keyboard()
    )


async def show_my_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать вопросы пользователя"""
    user = update.effective_user
    db = context.bot_data['db']

    # Проверяем активную подписку
    active_tracking = db.get_active_tracking(user.id)
    if not active_tracking:
        await update.message.reply_text("❌ Нет активной подписки на отслеживание.")
        return

    days = active_tracking[2]  # Количество дней подписки
    questions = db.get_user_questions_with_senders(user.id, days)

    if not questions:
        await update.message.reply_text(
            f"📭 За последние {days} {'день' if days == 1 else 'дней'} вопросов нет.\n\n"
            f"💡 Поделитесь своей ссылкой, чтобы получать вопросы!"
        )
        return

    response = f"📋 Ваши вопросы ({len(questions)} шт.):\n\n"
    for i, q in enumerate(questions[:10], 1):  # Ограничиваем 10 вопросами
        q_id, sender_id, sender_user, sender_name, question_text, date, is_answered, answer_text = q

        response += f"🔹 Вопрос #{q_id}\n"
        response += f"📅 {date[:16]}\n"
        response += f"❓ {question_text[:100]}{'...' if len(question_text) > 100 else ''}\n"
        response += f"✅ Ответ: {'Да' if is_answered else 'Нет'}\n"
        response += "─" * 25 + "\n"

    if len(questions) > 10:
        response += f"\n... и еще {len(questions) - 10} вопросов"

    await update.message.reply_text(response, reply_markup=get_tracking_keyboard())


async def show_senders_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать информацию об отправителях"""
    user = update.effective_user
    db = context.bot_data['db']

    # Проверяем активную подписку
    active_tracking = db.get_active_tracking(user.id)
    if not active_tracking:
        await update.message.reply_text("❌ Нет активной подписки на отслеживание.")
        return

    days = active_tracking[2]
    questions = db.get_user_questions_with_senders(user.id, days)

    if not questions:
        await update.message.reply_text("📭 Вопросов за этот период нет.")
        return

    # Собираем уникальных отправителей и их вопросы
    senders = {}
    for q in questions:
        q_id, sender_id, sender_user, sender_name, question_text, date, is_answered, answer_text = q
        if sender_id not in senders:
            senders[sender_id] = {
                'name': sender_name,
                'username': sender_user,
                'questions': [],
                'last_date': date
            }
        senders[sender_id]['questions'].append({
            'id': q_id,
            'text': question_text,
            'date': date,
            'answered': is_answered
        })

    response = f"👤 Отправители вопросов ({len(senders)} чел.):\n\n"

    for i, (sender_id, sender_info) in enumerate(senders.items(), 1):
        contact_link = f"https://t.me/{sender_info['username']}" if sender_info['username'] else "❌ Нет юзернейма"

        response += f"🔹 {sender_info['name']}\n"
        response += f"📛 Юзернейм: @{sender_info['username'] or 'нет'}\n"
        response += f"🆔 ID: {sender_id}\n"
        response += f"💎 Контакт: {contact_link}\n"
        response += f"📨 Всего вопросов: {len(sender_info['questions'])}\n"
        response += f"📅 Последний: {sender_info['last_date'][:16]}\n\n"

        # Показываем последние 2 вопроса этого отправителя
        response += "📝 Последние вопросы:\n"
        for j, question in enumerate(sender_info['questions'][:2], 1):
            response += f"   {j}. {question['text'][:50]}{'...' if len(question['text']) > 50 else ''}\n"
            response += f"      📅 {question['date'][:16]} | "
            response += f"✅" if question['answered'] else "⏳"
            response += f" | #{question['id']}\n"

        response += "─" * 30 + "\n\n"

    # Если отправителей много, ограничиваем вывод
    if len(senders) > 5:
        response += f"\n💡 Показаны первые 5 из {len(senders)} отправителей"

    await update.message.reply_text(response, reply_markup=get_tracking_keyboard())


async def show_time_left(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать оставшееся время подписки"""
    user = update.effective_user
    db = context.bot_data['db']

    active_tracking = db.get_active_tracking(user.id)
    if not active_tracking:
        await update.message.reply_text("❌ Нет активной подписки на отслеживание.")
        return

    end_date = datetime.fromisoformat(active_tracking[4])
    time_left = end_date - datetime.now()

    if time_left.total_seconds() <= 0:
        await update.message.reply_text("❌ Ваша подписка истекла.")
        return

    days = time_left.days
    hours = int(time_left.seconds / 3600)
    minutes = int((time_left.seconds % 3600) / 60)

    response = (
        f"⏰ Статус подписки\n\n"
        f"📅 Начало: {active_tracking[3][:16]}\n"
        f"📅 Окончание: {end_date.strftime('%d.%m.%Y %H:%M')}\n"
        f"⏳ Осталось: {days}д {hours}ч {minutes}м\n"
        f"📊 Всего дней: {active_tracking[2]}\n\n"
        f"💡 После окончания подписки доступ к отслеживанию прекратится."
    )

    await update.message.reply_text(response, reply_markup=get_tracking_keyboard())


# ========== ADMIN PAYMENT COMPLETION ==========
async def complete_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение оплаты и выдача услуги (только для админа)"""
    user = update.effective_user

    if not is_admin(user.id):
        await update.message.reply_text("❌ Нет прав доступа.")
        return

    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ Неверный формат команды.\n"
            "Используйте: /complete_payment PAYMENT_ID\n"
            "Пример: /complete_payment 123"
        )
        return

    try:
        payment_id = int(context.args[0])
        db = context.bot_data['db']

        # Получаем информацию о платеже из базы данных
        with sqlite3.connect(db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT payment_id, user_id, payment_type, amount, status
                FROM payments 
                WHERE payment_id = ?
            ''', (payment_id,))
            payment_info = cursor.fetchone()

            if not payment_info:
                await update.message.reply_text(f"❌ Платеж #{payment_id} не найден.")
                return

            payment_id_db, target_user_id, payment_type, amount, status = payment_info

            if status != 'pending':
                await update.message.reply_text(f"❌ Платеж #{payment_id} уже обработан.")
                return

            # Обновляем статус платежа
            db.update_payment_status(payment_id, 'completed')

        # Выдаем услугу в зависимости от типа
        if payment_type == 'tracking_1day':
            days = 1
            db.add_tracking_subscription(target_user_id, days)
            await grant_tracking_access(context, target_user_id, days)

            await update.message.reply_text(
                f"✅ Отслеживание выдано!\n\n"
                f"👤 Пользователь: {target_user_id}\n"
                f"⏰ Срок: {days} день\n"
                f"💵 Сумма: {amount} руб"
            )

        elif payment_type == 'tracking_7days':
            days = 7
            db.add_tracking_subscription(target_user_id, days)
            await grant_tracking_access(context, target_user_id, days)

            await update.message.reply_text(
                f"✅ Отслеживание выдано!\n\n"
                f"👤 Пользователь: {target_user_id}\n"
                f"⏰ Срок: {days} дней\n"
                f"💵 Сумма: {amount} руб"
            )
        else:
            await update.message.reply_text("❌ Неизвестный тип платежа.")

    except ValueError:
        await update.message.reply_text("❌ PAYMENT_ID должен быть числом.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        logging.error(f"Ошибка при завершении оплаты: {e}")


async def grant_tracking_access(context, user_id, days):
    """Выдача доступа к отслеживанию"""
    try:
        db = context.bot_data['db']
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🎉 Доступ к отслеживанию активирован!\n\n"
                 f"📊 Теперь вы можете:\n"
                 f"• Видеть кто вам пишет\n"
                 f"• Получать полную информацию об отправителях\n"
                 f"• Отслеживать активность {days} {'день' if days == 1 else 'дней'}\n\n"
                 f"💎 Для просмотра информации нажмите кнопку '👁️ Отслеживание'",
            reply_markup=get_main_keyboard(user_id, db)  # Передаем db для проверки подписки
        )
    except Exception as e:
        logging.error(f"Не удалось уведомить пользователя {user_id}: {e}")


# ========== START HANDLERS ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = context.bot_data['db']
    db.add_user(user.id, user.username, user.full_name)

    if context.args and context.args[0].startswith('user_'):
        target_user_id = int(context.args[0][5:])
        context.user_data['target_user_id'] = target_user_id
        await update.message.reply_text(
            "✉️ Напишите ваш анонимный вопрос:\nДля отмены используйте /cancel",
            reply_markup=ReplyKeyboardRemove()
        )
        return AWAITING_QUESTION
    else:
        deep_link = generate_deep_link(context.bot.username, user.id)
        welcome_text = (
            f"👋 Добро пожаловать в Анонимную Вопросницу!\n\n"
            f"🎯 Как это работает:\n"
            f"• Создайте ссылку для вопросов\n"
            f"• Поделитесь с друзьями\n"
            f"• Получайте анонимные вопросы\n"
            f"• Отвечайте на них\n\n"
            f"🔗 Ваша ссылка:\n{deep_link}\n\n"
            f"💡 Совет: Отправьте ссылку в соцсети или мессенджеры!"
        )
        await update.message.reply_text(
            welcome_text,
            reply_markup=get_main_keyboard(user.id)
        )
        return ConversationHandler.END


async def receive_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user_id = context.user_data.get('target_user_id')
    question_text = update.message.text
    db = context.bot_data['db']

    if target_user_id and question_text:
        question_id = db.add_question(target_user_id, question_text)
        user = update.effective_user

        with sqlite3.connect(db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO user_questions (user_id, target_user_id, question_id, date)
                VALUES (?, ?, ?, ?)
            ''', (user.id, target_user_id, question_id, datetime.now().isoformat()))
            conn.commit()

        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"❓ Новый анонимный вопрос #{question_id}:\n\n{question_text}\n\n"
                     f"💬 Ответить: /answer_{question_id}",
                reply_markup=get_main_keyboard(target_user_id)
            )
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление: {e}")

        await update.message.reply_text(
            "✅ Ваш вопрос отправлен анонимно!\n\n"
            "Спасибо за участие! 🎭",
            reply_markup=ReplyKeyboardRemove()
        )

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Отправка вопроса отменена.",
        reply_markup=get_main_keyboard(update.effective_user.id)
    )
    return ConversationHandler.END


# ========== BUTTON HANDLERS ==========
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопок"""
    user = update.effective_user
    text = update.message.text

    if text == "🔗 Мои ссылки":
        await my_links(update, context)
    elif text == "📊 Статистика":
        await stats(update, context)
    elif text == "💰 Платные функции":
        await show_payment_menu(update, context)
    elif text == "ℹ️ Помощь":
        await help_command(update, context)
    elif text == "🐞 Сообщить об ошибке":
        await report_bug(update, context)
    elif text == "👁️ Отслеживание":
        await show_tracking_menu(update, context)
    elif text == "📋 Мои вопросы":
        await show_my_questions(update, context)
    elif text == "👤 Отправители":
        await show_senders_info(update, context)
    elif text == "⏰ Осталось времени":
        await show_time_left(update, context)
    elif text == "📊 Отслеживание 1 день (99 руб)":
        await start_1day_purchase(update, context)
    elif text == "📈 Отслеживание 7 дней (249 руб)":
        await start_7days_purchase(update, context)
    elif text == "👑 Админ панель":
        await admin_panel(update, context)
    elif text == "📈 Общая статистика":
        await admin_stats(update, context)
    elif text == "👥 Все пользователи":
        await admin_users(update, context)
    elif text == "👁️ Все вопросы":
        await admin_questions(update, context)
    elif text == "💰 Активные платежи":
        await admin_payments(update, context)
    elif text == "🔙 Назад":
        await back_to_main(update, context)


# ========== BASIC HANDLERS ==========
async def my_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    deep_link = generate_deep_link(context.bot.username, user.id)
    await update.message.reply_text(
        f"🔗 Ваши ссылки для вопросов:\n\n"
        f"Основная ссылка:\n{deep_link}\n\n"
        f"📤 Поделитесь этой ссылкой:\n"
        f"• В Instagram\n• В Twitter\n• В мессенджерах\n• В соцсетях",
        reply_markup=get_main_keyboard(user.id)
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = context.bot_data['db']
    stats_data = db.get_user_stats(user.id)

    if stats_data and stats_data[0] is not None:
        total, answered = stats_data
        if total == 0:
            message = "📊 Ваша статистика:\n\n📭 Пока нет вопросов\n\n💡 Разместите ссылку в соцсетях!"
        else:
            percentage = (answered / total) * 100
            message = (
                f"📊 Ваша статистика:\n\n"
                f"📨 Всего вопросов: {total}\n"
                f"✅ Ответов дано: {answered}\n"
                f"⏳ Ожидают ответа: {total - answered}\n"
                f"📈 Процент ответов: {percentage:.1f}%"
            )
    else:
        message = "📊 Ваша статистика:\n\n📭 Пока нет вопросов\n\n💡 Разместите ссылку в соцсетях!"

    await update.message.reply_text(message, reply_markup=get_main_keyboard(user.id))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "ℹ️ Помощь по боту:\n\n"
        "🎯 Как использовать:\n"
        "1. Создайте ссылку (кнопка 'Мои ссылки')\n"
        "2. Поделитесь с друзьями\n"
        "3. Получайте анонимные вопросы\n"
        "4. Отвечайте на них\n\n"
        "💰 Платные функции:\n"
        "• Отслеживание 1 день - 99 руб\n"
        "• Отслеживание 7 дней - 249 руб\n\n"
        "💬 Ответ на вопрос:\n"
        "Используйте команду /answer_номер\n"
        "Пример: /answer_1\n\n"
        "🐞 Нашли ошибку?\n"
        "Используйте кнопку 'Сообщить об ошибке'\n\n"
        "❓ Частые вопросы:\n"
        "• Вопросы полностью анонимны\n"
        "• Получатель не видит кто спрашивает\n"
        "• Ответы приходят в этот чат"
    )
    await update.message.reply_text(help_text, reply_markup=get_main_keyboard(update.effective_user.id, context.bot_data['db']))


async def report_bug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сообщить об ошибке"""
    bug_report_text = (
        "🐞 Сообщить об ошибке\n\n"
        "Если вы столкнулись с проблемами в работе бота:\n\n"
        "📱 Напишите нам напрямую: @TYBAMONEY\n\n"
        "📋 Что указать в сообщении:\n"
        "• Описание проблемы\n"
        "• Что вы делали когда возникла ошибка\n"
        "• Скриншоты (если есть)\n"
        "• Ваш юзернейм (@username)\n\n"
        "⚡ Мы оперативно исправим все проблемы!\n"
        "💎 Спасибо за вашу помощь в улучшении бота!"
    )

    await update.message.reply_text(
        bug_report_text,
        reply_markup=get_main_keyboard(update.effective_user.id, context.bot_data['db'])
    )


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("❌ Нет прав доступа.")
        return
    await update.message.reply_text(
        "👑 Админ панель\n\n"
        "Здесь вы можете отслеживать всю активность бота",
        reply_markup=get_admin_keyboard()
    )


async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔙 Возврат в главное меню",
        reply_markup=get_main_keyboard(update.effective_user.id)
    )


# ========== QUESTION HANDLERS ==========
async def answer_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    command_text = update.message.text

    try:
        question_id = int(command_text.replace('/answer_', '').strip())
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Используйте: /answer_123")
        return ConversationHandler.END

    db = context.bot_data['db']
    question = db.get_question(question_id)

    if not question:
        await update.message.reply_text("❌ Вопрос не найден.")
        return ConversationHandler.END

    target_user_id = question[1]
    if user.id != target_user_id:
        await update.message.reply_text("❌ Вы не можете отвечать на этот вопрос.")
        return ConversationHandler.END

    context.user_data['answering_question_id'] = question_id
    question_text = question[2]

    await update.message.reply_text(
        f"✍️ Вы отвечаете на вопрос #{question_id}:\n\n"
        f"❓ Вопрос: {question_text}\n\n"
        f"💭 Напишите ваш ответ:\n"
        f"Для отмены: /cancel",
        reply_markup=ReplyKeyboardRemove()
    )
    return AWAITING_ANSWER


async def receive_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question_id = context.user_data.get('answering_question_id')
    answer_text = update.message.text
    db = context.bot_data['db']

    if question_id and answer_text:
        question = db.get_question(question_id)
        if not question:
            await update.message.reply_text("❌ Вопрос не найден.")
            return ConversationHandler.END

        question_text = question[2]
        db.answer_question(question_id, answer_text)

        try:
            with sqlite3.connect(db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT user_id FROM user_questions 
                    WHERE question_id = ? AND target_user_id = ?
                ''', (question_id, update.effective_user.id))
                result = cursor.fetchone()

                if result:
                    sender_user_id = result[0]
                    await context.bot.send_message(
                        chat_id=sender_user_id,
                        text=f"💌 Вы получили ответ!\n\n"
                             f"❓ Ваш вопрос: {question_text}\n"
                             f"💬 Ответ: {answer_text}\n\n"
                             f"🎭 Вопрос был анонимным для получателя",
                        reply_markup=get_main_keyboard(sender_user_id)
                    )
        except Exception as e:
            logging.error(f"Не удалось отправить ответ: {e}")

        await update.message.reply_text(
            f"✅ Ответ сохранен и отправлен!\n\n"
            f"❓ Вопрос: {question_text}\n"
            f"💬 Ваш ответ: {answer_text}",
            reply_markup=get_main_keyboard(update.effective_user.id)
        )
        context.user_data.pop('answering_question_id', None)

    return ConversationHandler.END


async def cancel_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop('answering_question_id', None)
    await update.message.reply_text(
        "❌ Ответ отменен.",
        reply_markup=get_main_keyboard(update.effective_user.id)
    )
    return ConversationHandler.END


# ========== ADMIN HANDLERS ==========
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("❌ Нет прав.")
        return

    db = context.bot_data['db']
    total_users, total_questions, answered_questions = db.get_global_stats()
    percentage = (answered_questions / total_questions * 100) if total_questions > 0 else 0

    await update.message.reply_text(
        f"👑 Админ статистика:\n\n"
        f"👥 Пользователей: {total_users}\n"
        f"📨 Вопросов: {total_questions}\n"
        f"✅ Ответов: {answered_questions}\n"
        f"⏳ Без ответа: {total_questions - answered_questions}\n"
        f"📈 Ответов: {percentage:.1f}%",
        reply_markup=get_admin_keyboard()
    )


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("❌ Нет прав.")
        return

    db = context.bot_data['db']
    users = db.get_all_users()

    if not users:
        await update.message.reply_text("📝 Пользователей нет.")
        return

    response = "👥 Все пользователи:\n\n"
    for user_data in users[:15]:
        user_id, username, full_name, reg_date = user_data
        response += f"🆔 ID: {user_id}\n"
        response += f"👤 Имя: {full_name}\n"
        response += f"📛 Юзернейм: @{username or 'нет'}\n"
        response += f"📅 Регистрация: {reg_date[:10]}\n"
        response += "─" * 20 + "\n"

    if len(users) > 15:
        response += f"\n... и еще {len(users) - 15} пользователей"

    await update.message.reply_text(response, reply_markup=get_admin_keyboard())


async def admin_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("❌ Нет прав.")
        return

    db = context.bot_data['db']
    questions = db.get_user_questions_with_senders(user.id)  # Используем общую функцию

    if not questions:
        await update.message.reply_text("📝 Вопросов пока нет.")
        return

    response = "👁️ Все вопросы (админ):\n\n"
    for q in questions[:10]:
        q_id, sender_id, sender_user, sender_name, question_text, date, is_answered, answer_text = q

        response += f"🔹 Вопрос #{q_id}\n"
        response += f"👤 ОТ: {sender_name} (@{sender_user or 'нет'})\n"
        response += f"🆔 ID отправителя: {sender_id}\n"
        response += f"📅 Дата: {date[:16]}\n"
        response += f"❓ Вопрос: {question_text[:80]}...\n"
        response += f"✅ ОТВЕТ: {answer_text[:80]}...\n" if is_answered else "⏳ Без ответа\n"
        response += "─" * 25 + "\n"

    if len(questions) > 10:
        response += f"\n... и еще {len(questions) - 10} вопросов"

    await update.message.reply_text(response, reply_markup=get_admin_keyboard())


async def admin_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр активных платежей (для админа)"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("❌ Нет прав доступа.")
        return

    db = context.bot_data['db']
    with sqlite3.connect(db.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p.payment_id, p.user_id, u.username, u.full_name, 
                   p.payment_type, p.amount, p.date
            FROM payments p
            JOIN users u ON p.user_id = u.user_id
            WHERE p.status = 'pending'
            ORDER BY p.date DESC
            LIMIT 10
        ''')
        pending_payments = cursor.fetchall()

    if not pending_payments:
        await update.message.reply_text("📝 Активных платежей нет.")
        return

    response = "📋 Активные платежи (ожидают обработки):\n\n"
    for payment in pending_payments:
        payment_id, user_id, username, full_name, payment_type, amount, date = payment

        response += f"🔹 Платеж #{payment_id}\n"
        response += f"👤 Пользователь: {full_name} (@{username or 'нет'})\n"
        response += f"🆔 ID: {user_id}\n"
        response += f"💰 Услуга: {payment_type}\n"
        response += f"💵 Сумма: {amount} руб\n"
        response += f"📅 Дата: {date[:16]}\n"
        response += f"📋 Команда: /complete_payment {payment_id}\n"
        response += "─" * 25 + "\n"

    await update.message.reply_text(response, reply_markup=get_admin_keyboard())


async def unknown_command(update, context):
    await update.message.reply_text(
        "❌ Неизвестная команда. Используйте кнопки меню или /help",
        reply_markup=get_main_keyboard(update.effective_user.id)
    )


# ========== MAIN ==========
def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )

    db = Database()
    logging.info("База данных инициализирована")

    application = Application.builder().token(BOT_TOKEN).build()
    application.bot_data['db'] = db

    # Conversation handlers
    question_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            AWAITING_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_question)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    answer_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^/answer_\d+$'), answer_question)],
        states={
            AWAITING_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_answer)]
        },
        fallbacks=[CommandHandler('cancel', cancel_answer)]
    )

    # Add handlers
    application.add_handler(question_conv_handler)
    application.add_handler(answer_conv_handler)
    application.add_handler(CommandHandler("my_links", my_links))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin_stats", admin_stats))
    application.add_handler(CommandHandler("admin_users", admin_users))
    application.add_handler(CommandHandler("admin_questions", admin_questions))
    application.add_handler(CommandHandler("admin_payments", admin_payments))
    application.add_handler(CommandHandler("complete_payment", complete_payment))
    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_button))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    logging.info("Бот запускается...")
    application.run_polling()


if __name__ == '__main__':
    main()