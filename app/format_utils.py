from datetime import datetime
from typing import List
from models import Project, Task

def format_roadmap_message(project: Project, tasks: List[Task]) -> str:
    """Форматирование роадмапа для отправки в канал"""
    
    roadmap = f"🗺 <b>Roadmap проекта: {project.name}</b>\n\n"
    
    if project.description:
        roadmap += f"📄 {project.description}\n\n"
    
    sorted_tasks = sorted(tasks, key=lambda t: t.order_index)
    
    total_tasks = len(sorted_tasks)
    completed_tasks = len([t for t in sorted_tasks if t.status == "completed"])
    in_progress_tasks = len([t for t in sorted_tasks if t.status == "in_progress"])
    planned_tasks = len([t for t in sorted_tasks if t.status == "planned"])
    cancelled_tasks = len([t for t in sorted_tasks if t.status == "cancelled"])
    
    progress = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
    
    roadmap += f"📊 <b>Прогресс проекта: {progress}%</b>\n"
    roadmap += f"{'▓' * (progress // 10)}{'░' * (10 - progress // 10)} {completed_tasks}/{total_tasks}\n\n"
    
    if not sorted_tasks:
        roadmap += "📝 <i>Задачи пока не добавлены</i>\n\n"
    else:
        roadmap += f"📋 <b>Задачи ({total_tasks}):</b>\n"
        
        for task in sorted_tasks:
            if task.status == "completed":
                emoji = "✅"
            elif task.status == "in_progress":
                emoji = "🔄"
            elif task.status == "planned":
                emoji = "⏳"
            elif task.status == "cancelled":
                emoji = "❌"
            else:
                emoji = "❓"
            
            roadmap += f"{emoji} {task.title}\n"
            
            if task.description:
                roadmap += f"    - {task.description}\n"
    
    if total_tasks > 0:
        roadmap += f"\n📈 <b>Статистика:</b>\n"
        if completed_tasks > 0:
            roadmap += f"✅ Завершено: {completed_tasks}\n"
        if in_progress_tasks > 0:
            roadmap += f"🔄 В работе: {in_progress_tasks}\n"
        if planned_tasks > 0:
            roadmap += f"⏳ Запланировано: {planned_tasks}\n"
        if cancelled_tasks > 0:
            roadmap += f"❌ Отменено: {cancelled_tasks}\n"
        roadmap += "\n"
    
    roadmap += f"🕐 Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
    roadmap += f"🤖 <a href='https://t.me/roadmapex_bot'>RoadMapEx Bot</a>"
    
    return roadmap

def format_task_status_emoji(status: str) -> str:
    """Получить эмодзи для статуса задачи"""
    status_emojis = {
        "planned": "⏳",
        "in_progress": "🔄", 
        "completed": "✅",
        "cancelled": "❌"
    }
    return status_emojis.get(status, "❓")

def format_task_status_text(status: str) -> str:
    """Получить текстовое описание статуса задачи"""
    status_texts = {
        "planned": "Запланирована",
        "in_progress": "В работе",
        "completed": "Завершена", 
        "cancelled": "Отменена"
    }
    return status_texts.get(status, "Неизвестно")

def format_project_stats(tasks: List[Task]) -> dict:
    """Получить статистику проекта"""
    total = len(tasks)
    completed = len([t for t in tasks if t.status == "completed"])
    in_progress = len([t for t in tasks if t.status == "in_progress"])
    planned = len([t for t in tasks if t.status == "planned"])
    cancelled = len([t for t in tasks if t.status == "cancelled"])
    
    progress = int((completed / total) * 100) if total > 0 else 0
    
    return {
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "planned": planned,
        "cancelled": cancelled,
        "progress": progress
    }

def format_progress_bar(progress: int, width: int = 10) -> str:
    """Создать прогресс-бар"""
    filled = int(progress / 100 * width)
    empty = width - filled
    return "▓" * filled + "░" * empty

def format_task_list_compact(tasks: List[Task], max_tasks: int = 5) -> str:
    """Компактный список задач для отображения в сообщениях"""
    if not tasks:
        return "📝 <i>Задач нет</i>"
    
    result = ""
    shown_tasks = tasks[:max_tasks]
    
    for i, task in enumerate(shown_tasks, 1):
        emoji = format_task_status_emoji(task.status)
        result += f"{emoji} {task.title[:30]}{'...' if len(task.title) > 30 else ''}\n"
    
    if len(tasks) > max_tasks:
        result += f"... и еще {len(tasks) - max_tasks} задач\n"
    
    return result