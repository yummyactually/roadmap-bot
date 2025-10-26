from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, 
    InlineKeyboardButton, BufferedInputFile
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from dao import UserDAO, ProjectDAO, TaskDAO
from format_utils import format_roadmap_message
from config import ADMIN_ID
from datetime import datetime

async def check_bot_in_channel(bot: Bot, channel_id: str) -> dict:
    """Проверить статус бота в канале"""
    try:
        bot_member = await bot.get_chat_member(channel_id, bot.id)
        
        if bot_member.status == "kicked":
            return {"status": "kicked", "message": "Бот удален из канала"}
        elif bot_member.status == "left":
            return {"status": "left", "message": "Бот покинул канал"}
        elif bot_member.status in ["administrator", "creator"]:
            if hasattr(bot_member, 'can_edit_messages') and bot_member.can_edit_messages:
                return {"status": "ok", "message": "Бот имеет все необходимые права"}
            else:
                return {"status": "no_rights", "message": "У бота нет прав на редактирование сообщений"}
        elif bot_member.status == "member":
            return {"status": "member", "message": "Бот является участником, но не администратором"}
        else:
            return {"status": "unknown", "message": f"Неизвестный статус: {bot_member.status}"}
            
    except Exception as e:
        error_msg = str(e).lower()
        if "bot was kicked" in error_msg or "forbidden" in error_msg:
            return {"status": "kicked", "message": "Бот удален из канала или заблокирован"}
        elif "chat not found" in error_msg:
            return {"status": "not_found", "message": "Канал не найден"}
        else:
            return {"status": "error", "message": f"Ошибка проверки: {str(e)[:50]}..."}

router = Router()

# ===== FSM СОСТОЯНИЯ =====
class ProjectStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_description = State()

class TaskStates(StatesGroup):
    waiting_for_project_id = State()
    waiting_for_title = State()
    waiting_for_description = State()

class ChannelStates(StatesGroup):
    waiting_for_project_id = State()
    waiting_for_channel_id = State()

class DeleteStates(StatesGroup):
    confirm_delete_project = State()
    confirm_delete_task = State()

class MoveTaskStates(StatesGroup):
    waiting_for_new_position = State()

# ===== ОСНОВНЫЕ КОМАНДЫ =====

@router.message(CommandStart())
async def start_command(message: Message, session: AsyncSession):
    """Обработчик команды /start"""
    try:
        user = await UserDAO.get_or_create_user(
            session=session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )
        
        projects = await ProjectDAO.get_user_projects(session, user.id)
        total_tasks = 0
        completed_tasks = 0
        
        for project in projects:
            tasks = await TaskDAO.get_project_tasks(session, project.id)
            total_tasks += len(tasks)
            for task in tasks:
                if task.status == "completed":
                    completed_tasks += 1
        
        progress = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 Мои проекты", callback_data="my_projects"),
                InlineKeyboardButton(text="📊 Статистика", callback_data="my_stats")
            ],
            [
                InlineKeyboardButton(text="➕ Создать проект", callback_data="create_project"),
                InlineKeyboardButton(text="📝 Добавить задачу", callback_data="add_task_menu")
            ],
            [
                InlineKeyboardButton(text="🔄 Управление задачами", callback_data="manage_tasks"),
                InlineKeyboardButton(text="🗑 Удаление", callback_data="delete_menu")
            ],
            [
                InlineKeyboardButton(text="❓ Помощь", callback_data="help")
            ]
        ])
        
        welcome_text = (
            f"🎯 <b>Добро пожаловать, {message.from_user.first_name}!</b>\n\n"
            f"🗺 <b>RoadMapEx</b> - управление проектами в Telegram\n\n"
            f"📊 <b>Ваша статистика:</b>\n"
            f"📁 Проектов: <b>{len(projects)}</b>\n"
            f"📝 Задач: <b>{total_tasks}</b>\n"
            f"✅ Завершено: <b>{completed_tasks}</b>\n"
            f"📈 Прогресс: <b>{progress}%</b>\n\n"
            f"👆 Выберите действие:"
        )
        
        await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@router.message(Command("help"))
async def help_command(message: Message):
    """Справка по использованию бота"""
    help_text = (
        "🤖 <b>RoadMapEx - Справка</b>\n\n"
        
        "<b>📋 Основные команды:</b>\n"
        "/start - Главное меню\n"
        "/help - Эта справка\n"
        "/add_project - Создать проект\n"
        "/add_task - Добавить задачу\n"
        "/roadmap - Показать Roadmap\n"
        "/set_channel - Настроить канал\n"
        "/update_task - Изменить статус задачи\n"
        "/admin - Панель администратора\n\n"
        
        "<b>🎯 Статусы задач:</b>\n"
        "⏳ <i>Запланированная</i> - задача создана\n"
        "🔄 <i>В работе</i> - задача выполняется\n"
        "✅ <i>Завершенная</i> - задача выполнена\n"
        "❌ <i>Отмененная</i> - задача отменена\n\n"
        
        "<b>📢 Каналы:</b>\n"
        "• Добавьте бота в канал как администратора\n"
        "• Используйте /set_channel для привязки канала к проекту\n"
        "• Roadmap будет автоматически обновляться в канале\n"
        "• При кике бота канал автоматически отвязывается\n\n"
        
        "<b>🗑 Удаление:</b>\n"
        "• Используйте меню 'Удаление' для безопасного удаления\n"
        "• Удаление проекта удаляет все его задачи\n"
        "• Удаление необратимо - будьте осторожны\n\n"
        
        "<b>💡 Советы:</b>\n"
        "• Создавайте проекты для группировки задач\n"
        "• Настройте каналы для команды\n"
        "• Регулярно обновляйте статусы задач\n\n"
        
        "<b>🔄 Управление порядком задач:</b>\n"
        "• В разделе управления задачами проекта видны номера позиций\n"
        "• Используйте кнопку перемещения для изменения порядка\n"
        "• Новые задачи добавляются в конец списка\n\n"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_start")]
    ])
    
    await message.answer(help_text, reply_markup=keyboard, parse_mode="HTML")

