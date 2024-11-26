# pylint: skip-file
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from uuid import UUID

# Модель для регистрации
class UserCreate(BaseModel):
    email: str
    password: str

# Модель для входа
class UserLogin(BaseModel):
    email: str
    password: str
#Модель для создания задачи
class TaskCreate(BaseModel):
    title: str
    description: str = None
    due_date: datetime = None  # Используем тип datetime для даты
    priority: int = 1
    status: bool = False
    category_id: Optional[UUID] = None
#Модель для создания категории
class CategoryCreate(BaseModel):
    name: str
