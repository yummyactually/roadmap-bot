from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import User, Project, Task, TaskStatus
from config import ADMIN_ID, LOG_LEVEL
import logging

logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
                
logger = logging.getLogger(__name__)
logger.info(__name__)

class UserDAO:
    """Data Access Object для работы с пользователями"""
    
    @staticmethod
    async def get_or_create_user(
        session: AsyncSession,
        telegram_id: int,
        username: str = None,
        first_name: str = None,
        last_name: str = None
    ) -> User:
        """Получить существующего пользователя или создать нового"""
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                is_admin=(telegram_id == ADMIN_ID)
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        else:
            updated = False
            if user.username != username:
                user.username = username
                updated = True
            if user.first_name != first_name:
                user.first_name = first_name
                updated = True
            if user.last_name != last_name:
                user.last_name = last_name
                updated = True
            
            if updated:
                await session.commit()
        
        return user
    
    @staticmethod
    async def set_admin(session: AsyncSession, telegram_id: int, is_admin: bool = True):
        """Назначить или снять права администратора"""
        await session.execute(
            update(User)
            .where(User.telegram_id == telegram_id)
            .values(is_admin=is_admin)
        )
        await session.commit()
    
    @staticmethod
    async def get_all_users(session: AsyncSession) -> List[User]:
        """Получить всех пользователей"""
        result = await session.execute(select(User).order_by(User.created_at.desc()))
        return result.scalars().all()

class ProjectDAO:
    """Data Access Object для работы с проектами"""
    
    @staticmethod
    async def create_project(
        session: AsyncSession,
        name: str,
        description: str,
        owner_id: int,
        channel_id: str = None
    ) -> Project:
        """Создать новый проект"""
        project = Project(
            name=name,
            description=description,
            owner_id=owner_id,
            channel_id=channel_id
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project
    
    @staticmethod
    async def get_project_by_id(session: AsyncSession, project_id: int) -> Optional[Project]:
        """Получить проект по ID с задачами"""
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.tasks))
            .where(Project.id == project_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_projects(session: AsyncSession, user_id: int) -> List[Project]:
        """Получить все проекты пользователя"""
        result = await session.execute(
            select(Project)
            .where(Project.owner_id == user_id, Project.is_active == True)
            .order_by(Project.created_at.desc())
        )
        return result.scalars().all()
    
    @staticmethod
    async def update_project(
        session: AsyncSession,
        project_id: int,
        name: str = None,
        description: str = None,
        channel_id: str = None
    ):
        """Обновить проект"""
        update_data = {"updated_at": datetime.now(timezone.utc)}
        
        if name is not None:
            update_data["name"] = name
        if description is not None:
            update_data["description"] = description
        if channel_id is not None:
            update_data["channel_id"] = channel_id
        
        await session.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(**update_data)
        )
        await session.commit()
    
    @staticmethod
    async def update_roadmap_message(
        session: AsyncSession,
        project_id: int,
        message_id: int
    ):
        """Обновить ID сообщения с роадмапом в канале"""
        await session.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(message_id=message_id, updated_at=datetime.now(timezone.utc))
        )
        await session.commit()
    
    @staticmethod
    async def remove_channel_from_project(session: AsyncSession, project_id: int):
        """Удалить канал из проекта (при кике бота)"""
        await session.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(
                channel_id=None,
                message_id=None,
                updated_at=datetime.now(timezone.utc)
            )
        )
        await session.commit()
    
    @staticmethod
    async def get_projects_by_channel(session: AsyncSession, channel_id: str) -> List[Project]:
        """Получить все проекты по ID канала"""
        result = await session.execute(
            select(Project).where(Project.channel_id == channel_id)
        )
        return result.scalars().all()
    
    @staticmethod
    async def delete_project(session: AsyncSession, project_id: int):
        """Удалить проект"""
        await session.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(is_active=False, updated_at=datetime.now(timezone.utc))
        )
        await session.commit()