@router.message(Command("add_project"))
async def add_project_command(message: Message, state: FSMContext):
    """Команда для создания нового проекта"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
    ])
    
    await message.answer(
        "🆕 <b>Создание нового проекта</b>\n\n"
        "📝 Введите название проекта:\n\n"
        "<i>Например: \"Мобильное приложение\" или \"Сайт компании\"</i>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(ProjectStates.waiting_for_name)

@router.message(Command("add_task"))
async def add_task_command(message: Message, state: FSMContext, session: AsyncSession):
    """Команда для добавления задачи"""
    try:
        user = await UserDAO.get_or_create_user(
            session=session,
            telegram_id=message.from_user.id
        )
        
        projects = await ProjectDAO.get_user_projects(session, user.id)
        
        if not projects:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать проект", callback_data="create_project")],
                [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_start")]
            ])
            
            await message.answer(
                "📋 У вас пока нет проектов.\n"
                "Создайте первый проект для добавления задач!",
                reply_markup=keyboard
            )
            return
        
        keyboard_buttons = []
        for project in projects:
            tasks_count = len(await TaskDAO.get_project_tasks(session, project.id))
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"📁 {project.name} ({tasks_count} задач)",
                    callback_data=f"select_project_{project.id}"
                )
            ])
        
        keyboard_buttons.append([
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await message.answer(
            "📋 <b>Выберите проект для добавления задачи:</b>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await state.set_state(TaskStates.waiting_for_project_id)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@router.message(Command("roadmap"))
async def roadmap_command(message: Message, session: AsyncSession):
    try:
        user = await UserDAO.get_or_create_user(
            session=session,
            telegram_id=message.from_user.id
        )
        
        projects = await ProjectDAO.get_user_projects(session, user.id)
        
        if not projects:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать первый проект", callback_data="create_project")],
                [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_start")]
            ])
            
            await message.answer(
                "📋 <b>У вас пока нет проектов</b>\n\n"
                "Создайте первый проект для начала работы!",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            return
        
        for project in projects:
            tasks = await TaskDAO.get_project_tasks(session, project.id)
            roadmap_text = format_roadmap_message(project, tasks)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="➕ Добавить задачу", callback_data=f"add_task_{project.id}"),
                    InlineKeyboardButton(text="🔄 Обновить канал", callback_data=f"update_channel_{project.id}")
                ],
                [
                    InlineKeyboardButton(text="📢 Настроить канал", callback_data=f"set_channel_{project.id}"),
                    InlineKeyboardButton(text="🗑 Удалить проект", callback_data=f"delete_project_{project.id}")
                ],
                [
                    InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_start")
                ]
            ])
            
            await message.answer(roadmap_text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@router.message(Command("set_channel"))
async def set_channel_command(message: Message, state: FSMContext, session: AsyncSession):
    """Команда для привязки канала к проекту"""
    try:
        user = await UserDAO.get_or_create_user(
            session=session,
            telegram_id=message.from_user.id
        )
        
        projects = await ProjectDAO.get_user_projects(session, user.id)
        
        if not projects:
            await message.answer("📋 У вас пока нет проектов.")
            return
        
        keyboard_buttons = []
        for project in projects:
            status = "✅" if project.channel_id else "➕"
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"{status} {project.name}",
                    callback_data=f"set_channel_{project.id}"
                )
            ])
        
        keyboard_buttons.append([
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await message.answer(
            "📢 <b>Выберите проект для настройки канала:</b>\n\n"
            "✅ - канал уже настроен\n"
            "➕ - настроить канал",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@router.message(Command("update_task"))
async def update_task_command(message: Message, session: AsyncSession):
    """Команда для обновления статуса задачи"""
    try:
        user = await UserDAO.get_or_create_user(
            session=session,
            telegram_id=message.from_user.id
        )
        
        projects = await ProjectDAO.get_user_projects(session, user.id)
        
        if not projects:
            await message.answer("📋 У вас пока нет проектов с задачами.")
            return
        
        all_tasks = []
        for project in projects:
            tasks = await TaskDAO.get_project_tasks(session, project.id)
            for task in tasks:
                all_tasks.append((task, project.name))
        
        if not all_tasks:
            await message.answer("📝 У вас пока нет задач для обновления.")
            return
        
        keyboard_buttons = []
        for task, project_name in all_tasks[:10]:  
            status_emoji = {"planned": "⏳", "in_progress": "🔄", "completed": "✅", "cancelled": "❌"}
            emoji = status_emoji.get(task.status, "❓")
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"{emoji} {task.title[:30]}... ({project_name})",
                    callback_data=f"update_task_{task.id}"
                )
            ])
        
        keyboard_buttons.append([
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await message.answer(
            "🔄 <b>Выберите задачу для изменения статуса:</b>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@router.message(Command("admin"))
async def admin_command(message: Message, session: AsyncSession):
    """Админ панель"""
    try:
        if message.from_user.id != ADMIN_ID:
            await message.answer("❌ У вас нет прав администратора!")
            return
        
        from models import User, Project, Task
        
        all_users_result = await session.execute(select(User))
        all_users = all_users_result.scalars().all()
        real_users = [u for u in all_users if not (u.username and u.username.lower().endswith('bot'))]
        
        projects_count = await session.execute(
            select(func.count(Project.id)).where(Project.is_active == True)
        )
        tasks_count = await session.execute(select(func.count(Task.id)))
        completed_tasks = await session.execute(
            select(func.count(Task.id)).where(Task.status == 'completed')
        )
        
        admin_text = (
            "🔧 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\n"
            "📊 <b>Статистика системы:</b>\n"
            f"👥 Пользователей: <b>{len(real_users)}</b>\n"
            f"📁 Проектов: <b>{projects_count.scalar()}</b>\n"
            f"✅ Всего задач: <b>{tasks_count.scalar()}</b>\n"
            f"🎯 Завершенных задач: <b>{completed_tasks.scalar()}</b>\n\n"
            f"🖥 <b>Информация о системе:</b>\n"
            f"📊 База данных: SQLite\n"
            f"⏰ Время сервера: {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}\n"
            f"🤖 Режим: Telegram Bot"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📄 Экспорт JSON", callback_data="export_users_json"),
                InlineKeyboardButton(text="📝 Экспорт TXT", callback_data="export_users_txt")
            ],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_start")]
        ])
        
        await message.answer(admin_text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

# ===== ОБРАБОТЧИКИ FSM =====

@router.message(ProjectStates.waiting_for_name)
async def project_name_handler(message: Message, state: FSMContext):
    """Обработка названия проекта"""
    try:
        if len(message.text) > 100:
            await message.answer(
                "❌ Название слишком длинное (максимум 100 символов).\n"
                "Попробуйте сократить название."
            )
            return
        
        await state.update_data(name=message.text.strip())
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Пропустить описание", callback_data="skip_description")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
        ])
        
        await message.answer(
            "📄 <b>Описание проекта</b>\n\n"
            "💬 Введите краткое описание проекта или нажмите 'Пропустить':\n\n"
            "<i>Например: \"Разработка мобильного приложения для управления задачами\"</i>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await state.set_state(ProjectStates.waiting_for_description)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@router.message(ProjectStates.waiting_for_description)  
async def project_description_handler(message: Message, state: FSMContext, session: AsyncSession):
    """Обработка описания проекта"""
    try:
        if len(message.text) > 1000:
            await message.answer(
                "❌ Описание слишком длинное (максимум 1000 символов).\n"
                "Попробуйте сократить описание."
            )
            return
        
        data = await state.get_data()
        
        user = await UserDAO.get_or_create_user(
            session=session,
            telegram_id=message.from_user.id
        )
        
        project = await ProjectDAO.create_project(
            session=session,
            name=data["name"],
            description=message.text.strip(),
            owner_id=user.id
        )
        
        await state.clear()
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Добавить задачу", callback_data=f"add_task_{project.id}"),
                InlineKeyboardButton(text="📢 Настроить канал", callback_data=f"set_channel_{project.id}")
            ],
            [
                InlineKeyboardButton(text="🗺 Показать Roadmap", callback_data=f"show_roadmap_{project.id}"),
                InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_start")
            ]
        ])
        
        success_text = (
            f"✅ <b>Проект создан!</b>\n\n"
            f"📁 <b>{project.name}</b>\n"
            f"📝 {project.description}\n\n"
            f"🆔 ID проекта: {project.id}\n"
            f"📅 Создан: {project.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"🎯 <b>Следующие шаги:</b>\n"
            f"• Добавьте задачи к проекту\n"
            f"• Настройте канал для автопубликации"
        )
        
        await message.answer(success_text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@router.message(TaskStates.waiting_for_title)
async def task_title_handler(message: Message, state: FSMContext):
    """Обработка названия задачи"""
    try:
        if len(message.text) > 200:
            await message.answer(
                "❌ Название задачи слишком длинное (максимум 200 символов)."
            )
            return
        
        await state.update_data(title=message.text.strip())
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Пропустить описание", callback_data="skip_task_description")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
        ])
        
        await message.answer(
            "📄 <b>Описание задачи</b>\n\n"
            "💬 Введите описание задачи или нажмите 'Пропустить':\n\n"
            "<i>Например: \"Создать макет главной страницы с адаптивным дизайном\"</i>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await state.set_state(TaskStates.waiting_for_description)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@router.message(TaskStates.waiting_for_description)
async def task_description_handler(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    """Обработка описания задачи"""
    try:
        data = await state.get_data()
        
        if "title" not in data or "project_id" not in data:
            await message.answer("❌ Ошибка: данные задачи потеряны. Начните заново.")
            await state.clear()
            return
        
        user = await UserDAO.get_or_create_user(
            session=session,
            telegram_id=message.from_user.id
        )
        
        task = await TaskDAO.create_task(
            session=session,
            title=data["title"],
            description=message.text.strip(),
            project_id=data["project_id"],
            creator_id=user.id,
            priority="medium"
        )
        
        await state.clear()
        
        project = await ProjectDAO.get_project_by_id(session, data["project_id"])
        
        update_message = ""
        if project and project.channel_id and project.message_id and bot:
            try:
                tasks = await TaskDAO.get_project_tasks(session, project.id)
                roadmap_text = format_roadmap_message(project, tasks)
                
                await bot.edit_message_text(
                    text=roadmap_text,
                    chat_id=project.channel_id,
                    message_id=project.message_id,
                    parse_mode="HTML"
                )
                
                update_message = "\n🔄 Roadmap автоматически обновлен в канале!"
            except Exception as e:
                update_message = f"\n⚠️ Ошибка обновления канала: {str(e)[:50]}..."
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_start")]
        ])
        
        await message.answer(
            f"✅ <b>Задача создана!</b>{update_message}\n\n"
            f"📝 <b>{task.title}</b>\n"
            f"📄 {task.description}\n\n"
            f"🆔 ID: {task.id}\n"
            f"📁 Проект: {project.name if project else 'Неизвестен'}\n"
            f"⏳ Статус: Запланирована",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@router.message(ChannelStates.waiting_for_channel_id)
async def channel_id_handler(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    """Обработка ID канала"""
    try:
        data = await state.get_data()
        project_id = data.get("project_id")
        
        if not project_id:
            await message.answer("❌ Ошибка: проект не найден.")
            await state.clear()
            return
        
        channel_id = message.text.strip()
        
        if not (channel_id.startswith('@') or channel_id.startswith('-') or channel_id.isdigit()):
            await message.answer(
                "❌ Неверный формат ID канала.\n\n"
                "Используйте один из форматов:\n"
                "• @channel_username\n"
                "• -100123456789 (ID канала)\n"
                "• 123456789 (ID чата)"
            )
            return
        
        await ProjectDAO.update_project(
            session=session,
            project_id=project_id,
            channel_id=channel_id
        )
        
        project = await ProjectDAO.get_project_by_id(session, project_id)
        tasks = await TaskDAO.get_project_tasks(session, project_id)
        roadmap_text = format_roadmap_message(project, tasks)
        
        if bot:
            sent_message = await bot.send_message(
                chat_id=channel_id,
                text=roadmap_text,
                parse_mode="HTML"
            )
            
            await ProjectDAO.update_roadmap_message(session, project_id, sent_message.message_id)
        
        await state.clear()
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_start")]
        ])
        
        await message.answer(
            f"✅ <b>Канал настроен!</b>\n\n"
            f"📢 Канал: <code>{channel_id}</code>\n"
            f"📝 Roadmap опубликован в канале\n"
            f"🔄 Будет автоматически обновляться при изменениях",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
    except Exception as e:
        await message.answer(f"❌ Ошибка настройки канала: {str(e)}")

@router.message(MoveTaskStates.waiting_for_new_position)
async def move_task_position_handler(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    """Обработка новой позиции для задачи"""
    try:
        data = await state.get_data()
        task_id = data.get("task_id")
        project_id = data.get("project_id")
        
        if not task_id or not project_id:
            await message.answer("❌ Ошибка: данные задачи потеряны. Начните заново.")
            await state.clear()
            return
        
        try:
            new_position = int(message.text.strip())
        except ValueError:
            await message.answer("❌ Введите корректный номер позиции (число)!")
            return
        
        tasks = await TaskDAO.get_project_tasks(session, project_id)
        if new_position < 1 or new_position > len(tasks):
            await message.answer(f"❌ Позиция должна быть от 1 до {len(tasks)}!")
            return
        
        success = await TaskDAO.move_task_to_position(session, task_id, new_position)
        
        if success:
            project = await ProjectDAO.get_project_by_id(session, project_id)
            
            update_message = ""
            if project and project.channel_id and project.message_id and bot:
                try:
                    updated_tasks = await TaskDAO.get_project_tasks(session, project.id)
                    roadmap_text = format_roadmap_message(project, updated_tasks)
                    
                    await bot.edit_message_text(
                        text=roadmap_text,
                        chat_id=project.channel_id,
                        message_id=project.message_id,
                        parse_mode="HTML"
                    )
                    
                    update_message = "\n🔄 Roadmap автоматически обновлен в канале!"
                except Exception as e:
                    if "message is not modified" not in str(e):
                        update_message = f"\n⚠️ Ошибка обновления канала: {str(e)[:50]}..."
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📝 К задачам проекта", callback_data=f"project_tasks_{project_id}_0"),
                    InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_start")
                ]
            ])
            
            await message.answer(
                f"✅ <b>Задача перемещена!</b>{update_message}\n\n"
                f"📝 Задача перемещена на позицию {new_position}\n"
                f"📁 Проект: {project.name if project else 'Неизвестен'}",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        else:
            await message.answer("❌ Ошибка перемещения задачи. Проверьте номер позиции.")
        
        await state.clear()
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
        await state.clear()

# ===== CALLBACK ОБРАБОТЧИКИ =====

@router.callback_query(F.data == "my_projects")
async def my_projects_callback(callback: CallbackQuery, session: AsyncSession):
    """Показать все проекты пользователя"""
    try:
        await callback.answer()
        
        user = await UserDAO.get_or_create_user(
            session=session,
            telegram_id=callback.from_user.id
        )
        
        projects = await ProjectDAO.get_user_projects(session, user.id)
        
        if not projects:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать проект", callback_data="create_project")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
            ])
            
            await callback.message.edit_text(
                "📋 <b>У вас пока нет проектов</b>\n\n"
                "Создайте первый проект для начала работы!",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            return
        
        keyboard_buttons = []
        for project in projects:
            tasks = await TaskDAO.get_project_tasks(session, project.id)
            tasks_count = len(tasks)
            completed_count = len([t for t in tasks if t.status == "completed"])
            progress = f"{completed_count}/{tasks_count}" if tasks_count > 0 else "0/0"
            
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"📁 {project.name} ({progress})",
                    callback_data=f"show_roadmap_{project.id}"
                )
            ])
        
        keyboard_buttons.extend([
            [InlineKeyboardButton(text="➕ Создать новый", callback_data="create_project")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await callback.message.edit_text(
            f"📁 <b>Ваши проекты ({len(projects)}):</b>\n\n"
            "Выберите проект для просмотра:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data == "my_stats")
async def my_stats_callback(callback: CallbackQuery, session: AsyncSession):
    """Показать статистику пользователя"""
    try:
        await callback.answer()
        
        user = await UserDAO.get_or_create_user(
            session=session,
            telegram_id=callback.from_user.id
        )
        
        projects = await ProjectDAO.get_user_projects(session, user.id)
        
        total_tasks = 0
        completed_tasks = 0
        in_progress_tasks = 0
        planned_tasks = 0
        
        for project in projects:
            tasks = await TaskDAO.get_project_tasks(session, project.id)
            total_tasks += len(tasks)
            for task in tasks:
                if task.status == "completed":
                    completed_tasks += 1
                elif task.status == "in_progress":
                    in_progress_tasks += 1
                elif task.status == "planned":
                    planned_tasks += 1
        
        progress = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
        
        stats_text = (
            f"📊 <b>Ваша статистика</b>\n\n"
            f"📁 Проектов: <b>{len(projects)}</b>\n"
            f"📝 Всего задач: <b>{total_tasks}</b>\n\n"
            f"✅ Завершено: <b>{completed_tasks}</b>\n"
            f"🔄 В работе: <b>{in_progress_tasks}</b>\n"
            f"⏳ Запланировано: <b>{planned_tasks}</b>\n\n"
            f"📈 Общий прогресс: <b>{progress}%</b>\n"
            f"{'█' * (progress // 10)}{'░' * (10 - progress // 10)}\n\n"
            f"📅 Регистрация: {user.created_at.strftime('%d.%m.%Y')}"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
        ])
        
        await callback.message.edit_text(
            stats_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data == "create_project")
async def create_project_callback(callback: CallbackQuery, state: FSMContext):
    """Начать создание проекта через callback"""
    try:
        await callback.answer()
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
        ])
        
        await callback.message.edit_text(
            "🆕 <b>Создание нового проекта</b>\n\n"
            "📝 Введите название проекта:\n\n"
            "<i>Например: \"Мобильное приложение\" или \"Сайт компании\"</i>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await state.set_state(ProjectStates.waiting_for_name)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data == "add_task_menu")
async def add_task_menu_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Меню добавления задачи"""
    try:
        await callback.answer()
        
        user = await UserDAO.get_or_create_user(
            session=session,
            telegram_id=callback.from_user.id
        )
        
        projects = await ProjectDAO.get_user_projects(session, user.id)
        
        if not projects:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать проект", callback_data="create_project")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
            ])
            
            await callback.message.edit_text(
                "📋 У вас пока нет проектов.\n"
                "Создайте первый проект для добавления задач!",
                reply_markup=keyboard
            )
            return
        
        keyboard_buttons = []
        for project in projects:
            tasks_count = len(await TaskDAO.get_project_tasks(session, project.id))
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"📁 {project.name} ({tasks_count} задач)",
                    callback_data=f"select_project_{project.id}"
                )
            ])
        
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await callback.message.edit_text(
            "📋 <b>Выберите проект для добавления задачи:</b>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await state.set_state(TaskStates.waiting_for_project_id)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data == "manage_tasks")
async def manage_tasks_callback(callback: CallbackQuery, session: AsyncSession):
    """Меню управления задачами"""
    try:
        await callback.answer()
        
        user = await UserDAO.get_or_create_user(
            session=session,
            telegram_id=callback.from_user.id
        )
        
        projects = await ProjectDAO.get_user_projects(session, user.id)
        
        all_tasks = []
        for project in projects:
            tasks = await TaskDAO.get_project_tasks(session, project.id)
            for task in tasks:
                all_tasks.append((task, project.name))
        
        if not all_tasks:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить задачу", callback_data="add_task_menu")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
            ])
            
            await callback.message.edit_text(
                "📝 У вас нет задач.\n"
                "Добавьте задачи для управления ими!",
                reply_markup=keyboard
            )
            return
        
        page = 0
        keyboard_buttons = []
        start_idx = page * 8
        end_idx = start_idx + 8
        
        for task, project_name in all_tasks[start_idx:end_idx]:
            status_emoji = {"planned": "⏳", "in_progress": "🔄", "completed": "✅", "cancelled": "❌"}
            emoji = status_emoji.get(task.status, "❓")
            callback_data = f"update_task_{task.id}"
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"{emoji} {task.title[:25]}...",
                    callback_data=callback_data
                )
            ])
        
        nav_buttons = []
        if len(all_tasks) > 8:
            if page > 0:
                nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"tasks_page_{page-1}"))
            if end_idx < len(all_tasks):
                nav_buttons.append(InlineKeyboardButton(text="➡️ Далее", callback_data=f"tasks_page_{page+1}"))
            
            if nav_buttons:
                keyboard_buttons.append(nav_buttons)
        
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        page_info = f" (стр. {page+1}/{((len(all_tasks)-1)//8)+1})" if len(all_tasks) > 8 else ""
        
        await callback.message.edit_text(
            f"🔄 <b>Управление задачами ({len(all_tasks)}){page_info}:</b>\n\n"
            "Выберите задачу для изменения статуса:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("tasks_page_"))
async def tasks_page_callback(callback: CallbackQuery, session: AsyncSession):
    """Пагинация задач"""
    try:
        await callback.answer()
        
        page = int(callback.data.split("_")[2])
        
        user = await UserDAO.get_or_create_user(
            session=session,
            telegram_id=callback.from_user.id
        )
        
        projects = await ProjectDAO.get_user_projects(session, user.id)
        
        all_tasks = []
        for project in projects:
            tasks = await TaskDAO.get_project_tasks(session, project.id)
            for task in tasks:
                all_tasks.append((task, project.name))
        
        keyboard_buttons = []
        start_idx = page * 8
        end_idx = start_idx + 8
        
        for task, project_name in all_tasks[start_idx:end_idx]:
            status_emoji = {"planned": "⏳", "in_progress": "🔄", "completed": "✅", "cancelled": "❌"}
            emoji = status_emoji.get(task.status, "❓")
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"{emoji} {task.title[:25]}...",
                    callback_data=f"update_task_{task.id}"
                )
            ])
        
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"tasks_page_{page-1}"))
        if end_idx < len(all_tasks):
            nav_buttons.append(InlineKeyboardButton(text="➡️ Далее", callback_data=f"tasks_page_{page+1}"))
        
        if nav_buttons:
            keyboard_buttons.append(nav_buttons)
            
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        page_info = f" (стр. {page+1}/{((len(all_tasks)-1)//8)+1})"
        
        await callback.message.edit_text(
            f"🔄 <b>Управление задачами ({len(all_tasks)}){page_info}:</b>\n\n"
            "Выберите задачу для изменения статуса:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data == "delete_menu")
async def delete_menu_callback(callback: CallbackQuery, session: AsyncSession):
    """Меню удаления"""
    try:
        await callback.answer()
        
        user = await UserDAO.get_or_create_user(
            session=session,
            telegram_id=callback.from_user.id
        )
        
        projects = await ProjectDAO.get_user_projects(session, user.id)
        
        if not projects:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
            ])
            
            await callback.message.edit_text(
                "📋 <b>У вас нет проектов для удаления</b>\n\n"
                "Сначала создайте проекты и задачи.",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            return
        
        keyboard_buttons = [
            [InlineKeyboardButton(text="🗑 Удалить проекты", callback_data="delete_projects_menu")],
            [InlineKeyboardButton(text="🗑 Удалить задачи", callback_data="delete_tasks_menu")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
        ]
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await callback.message.edit_text(
            "🗑 <b>Меню удаления</b>\n\n"
            "⚠️ <b>Внимание!</b> Удаление необратимо.\n"
            "• При удалении проекта удаляются все его задачи\n"
            "• Будьте осторожны при выборе\n\n"
            "Что хотите удалить?",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data == "delete_projects_menu")
async def delete_projects_menu_callback(callback: CallbackQuery, session: AsyncSession):
    """Меню удаления проектов"""
    try:
        await callback.answer()
        
        user = await UserDAO.get_or_create_user(
            session=session,
            telegram_id=callback.from_user.id
        )
        
        projects = await ProjectDAO.get_user_projects(session, user.id)
        
        if not projects:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="delete_menu")]
            ])
            
            await callback.message.edit_text(
                "📋 <b>У вас нет проектов для удаления</b>",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            return
        
        keyboard_buttons = []
        for project in projects:
            tasks = await TaskDAO.get_project_tasks(session, project.id)
            tasks_count = len(tasks)
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"🗑 {project.name} ({tasks_count} задач)",
                    callback_data=f"confirm_delete_project_{project.id}"
                )
            ])
        
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔙 Назад", callback_data="delete_menu")
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await callback.message.edit_text(
            "🗑 <b>Удаление проектов</b>\n\n"
            "⚠️ <b>ВНИМАНИЕ!</b> При удалении проекта будут удалены все его задачи!\n\n"
            "Выберите проект для удаления:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data == "delete_tasks_menu")
async def delete_tasks_menu_callback(callback: CallbackQuery, session: AsyncSession):
    """Меню удаления задач"""
    try:
        await callback.answer()
        
        user = await UserDAO.get_or_create_user(
            session=session,
            telegram_id=callback.from_user.id
        )
        
        projects = await ProjectDAO.get_user_projects(session, user.id)
        
        all_tasks = []
        for project in projects:
            tasks = await TaskDAO.get_project_tasks(session, project.id)
            for task in tasks:
                all_tasks.append((task, project.name))
        
        if not all_tasks:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="delete_menu")]
            ])
            
            await callback.message.edit_text(
                "📝 <b>У вас нет задач для удаления</b>",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            return
        
        keyboard_buttons = []
        for task, project_name in all_tasks[:8]:  
            status_emoji = {"planned": "⏳", "in_progress": "🔄", "completed": "✅", "cancelled": "❌"}
            emoji = status_emoji.get(task.status, "❓")
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"🗑 {emoji} {task.title[:20]}... ({project_name[:10]})",
                    callback_data=f"confirm_delete_task_{task.id}"
                )
            ])
        
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔙 Назад", callback_data="delete_menu")
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await callback.message.edit_text(
            f"🗑 <b>Удаление задач</b>\n\n"
            f"Выберите задачу для удаления из {len(all_tasks)} доступных:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("confirm_delete_project_"))
async def confirm_delete_project_callback(callback: CallbackQuery, session: AsyncSession):
    """Подтверждение удаления проекта"""
    try:
        await callback.answer()
        
        project_id = int(callback.data.split("_")[3])
        project = await ProjectDAO.get_project_by_id(session, project_id)
        
        if not project:
            await callback.answer("❌ Проект не найден!", show_alert=True)
            return
        
        tasks = await TaskDAO.get_project_tasks(session, project_id)
        tasks_count = len(tasks)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 ДА, УДАЛИТЬ", callback_data=f"delete_project_{project_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="delete_projects_menu")
            ]
        ])
        
        await callback.message.edit_text(
            f"🗑 <b>ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ</b>\n\n"
            f"📁 <b>Проект:</b> {project.name}\n"
            f"📝 <b>Задач:</b> {tasks_count}\n"
            f"📄 <b>Описание:</b> {project.description or 'Без описания'}\n\n"
            f"⚠️ <b>ВНИМАНИЕ!</b>\n"
            f"Это действие удалит:\n"
            f"• Проект \"{project.name}\"\n"
            f"• Все {tasks_count} задач проекта\n"
            f"• Настройки канала\n\n"
            f"❗ <b>Восстановить данные будет невозможно!</b>\n\n"
            f"Вы уверены?",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("confirm_delete_task_"))
async def confirm_delete_task_callback(callback: CallbackQuery, session: AsyncSession):
    """Подтверждение удаления задачи"""
    try:
        await callback.answer()
        
        task_id = int(callback.data.split("_")[3])
        task = await TaskDAO.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена!", show_alert=True)
            return
        
        project = await ProjectDAO.get_project_by_id(session, task.project_id)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 ДА, УДАЛИТЬ", callback_data=f"delete_task_{task_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="delete_tasks_menu")
            ]
        ])
        
        status_names = {"planned": "⏳ Запланирована", "in_progress": "🔄 В работе", "completed": "✅ Завершена", "cancelled": "❌ Отменена"}
        status_text = status_names.get(task.status, "❓ Неизвестно")
        
        await callback.message.edit_text(
            f"🗑 <b>ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ</b>\n\n"
            f"📝 <b>Задача:</b> {task.title}\n"
            f"📄 <b>Описание:</b> {task.description or 'Без описания'}\n"
            f"🎯 <b>Статус:</b> {status_text}\n"
            f"📁 <b>Проект:</b> {project.name if project else 'Неизвестен'}\n\n"
            f"⚠️ <b>ВНИМАНИЕ!</b>\n"
            f"Задача будет удалена безвозвратно!\n\n"
            f"Вы уверены?",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("delete_project_"))