class TaskDAO:
    """Data Access Object для работы с задачами"""
    
    @staticmethod
    async def create_task(
        session: AsyncSession,
        title: str,
        description: str,
        project_id: int,
        creator_id: int,
        priority: str = "medium",
        estimated_days: int = None
    ) -> Task:
        """Создать новую задачу"""
        result = await session.execute(
            select(func.coalesce(func.max(Task.order_index), 0) + 1)
            .where(Task.project_id == project_id)
        )
        next_order = result.scalar()
        
        task = Task(
            title=title,
            description=description,
            project_id=project_id,
            creator_id=creator_id,
            priority=priority,
            estimated_days=estimated_days,
            order_index=next_order,
            status="planned",  
            created_at=datetime.now(timezone.utc)  
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return task
    
    @staticmethod
    async def get_project_tasks(session: AsyncSession, project_id: int) -> List[Task]:
        """Получить все задачи проекта в правильном порядке"""
        result = await session.execute(
            select(Task)
            .where(Task.project_id == project_id)
            .order_by(Task.order_index.asc())
        )
        return result.scalars().all()
    
    @staticmethod
    async def get_task_by_id(session: AsyncSession, task_id: int) -> Optional[Task]:
        """Получить задачу по ID"""
        result = await session.execute(
            select(Task).where(Task.id == task_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def update_task_status(
        session: AsyncSession,
        task_id: int,
        status: str
    ):
        """Обновить статус задачи"""
        valid_statuses = ["planned", "in_progress", "completed", "cancelled"]
        if status not in valid_statuses:
            return False
        
        task = await TaskDAO.get_task_by_id(session, task_id)
        if not task:
            return False
        
        update_data = {"status": status, "updated_at": datetime.now(timezone.utc)}
        
        if status == "completed":
            update_data["completed_at"] = datetime.now(timezone.utc)
            
            if task.created_at:
                created_at = task.created_at
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                
                completed_at = datetime.now(timezone.utc)
                actual_days = (completed_at - created_at).days
                update_data["actual_days"] = max(actual_days, 1)
        
        await session.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(**update_data)
        )
        
        await session.commit()
        
        updated_task = await TaskDAO.get_task_by_id(session, task_id)
        if not updated_task:
            logger.warning(f"Ошибка: задача {task_id} не найдена после обновления")
        
        return True
    
    @staticmethod
    async def update_task(
        session: AsyncSession,
        task_id: int,
        title: str = None,
        description: str = None,
        priority: str = None,
        estimated_days: int = None
    ):
        """Обновить задачу"""
        update_data = {"updated_at": datetime.now(timezone.utc)}
        
        if title is not None:
            update_data["title"] = title
        if description is not None:
            update_data["description"] = description
        if priority is not None:
            update_data["priority"] = priority
        if estimated_days is not None:
            update_data["estimated_days"] = estimated_days
        
        await session.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(**update_data)
        )
        await session.commit()
    
    @staticmethod
    async def delete_task(session: AsyncSession, task_id: int):
        """Удалить задачу"""
        await session.execute(
            delete(Task).where(Task.id == task_id)
        )
        await session.commit()
    
    @staticmethod
    async def calculate_project_progress(session: AsyncSession, project_id: int) -> dict:
        """Вычислить прогресс проекта"""
        result = await session.execute(
            select(
                func.count(Task.id).label('total'),
                func.sum(func.case((Task.status == 'completed', 1), else_=0)).label('completed'),
                func.sum(func.case((Task.status == 'in_progress', 1), else_=0)).label('in_progress'),
                func.sum(func.case((Task.status == 'planned', 1), else_=0)).label('planned')
            ).where(Task.project_id == project_id)
        )
        
        stats = result.one()
        total = stats.total or 0
        completed = stats.completed or 0
        in_progress = stats.in_progress or 0
        planned = stats.planned or 0
        
        progress_percent = int((completed / total) * 100) if total > 0 else 0
        
        return {
            'total': total,
            'completed': completed,
            'in_progress': in_progress,
            'planned': planned,
            'progress_percent': progress_percent
        }

    @staticmethod
    async def move_task_to_position(
        session: AsyncSession,
        task_id: int,
        new_position: int
    ):
        """Переместить задачу на новую позицию"""
        task = await TaskDAO.get_task_by_id(session, task_id)
        if not task:
            return False
        
        if new_position < 1 or new_position > len(tasks):
            return False
        
        current_position = task.order_index
        
        if current_position == new_position:
            return True
        
        if current_position < new_position:
            for t in tasks:
                if t.id == task_id:
                    continue
                if current_position < t.order_index <= new_position:
                    await session.execute(
                        update(Task)
                        .where(Task.id == t.id)
                        .values(order_index=t.order_index - 1)
                    )
        else:
            for t in tasks:
                if t.id == task_id:
                    continue
                if new_position <= t.order_index < current_position:
                    await session.execute(
                        update(Task)
                        .where(Task.id == t.id)
                        .values(order_index=t.order_index + 1)
                    )
        
        await session.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(order_index=new_position, updated_at=datetime.now(timezone.utc))
        )
        
        await session.commit()
        
        return True

    @staticmethod
    async def move_task_to_position(
        session: AsyncSession,
        task_id: int,
        new_position: int
    ):
        """Переместить задачу на новую позицию"""
        
        task = await TaskDAO.get_task_by_id(session, task_id)
        if not task:
            return False
        
        project_id = task.project_id
        current_position = task.order_index
        
        result = await session.execute(
            select(Task)
            .where(Task.project_id == project_id)
            .order_by(Task.order_index.asc())
        )
        all_tasks = result.scalars().all()
        
        if new_position < 1 or new_position > len(all_tasks):
            return False
        
        if current_position == new_position:
            return True
        
        if current_position < new_position:
            for i, t in enumerate(all_tasks):
                if t.id == task_id:
                    new_order = new_position
                elif t.order_index <= current_position:
                    new_order = t.order_index
                elif t.order_index <= new_position:
                    new_order = t.order_index - 1
                else:
                    new_order = t.order_index
                
                await session.execute(
                    update(Task)
                    .where(Task.id == t.id)
                    .values(order_index=new_order)
                )
        else:
            for i, t in enumerate(all_tasks):
                if t.id == task_id:
                    new_order = new_position
                elif t.order_index < new_position:
                    new_order = t.order_index
                elif t.order_index < current_position:
                    new_order = t.order_index + 1
                else:
                    new_order = t.order_index
                
                await session.execute(
                    update(Task)
                    .where(Task.id == t.id)
                    .values(order_index=new_order)
                )
        
        await session.commit()
        
        result_after = await session.execute(
            select(Task)
            .where(Task.project_id == project_id)
            .order_by(Task.order_index.asc())
        )
        tasks_after = result_after.scalars().all()
        return True