async def delete_project_callback(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Удаление проекта"""
    try:
        await callback.answer("🗑 Удаляю проект...")
        
        project_id = int(callback.data.split("_")[2])
        project = await ProjectDAO.get_project_by_id(session, project_id)
        
        if not project:
            await callback.answer("❌ Проект не найден!", show_alert=True)
            return
        
        await ProjectDAO.delete_project(session, project_id)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔙 К удалению", callback_data="delete_menu"),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")
            ]
        ])
        
        await callback.message.edit_text(
            f"✅ <b>Проект удален!</b>\n\n"
            f"🗑 Удаленный проект: <b>{project.name}</b>\n"
            f"📝 Все задачи проекта также удалены\n"
            f"📢 Настройки канала очищены\n\n"
            f"💡 Вы можете создать новые проекты в любое время.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(f"❌ Ошибка удаления: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("delete_task_"))
async def delete_task_callback(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Удаление задачи"""
    try:
        await callback.answer("🗑 Удаляю задачу...")
        
        task_id = int(callback.data.split("_")[2])
        task = await TaskDAO.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена!", show_alert=True)
            return
        
        project = await ProjectDAO.get_project_by_id(session, task.project_id)
        task_title = task.title
        
        await TaskDAO.delete_task(session, task_id)
        
        update_message = ""
        if project and project.channel_id and project.message_id and bot:
            try:
                tasks = await TaskDAO.get_project_tasks(session, project.id)
                roadmap_text = format_roadmap_message(project, tasks)
                
                await bot.edit_message_text(
                    text=roadmap_text,
                    chat_id=project.channel_id,
                    message_id=project.message_id,
                    parse_mode="HTML"
                )
                
                update_message = "\n🔄 Roadmap автоматически обновлен в канале!"
            except Exception as e:
                update_message = f"\n⚠️ Ошибка обновления канала: {str(e)[:50]}..."
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Удалить еще", callback_data="delete_tasks_menu"),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")
            ]
        ])
        
        await callback.message.edit_text(
            f"✅ <b>Задача удалена!</b>{update_message}\n\n"
            f"🗑 Удаленная задача: <b>{task_title}</b>\n"
            f"📁 Из проекта: {project.name if project else 'Неизвестен'}\n\n"
            f"💡 Остальные задачи остались без изменений.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(f"❌ Ошибка удаления: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("project_tasks_"))
async def project_tasks_callback(callback: CallbackQuery, session: AsyncSession):
    """Показать задачи конкретного проекта с пагинацией и индексами"""
    try:
        await callback.answer()
        
        parts = callback.data.split("_")
        project_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0
        
        project = await ProjectDAO.get_project_by_id(session, project_id)
        if not project:
            await callback.answer("❌ Проект не найден!", show_alert=True)
            return
        
        tasks = await TaskDAO.get_project_tasks(session, project_id)
        
        if not tasks:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить первую задачу", callback_data=f"add_task_{project_id}")],
                [InlineKeyboardButton(text="🔙 К проекту", callback_data=f"show_roadmap_{project_id}")]
            ])
            
            await callback.message.edit_text(
                f"📝 <b>Задачи проекта \"{project.name}\"</b>\n\n"
                "У проекта пока нет задач.\n"
                "Добавьте первую задачу!",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            return
        
        per_page = 10
        start_idx = page * per_page
        end_idx = start_idx + per_page
        
        keyboard_buttons = []
        for i, task in enumerate(tasks[start_idx:end_idx]):
            status_emoji = {"planned": "⏳", "in_progress": "🔄", "completed": "✅", "cancelled": "❌"}
            emoji = status_emoji.get(task.status, "❓")
            position = start_idx + i + 1
            
            row = []
            
            if position > 1:
                row.append(InlineKeyboardButton(text="⬆", callback_data=f"move_task_{task.id}_up"))
            else:
                row.append(InlineKeyboardButton(text="·", callback_data="dummy"))
            
            row.append(InlineKeyboardButton(
                text=f"{position}.{emoji} {task.title[:18]}",
                callback_data=f"update_task_{task.id}"
            ))
            
            if position < len(tasks):
                row.append(InlineKeyboardButton(text="⬇", callback_data=f"move_task_{task.id}_down"))
            else:
                row.append(InlineKeyboardButton(text="·", callback_data="dummy"))
            
            keyboard_buttons.append(row)
        
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅️ Пред", callback_data=f"project_tasks_{project_id}_{page-1}"))
        if end_idx < len(tasks):
            nav_buttons.append(InlineKeyboardButton(text="След ➡️", callback_data=f"project_tasks_{project_id}_{page+1}"))
        
        if nav_buttons:
            keyboard_buttons.append(nav_buttons)
        
        keyboard_buttons.extend([
            [InlineKeyboardButton(text="🔀 Переместить на позицию", callback_data=f"move_any_task_{project_id}")],
            [InlineKeyboardButton(text="➕ Добавить задачу", callback_data=f"add_task_{project_id}")],
            [InlineKeyboardButton(text="🔙 К проекту", callback_data=f"show_roadmap_{project_id}")]
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        completed = len([t for t in tasks if t.status == "completed"])
        in_progress = len([t for t in tasks if t.status == "in_progress"])
        planned = len([t for t in tasks if t.status == "planned"])
        cancelled = len([t for t in tasks if t.status == "cancelled"])
        
        page_info = f" (стр. {page+1}/{((len(tasks)-1)//per_page)+1})" if len(tasks) > per_page else ""
        
        await callback.message.edit_text(
            f"📝 <b>Задачи проекта \"{project.name}\"</b>{page_info}\n\n"
            f"📊 <b>Статистика:</b>\n"
            f"✅ Завершено: <b>{completed}</b> | 🔄 В работе: <b>{in_progress}</b>\n"
            f"⏳ Запланировано: <b>{planned}</b> | ❌ Отменено: <b>{cancelled}</b>\n\n"
            f"💡 ⬆⬇ - быстрое перемещение задач",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("move_task_") & F.data.endswith("_up"))
async def move_task_up_callback(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Переместить задачу на одну позицию вверх"""
    try:
        task_id = int(callback.data.split("_")[2])
        task = await TaskDAO.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена!", show_alert=True)
            return
        
        current_order = task.order_index
        if current_order <= 1:
            await callback.answer("❌ Задача уже в самом верху!", show_alert=True)
            return
            
        new_position = current_order - 1
        success = await TaskDAO.move_task_to_position(session, task_id, new_position)
        
        if success:
            await callback.answer("⬆️ Задача перемещена вверх!")
            
            project = await ProjectDAO.get_project_by_id(session, task.project_id)
            if project and project.channel_id and project.message_id and bot:
                try:
                    updated_tasks = await TaskDAO.get_project_tasks(session, project.id)
                    roadmap_text = format_roadmap_message(project, updated_tasks)
                    
                    await bot.edit_message_text(
                        text=roadmap_text,
                        chat_id=project.channel_id,
                        message_id=project.message_id,
                        parse_mode="HTML"
                    )
                except:
                    pass
            
            await refresh_project_tasks_interface(callback, session, task.project_id)
            
        else:
            await callback.answer("❌ Ошибка перемещения!", show_alert=True)
            
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("move_task_") & F.data.endswith("_down"))
async def move_task_down_callback(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Переместить задачу на одну позицию вниз"""
    try:
        task_id = int(callback.data.split("_")[2])
        task = await TaskDAO.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена!", show_alert=True)
            return
        
        tasks = await TaskDAO.get_project_tasks(session, task.project_id)
        max_position = len(tasks)
        current_order = task.order_index
        
        if current_order >= max_position:
            await callback.answer("❌ Задача уже в самом низу!", show_alert=True)
            return
        
        new_position = current_order + 1
        success = await TaskDAO.move_task_to_position(session, task_id, new_position)
        
        if success:
            await callback.answer("⬇️ Задача перемещена вниз!")
            
            project = await ProjectDAO.get_project_by_id(session, task.project_id)
            if project and project.channel_id and project.message_id and bot:
                try:
                    updated_tasks = await TaskDAO.get_project_tasks(session, project.id)
                    roadmap_text = format_roadmap_message(project, updated_tasks)
                    
                    await bot.edit_message_text(
                        text=roadmap_text,
                        chat_id=project.channel_id,
                        message_id=project.message_id,
                        parse_mode="HTML"
                    )
                except:
                    pass
            
            await refresh_project_tasks_interface(callback, session, task.project_id)
            
        else:
            await callback.answer("❌ Ошибка перемещения!", show_alert=True)
            
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("move_any_task_"))
async def move_any_task_callback(callback: CallbackQuery, session: AsyncSession):
    """Выбрать задачу для перемещения на позицию"""
    try:
        await callback.answer()
        
        project_id = int(callback.data.split("_")[3])
        project = await ProjectDAO.get_project_by_id(session, project_id)
        tasks = await TaskDAO.get_project_tasks(session, project_id)
        
        if not tasks:
            await callback.answer("❌ Нет задач для перемещения!", show_alert=True)
            return
        
        keyboard_buttons = []
        for task in tasks:
            status_emoji = {"planned": "⏳", "in_progress": "🔄", "completed": "✅", "cancelled": "❌"}
            emoji = status_emoji.get(task.status, "❓")
            
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"{task.order_index}. {emoji} {task.title[:25]}...",
                    callback_data=f"move_task_to_{task.id}"
                )
            ])
        
        keyboard_buttons.append([
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"project_tasks_{project_id}_0")
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await callback.message.edit_text(
            f"🔀 <b>Выберите задачу для перемещения</b>\n\n"
            f"📁 Проект: <b>{project.name}</b>\n"
            f"📝 Всего задач: <b>{len(tasks)}</b>\n\n"
            f"👆 Выберите задачу которую хотите переместить:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("move_task_to_"))
async def move_task_to_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Переместить задачу на указанную позицию"""
    try:
        await callback.answer()
        
        task_id = int(callback.data.split("_")[3])
        task = await TaskDAO.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена!", show_alert=True)
            return
        
        project = await ProjectDAO.get_project_by_id(session, task.project_id)
        tasks = await TaskDAO.get_project_tasks(session, task.project_id)
        
        await state.update_data(task_id=task_id, project_id=task.project_id)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"project_tasks_{task.project_id}_0")]
        ])
        
        await callback.message.edit_text(
            f"🔀 <b>Перемещение задачи</b>\n\n"
            f"📝 <b>Задача:</b> {task.title}\n"
            f"📁 <b>Проект:</b> {project.name if project else 'Неизвестен'}\n"
            f"📍 <b>Текущая позиция:</b> {task.order_index}\n\n"
            f"💡 <b>Всего позиций:</b> 1-{len(tasks)}\n\n"
            f"🔢 Введите новую позицию (1-{len(tasks)}):",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        await state.set_state(MoveTaskStates.waiting_for_new_position)
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("select_project_"))
async def select_project_callback(callback: CallbackQuery, state: FSMContext):
    """Выбор проекта для добавления задачи"""
    try:
        await callback.answer()
        
        project_id = int(callback.data.split("_")[2])
        await state.update_data(project_id=project_id)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
        ])
        
        await callback.message.edit_text(
            "📝 <b>Новая задача</b>\n\n"
            "✏️ Введите название задачи:\n\n"
            "<i>Например: \"Создать дизайн главной страницы\"</i>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        await state.set_state(TaskStates.waiting_for_title)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("update_task_"))
async def update_task_callback(callback: CallbackQuery, session: AsyncSession):
    """Обновление статуса задачи"""
    try:
        await callback.answer()
        
        task_id = int(callback.data.split("_")[2])
        task = await TaskDAO.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена!", show_alert=True)
            return
        
        if task.status not in ["planned", "in_progress", "completed", "cancelled"]:
            await TaskDAO.update_task_status(session, task_id, "planned")
            task.status = "planned"
        
        statuses = []
        if task.status == "planned":
            statuses = [
                ("🔄 Взять в работу", "in_progress"),
                ("✅ Завершить сразу", "completed"),
                ("❌ Отменить", "cancelled")
            ]
        elif task.status == "in_progress":
            statuses = [
                ("✅ Завершить", "completed"),
                ("⏳ Запланировать", "planned"),
                ("❌ Отменить", "cancelled")
            ]
        elif task.status == "cancelled":
            statuses = [
                ("⏳ Запланировать", "planned"),
                ("🔄 Взять в работу", "in_progress"),
                ("✅ Завершить", "completed")
            ]
        elif task.status == "completed":
            statuses = [
                ("🔄 Возобновить работу", "in_progress"),
                ("⏳ Запланировать", "planned"),
                ("❌ Отменить", "cancelled")
            ]
        
        keyboard_buttons = []
        for status_text, status_value in statuses:
            callback_data = f"set_status_{task_id}_{status_value}"
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=status_text,
                    callback_data=callback_data
                )
            ])
        
        keyboard_buttons.extend([
            [InlineKeyboardButton(text="🗑 Удалить задачу", callback_data=f"confirm_delete_task_{task_id}")],
            [InlineKeyboardButton(text="🔙 Назад к задачам", callback_data="manage_tasks")]
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        status_names = {
            "planned": "⏳ Запланирована", 
            "in_progress": "🔄 В работе", 
            "completed": "✅ Завершена", 
            "cancelled": "❌ Отменена"
        }
        current_status = status_names.get(task.status, f"❓ {task.status}")
        
        message_text = (
            f"🔄 <b>Управление задачей</b>\n\n"
            f"📝 <b>{task.title}</b>\n"
            f"📄 {task.description or 'Без описания'}\n\n"
            f"🎯 Текущий статус: {current_status}\n\n"
            f"Выберите действие:"
        )
        
        await callback.message.edit_text(
            message_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("set_status_"))
async def set_status_callback(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Установка нового статуса задачи"""
    try:
        parts = callback.data.split("_")
        if len(parts) < 4:
            await callback.answer("❌ Ошибка обработки команды!", show_alert=True)
            return
            
        task_id = int(parts[2])
        new_status = "_".join(parts[3:])

        success = await TaskDAO.update_task_status(session, task_id, new_status)
        
        if not success:
            await callback.answer("❌ Ошибка обновления статуса!", show_alert=True)
            return
        
        task_after = await TaskDAO.get_task_by_id(session, task_id)
        
        if task_after.status != new_status:
            await callback.answer(f"❌ Статус не изменился! Попробуйте снова.", show_alert=True)
            return
        
        await callback.answer("✅ Статус обновлен!")
        
        project = await ProjectDAO.get_project_by_id(session, task_after.project_id)
        
        update_message = ""
        if project and project.channel_id and project.message_id and bot:
            try:
                tasks = await TaskDAO.get_project_tasks(session, project.id)
                roadmap_text = format_roadmap_message(project, tasks)
                
                await bot.edit_message_text(
                    text=roadmap_text,
                    chat_id=project.channel_id,
                    message_id=project.message_id,
                    parse_mode="HTML"
                )
                
                update_message = "\n🔄 Roadmap автоматически обновлен в канале!"
            except Exception as channel_error:
                error_str = str(channel_error).lower()
                if any(phrase in error_str for phrase in [
                    "bot was kicked",
                    "chat not found", 
                    "forbidden",
                    "bot is not a member",
                    "kicked from",
                    "not enough rights"
                ]):
                    await ProjectDAO.remove_channel_from_project(session, project.id)
                    update_message = "\n⚠️ Бот был удален из канала. Канал отвязан от проекта."
                else:
                    update_message = f"\n⚠️ Ошибка обновления канала: {str(channel_error)[:50]}..."
        
        status_names = {
            "planned": "⏳ Запланирована", 
            "in_progress": "🔄 В работе", 
            "completed": "✅ Завершена", 
            "cancelled": "❌ Отменена"
        }
        new_status_text = status_names.get(new_status, f"❓ {new_status}")
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Другие задачи", callback_data="manage_tasks"),
                InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_start")
            ]
        ])
        
        await callback.message.edit_text(
            f"✅ <b>Статус задачи изменен!</b>{update_message}\n\n"
            f"📝 <b>{task_after.title}</b>\n"
            f"🎯 Новый статус: {new_status_text}\n"
            f"📁 Проект: {project.name if project else 'Неизвестен'}",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("show_roadmap_"))
async def show_roadmap_callback(callback: CallbackQuery, session: AsyncSession):
    try:
        await callback.answer()
        
        project_id = int(callback.data.split("_")[2])
        project = await ProjectDAO.get_project_by_id(session, project_id)
        
        if not project:
            await callback.answer("❌ Проект не найден!", show_alert=True)
            return
        
        tasks = await TaskDAO.get_project_tasks(session, project_id)
        roadmap_text = format_roadmap_message(project, tasks)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Добавить задачу", callback_data=f"add_task_{project.id}"),
                InlineKeyboardButton(text="🔄 Обновить канал", callback_data=f"update_channel_{project.id}")
            ],
            [
                InlineKeyboardButton(text="📝 Управление задачами", callback_data=f"project_tasks_{project.id}_0"),
                InlineKeyboardButton(text="📢 Настроить канал", callback_data=f"set_channel_{project.id}")
            ],
            [
                InlineKeyboardButton(text="🗑 Удалить проект", callback_data=f"confirm_delete_project_{project.id}"),
                InlineKeyboardButton(text="🔙 К проектам", callback_data="my_projects")
            ]
        ])
        
        await callback.message.edit_text(
            roadmap_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("add_task_"))
async def add_task_callback(callback: CallbackQuery, state: FSMContext):
    """Добавить задачу к проекту"""
    try:
        await callback.answer()
        
        project_id = int(callback.data.split("_")[2])
        await state.update_data(project_id=project_id)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
        ])
        
        await callback.message.edit_text(
            "📝 <b>Добавление новой задачи</b>\n\n"
            "✏️ Введите название задачи:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        await state.set_state(TaskStates.waiting_for_title)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("update_channel_"))
async def update_channel_callback(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    try:
        project_id = int(callback.data.split("_")[2])
        project = await ProjectDAO.get_project_by_id(session, project_id)

        if not project:
            await callback.answer("❌ Проект не найден!", show_alert=True)
            return
        
        if not project.channel_id:
            await callback.answer("❌ Канал не настроен для этого проекта!", show_alert=True)
            return
        
        channel_status = await check_bot_in_channel(bot, project.channel_id)
        
        if channel_status["status"] == "ok":
            try:
                tasks = await TaskDAO.get_project_tasks(session, project_id)
                roadmap_text = format_roadmap_message(project, tasks)
                
                if project.message_id:
                    await bot.edit_message_text(
                        text=roadmap_text,
                        chat_id=project.channel_id,
                        message_id=project.message_id,
                        parse_mode="HTML"
                    )
                    update_message = "✅ Roadmap успешно обновлен в канале!"
                else:
                    sent_message = await bot.send_message(
                        chat_id=project.channel_id,
                        text=roadmap_text,
                        parse_mode="HTML"
                    )
                    await ProjectDAO.update_roadmap_message(session, project_id, sent_message.message_id)
                    update_message = "✅ Новый Roadmap отправлен в канал!"
                
                await callback.answer(update_message, show_alert=False)

            except Exception as e:
                error_msg = str(e).lower()
                
                if "message is not modified" in error_msg:
                    await callback.answer("✅ Roadmap актуален - изменений нет!", show_alert=False)
                
                elif "message not found" in error_msg or "message_id_invalid" in error_msg or "bad request: message to edit not found" in error_msg:
                    await ProjectDAO.remove_channel_from_project(session, project.id)
                    await callback.answer("❌ Сообщение Roadmap было удалено из канала.\nКанал отвязан от проекта.", show_alert=True)
                
                elif "message too long" in error_msg or "request entity too large" in error_msg:
                    try:
                        try:
                            await bot.delete_message(chat_id=project.channel_id, message_id=project.message_id)
                        except:
                            pass  
                        
                        sent_message = await bot.send_message(
                            chat_id=project.channel_id,
                            text=roadmap_text,
                            parse_mode="HTML"
                        )
                        await ProjectDAO.update_roadmap_message(session, project_id, sent_message.message_id)
                        await callback.answer("✅ Создан новый Roadmap - старый был слишком большим!", show_alert=False)
                        
                    except Exception as e2:
                        await ProjectDAO.remove_channel_from_project(session, project.id)
                        await callback.answer("❌ Не удалось создать новый Roadmap.\nКанал отвязан от проекта.", show_alert=True)
                
                else:
                    await callback.answer(f"❌ Ошибка обновления: {str(e)[:100]}...", show_alert=True)
                
        else:
            await ProjectDAO.remove_channel_from_project(session, project.id)
            await callback.answer("❌ Бот удален из канала - отвязываем канал!", show_alert=True)
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("set_channel_"))
async def set_channel_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Настройка канала для проекта"""
    try:
        await callback.answer()
        
        project_id = int(callback.data.split("_")[2])
        project = await ProjectDAO.get_project_by_id(session, project_id)
        
        if not project:
            await callback.answer("❌ Проект не найден!", show_alert=True)
            return
        
        await state.update_data(project_id=project_id)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
        ])
        
        current_channel = f"\n\n🔗 Текущий канал: <code>{project.channel_id}</code>" if project.channel_id else ""
        
        await callback.message.edit_text(
            f"📢 <b>Настройка канала</b>\n\n"
            f"📁 Проект: <b>{project.name}</b>{current_channel}\n\n"
            f"💬 Введите ID канала или username:\n\n"
            f"<b>Форматы:</b>\n"
            f"• @channel_username\n"
            f"• -100123456789 (ID канала)\n"
            f"• 123456789 (ID чата)\n\n"
            f"⚠️ <b>Важно:</b> Добавьте бота в канал как администратора!",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        await state.set_state(ChannelStates.waiting_for_channel_id)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data == "skip_description")
async def skip_description_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Пропустить описание проекта"""
    try:
        await callback.answer()
        
        data = await state.get_data()
        
        if "name" not in data:
            await callback.answer("❌ Ошибка: название проекта не найдено!", show_alert=True)
            await state.clear()
            return
        
        user = await UserDAO.get_or_create_user(
            session=session,
            telegram_id=callback.from_user.id
        )
        
        project = await ProjectDAO.create_project(
            session=session,
            name=data["name"],
            description="",
            owner_id=user.id
        )
        
        await state.clear()
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Добавить задачу", callback_data=f"add_task_{project.id}"),
                InlineKeyboardButton(text="📢 Настроить канал", callback_data=f"set_channel_{project.id}")
            ],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_start")]
        ])
        
        await callback.message.edit_text(
            f"✅ <b>Проект создан!</b>\n\n"
            f"📁 <b>{project.name}</b>\n\n"
            f"🆔 ID: {project.id}\n"
            f"📅 Создан: {project.created_at.strftime('%d.%m.%Y %H:%M')}",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data == "skip_task_description")
async def skip_task_description_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    """Пропустить описание задачи"""
    try:
        await callback.answer()
        
        data = await state.get_data()
        
        if "title" not in data or "project_id" not in data:
            await callback.answer("❌ Ошибка: данные задачи не найдены!", show_alert=True)
            await state.clear()
            return
        
        user = await UserDAO.get_or_create_user(
            session=session,
            telegram_id=callback.from_user.id
        )
        
        task = await TaskDAO.create_task(
            session=session,
            title=data["title"],
            description="",
            project_id=data["project_id"],
            creator_id=user.id,
            priority="medium"
        )
        
        await state.clear()
        
        project = await ProjectDAO.get_project_by_id(session, data["project_id"])
        
        update_message = ""
        if project and project.channel_id and project.message_id and bot:
            try:
                tasks = await TaskDAO.get_project_tasks(session, project.id)
                roadmap_text = format_roadmap_message(project, tasks)
                
                await bot.edit_message_text(
                    text=roadmap_text,
                    chat_id=project.channel_id,
                    message_id=project.message_id,
                    parse_mode="HTML"
                )
                
                update_message = "\n🔄 Roadmap автоматически обновлен в канале!"
            except Exception as e:
                update_message = f"\n⚠️ Ошибка обновления канала: {str(e)[:50]}..."
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_start")]
        ])
        
        await callback.message.edit_text(
            f"✅ <b>Задача создана!</b>{update_message}\n\n"
            f"📝 <b>{task.title}</b>\n\n"
            f"🆔 ID: {task.id}\n"
            f"📁 Проект: {project.name if project else 'Неизвестен'}",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data == "back_to_start")
async def back_to_start_callback(callback: CallbackQuery, session: AsyncSession):
    """Вернуться в главное меню"""
    try:
        await callback.answer()
        
        user = await UserDAO.get_or_create_user(
            session=session,
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name
        )
        
        projects = await ProjectDAO.get_user_projects(session, user.id)
        total_tasks = 0
        completed_tasks = 0
        
        for project in projects:
            tasks = await TaskDAO.get_project_tasks(session, project.id)
            total_tasks += len(tasks)
            for task in tasks:
                if task.status == "completed":
                    completed_tasks += 1
        
        progress = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 Мои проекты", callback_data="my_projects"),
                InlineKeyboardButton(text="📊 Статистика", callback_data="my_stats")
            ],
            [
                InlineKeyboardButton(text="➕ Создать проект", callback_data="create_project"),
                InlineKeyboardButton(text="📝 Добавить задачу", callback_data="add_task_menu")
            ],
            [
                InlineKeyboardButton(text="🔄 Управление задачами", callback_data="manage_tasks"),
                InlineKeyboardButton(text="🗑 Удаление", callback_data="delete_menu")
            ],
            [
                InlineKeyboardButton(text="❓ Помощь", callback_data="help")
            ]
        ])
        
        welcome_text = (
            f"🎯 <b>Добро пожаловать, {callback.from_user.first_name}!</b>\n\n"
            f"🗺 <b>RoadMapEx</b> - управление проектами в Telegram\n\n"
            f"📊 <b>Ваша статистика:</b>\n"
            f"📁 Проектов: <b>{len(projects)}</b>\n"
            f"📝 Задач: <b>{total_tasks}</b>\n"
            f"✅ Завершено: <b>{completed_tasks}</b>\n"
            f"📈 Прогресс: <b>{progress}%</b>\n\n"
            f"👆 Выберите действие:"
        )
        
        await callback.message.edit_text(welcome_text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data == "cancel_action")
async def cancel_action_callback(callback: CallbackQuery, state: FSMContext):
    """Отмена текущего действия"""
    try:
        await callback.answer("❌ Действие отменено")
        await state.clear()
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_start")]
        ])
        
        await callback.message.edit_text(
            "❌ <b>Действие отменено</b>\n\n"
            "Вы можете вернуться в главное меню.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data == "export_users_json")
async def export_users_json_callback(callback: CallbackQuery, session: AsyncSession):
    """Экспорт пользователей в JSON"""
    try:
        await callback.answer("📄 Экспортирую в JSON...")
        
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("❌ Доступ запрещен!", show_alert=True)
            return
        
        all_users = await UserDAO.get_all_users(session)
        
        users_data = []
        for user in all_users:
            if user.username and user.username.lower().endswith('bot'):
                continue
            
            users_data.append({
                "id": str(user.telegram_id),
                "username": user.username or ""
            })
        
        import json
        json_content = json.dumps(users_data, ensure_ascii=False, indent=2)
        
        filename = f"users_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        from aiogram.types import BufferedInputFile
        file = BufferedInputFile(
            json_content.encode('utf-8'),
            filename=filename
        )
        
        await callback.message.answer_document(
            document=file,
            caption=f"📄 <b>Экспорт пользователей</b>\n\n"
                   f"👥 Всего: <b>{len(users_data)}</b> (без ботов)\n"
                   f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode="HTML"
        )
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка экспорта: {str(e)}", show_alert=True)

@router.callback_query(F.data == "export_users_txt")
async def export_users_txt_callback(callback: CallbackQuery, session: AsyncSession):
    """Экспорт пользователей в TXT"""
    try:
        await callback.answer("📝 Экспортирю в TXT...")
        
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("❌ Доступ запрещен!", show_alert=True)
            return
        
        all_users = await UserDAO.get_all_users(session)
        
        txt_lines = []
        for user in all_users:
            if user.username and user.username.lower().endswith('bot'):
                continue
            txt_lines.append(str(user.telegram_id))
        
        txt_content = '\n'.join(txt_lines)
        
        filename = f"users_ids_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        from aiogram.types import BufferedInputFile
        file = BufferedInputFile(
            txt_content.encode('utf-8'),
            filename=filename
        )
        
        await callback.message.answer_document(
            document=file,
            caption=f"📝 <b>Экспорт ID пользователей</b>\n\n"
                   f"👥 Всего: <b>{len(txt_lines)}</b> (без ботов)\n"
                   f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode="HTML"
        )
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка экспорта: {str(e)}", show_alert=True)

async def refresh_project_tasks_interface(callback: CallbackQuery, session: AsyncSession, project_id: int, page: int = 0):
    """Обновить интерфейс управления задачами проекта в реальном времени"""
    try:
        project = await ProjectDAO.get_project_by_id(session, project_id)
        if not project:
            return
        
        tasks = await TaskDAO.get_project_tasks(session, project_id)
        if not tasks:
            return
        
        per_page = 10
        start_idx = page * per_page
        end_idx = start_idx + per_page
        
        keyboard_buttons = []
        for i, task in enumerate(tasks[start_idx:end_idx]):
            status_emoji = {"planned": "⏳", "in_progress": "🔄", "completed": "✅", "cancelled": "❌"}
            emoji = status_emoji.get(task.status, "❓")
            position = start_idx + i + 1
            
            row = []
            
            if position > 1:
                row.append(InlineKeyboardButton(text="⬆", callback_data=f"move_task_{task.id}_up"))
            else:
                row.append(InlineKeyboardButton(text="·", callback_data="dummy"))
            
            row.append(InlineKeyboardButton(
                text=f"{position}.{emoji} {task.title[:18]}",
                callback_data=f"update_task_{task.id}"
            ))
            
            if position < len(tasks):
                row.append(InlineKeyboardButton(text="⬇", callback_data=f"move_task_{task.id}_down"))
            else:
                row.append(InlineKeyboardButton(text="·", callback_data="dummy"))
            
            keyboard_buttons.append(row)
        
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅️ Пред", callback_data=f"project_tasks_{project_id}_{page-1}"))
        if end_idx < len(tasks):
            nav_buttons.append(InlineKeyboardButton(text="След ➡️", callback_data=f"project_tasks_{project_id}_{page+1}"))
        
        if nav_buttons:
            keyboard_buttons.append(nav_buttons)
        
        keyboard_buttons.extend([
            [InlineKeyboardButton(text="🔀 Переместить на позицию", callback_data=f"move_any_task_{project_id}")],
            [InlineKeyboardButton(text="➕ Добавить задачу", callback_data=f"add_task_{project_id}")],
            [InlineKeyboardButton(text="🔙 К проекту", callback_data=f"show_roadmap_{project_id}")]
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        completed = len([t for t in tasks if t.status == "completed"])
        in_progress = len([t for t in tasks if t.status == "in_progress"])
        planned = len([t for t in tasks if t.status == "planned"])
        cancelled = len([t for t in tasks if t.status == "cancelled"])
        
        page_info = f" (стр. {page+1}/{((len(tasks)-1)//per_page)+1})" if len(tasks) > per_page else ""
        
        new_text = (
            f"📝 <b>Задачи проекта \"{project.name}\"</b>{page_info}\n\n"
            f"📊 <b>Статистика:</b>\n"
            f"✅ Завершено: <b>{completed}</b> | 🔄 В работе: <b>{in_progress}</b>\n"
            f"⏳ Запланировано: <b>{planned}</b> | ❌ Отменено: <b>{cancelled}</b>\n\n"
            f"💡 ⬆⬇ - быстрое перемещение задач"
        )
        
        await callback.message.edit_text(
            new_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except:
        pass

@router.callback_query(F.data == "help")
async def help_callback(callback: CallbackQuery):
    """Показать справку через callback"""
    try:
        await callback.answer()
        await help_command(callback.message)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data == "dummy")
async def dummy_callback(callback: CallbackQuery):
    """Обработчик пустых кнопок"""
    await callback.answer()

@router.message()
async def unknown_message_handler(message: Message):
    """Обработчик неизвестных сообщений"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_start")]
    ])
    
    await message.answer(
        "❓ <b>Неизвестная команда</b>\n\n"
        "Используйте /start для перехода в главное меню или выберите команду из списка:\n\n"
        "/help - Справка\n"
        "/add_project - Создать проект\n"
        "/roadmap - Показать Roadmap",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@router.callback_query()
async def unknown_callback_handler(callback: CallbackQuery):
    """Обработчик неизвестных callback'ов"""
    await callback.answer("❓ Неизвестная команда", show_alert=True)
