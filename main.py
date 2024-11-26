# pylint: skip-file
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from database import Base, engine, get_db
from models import User, Task, Category
from schemas import UserCreate, UserLogin, TaskCreate, CategoryCreate
from auth import create_access_token, get_current_user
from utils import hash_password, verify_password
from fastapi.openapi.utils import get_openapi
from fastapi import Path
from uuid import UUID
from rabbitmq_config import setup_notification_queue, publish_notification

# Создает экземпляр приложения FastAPI.
app = FastAPI()

# Создает все таблицы, описанные в моделях SQLAlchemy, в базе данных.
Base.metadata.create_all(bind=engine)

# Настройка кастомной OpenAPI схемы
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="TaskNest API",
        version="1.0.0",
        description="API for managing users, tasks, and notifications",
        routes=app.routes,
    )

    if "components" not in openapi_schema:
        openapi_schema["components"] = {}

    if "securitySchemes" not in openapi_schema["components"]:
        openapi_schema["components"]["securitySchemes"] = {}

    openapi_schema["components"]["securitySchemes"]["bearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }

    for path, methods in openapi_schema["paths"].items():
        for method, details in methods.items():
            if path in ["/tasks/", "/tasks/{id}", "/categories/"] and method in ["post", "put", "delete", "get"]:
                details["security"] = [{"bearerAuth": []}]
            elif path == "/categories/{id}/tasks" and method == "get":
                details["security"] = [{"bearerAuth": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Эндпоинт для проверки подключения
@app.get("/")
def read_root():
    return {"message": "API is working"}

# Эндпоинт для регистрации пользователя
@app.post("/users/register")
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    if not user.email or not user.password:
        raise HTTPException(status_code=400, detail="Email and password are required")
    if len(user.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long")

    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    hashed_password = hash_password(user.password)
    new_user = User(email=user.email, password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User created successfully"}

# Эндпоинт для авторизации пользователя
@app.post("/users/login")
def login_user(user: UserLogin, db: Session = Depends(get_db)):
    if not user.email or not user.password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user or not verify_password(user.password, db_user.password):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    token = create_access_token(data={"user_id": str(db_user.id)})
    return {"access_token": token, "token_type": "bearer"}

# Эндпоинт для получения задач пользователя
@app.get("/users/{id}/tasks")
def get_user_tasks(id: str, db: Session = Depends(get_db)):
    try:
        # Проверяем, является ли ID валидным UUID
        uuid_id = UUID(id, version=4)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format. Must be a valid UUID.")

    # Проверяем наличие пользователя
    user = db.query(User).filter(User.id == uuid_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Получаем задачи пользователя
    tasks = db.query(Task).filter(Task.user_id == uuid_id).all()
    if not tasks:
        raise HTTPException(status_code=404, detail="No tasks found for this user")

    return {"tasks": tasks}


# Эндпоинт для создания задачи
@app.post("/tasks/")
def create_task(task: TaskCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not task.title or not task.priority:
        raise HTTPException(status_code=400, detail="Task title and priority are required")
    if task.priority < 1 or task.priority > 5:
        raise HTTPException(status_code=400, detail="Priority must be between 1 and 5")

    new_task = Task(
        title=task.title,
        description=task.description,
        due_date=task.due_date,
        priority=task.priority,
        status=task.status,
        user_id=current_user.id
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    notification_message = {
        "user_id": str(current_user.id),
        "task_id": str(new_task.id),
        "message": f"Task '{new_task.title}' created successfully!",
        "timestamp": str(new_task.due_date) if new_task.due_date else "No due date"
    }
    publish_notification(notification_message)

    return {"message": "Task created successfully", "task": new_task}

# Эндпоинт для получения списка задач
@app.get("/tasks/")
def get_tasks(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    tasks = db.query(Task).filter(Task.user_id == current_user.id).all()
    if not tasks:
        raise HTTPException(status_code=404, detail="No tasks found")
    return {"tasks": tasks}

# Эндпоинт для обновления задачи
@app.put("/tasks/{id}", summary="Update Task", response_description="The updated task")
def update_task(
    id: str,
    task_update: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        # Проверяем, является ли ID валидным UUID
        uuid_id = UUID(id, version=4)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format. Must be a valid UUID.")

    # Поиск задачи
    task = db.query(Task).filter(Task.id == uuid_id, Task.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Проверки на валидность данных
    if task_update.priority and (task_update.priority < 1 or task_update.priority > 5):
        raise HTTPException(status_code=400, detail="Priority must be between 1 and 5")
    if not task_update.title or task_update.title.strip() == "":
        raise HTTPException(status_code=400, detail="Task title cannot be empty")

    # Обновление задачи
    task.title = task_update.title
    task.description = task_update.description
    task.due_date = task_update.due_date
    task.priority = task_update.priority or task.priority
    task.status = task_update.status

    db.commit()
    db.refresh(task)
    return {"message": "Task updated successfully", "task": task}


@app.delete("/tasks/{id}", summary="Delete Task", response_description="Task deleted")
def delete_task(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        # Проверяем, является ли ID валидным UUID
        uuid_id = UUID(id, version=4)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format. Must be a valid UUID.")

    # Поиск задачи
    task = db.query(Task).filter(Task.id == uuid_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this task")

    # Удаление задачи
    db.delete(task)
    db.commit()
    return {"message": "Task deleted successfully"}


@app.post("/categories/", summary="Create a Category", response_description="The created category")
def create_category(
    category: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not category.name or category.name.strip() == "":
        raise HTTPException(status_code=400, detail="Category name is required")

    existing_category = db.query(Category).filter(
        Category.name == category.name,
        Category.user_id == current_user.id
    ).first()
    if existing_category:
        raise HTTPException(status_code=400, detail="Category already exists")

    new_category = Category(
        name=category.name,
        user_id=current_user.id
    )
    db.add(new_category)
    db.commit()
    db.refresh(new_category)

    return {"message": "Category created successfully", "category": new_category}

@app.get("/categories/", summary="Get all categories", response_description="List of user categories")
def get_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    categories = db.query(Category).filter(Category.user_id == current_user.id).all()
    if not categories:
        raise HTTPException(status_code=404, detail="No categories found")
    return {"categories": categories}

@app.get("/categories/{id}/tasks", summary="Get tasks by category", response_description="List of tasks in a specific category")
def get_tasks_by_category(
    id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not id:
        raise HTTPException(status_code=400, detail="Category ID is required")

    category = db.query(Category).filter(Category.id == id, Category.user_id == current_user.id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found or does not belong to the current user")

    tasks = db.query(Task).filter(Task.category_id == id).all()
    if not tasks:
        raise HTTPException(status_code=404, detail="No tasks found in this category")

    return {"category": category.name, "tasks": tasks}


# Настраиваем очередь для уведомлений
setup_notification_queue()



#http://127.0.0.1:8000
#http://127.0.0.1:8000/docs открыть эту ссылку
#http://127.0.0.1:8000/openapi.json
#venv\Scripts\activate ДЛЯ АКТИВАЦИИ ВИРТУАЛЬНОЙ .. из папки cd D:\Study\3rdForm\Project\SwaggerTask
# ctrl с   для остановки программы в терминале после запуска командой uvicorn main:app --reload
#в конце deactivate

#тестирование - запускаем RabbitMQ start, запускаем вирт окр, далее проект,
#запускаем отдельно файл consumer.py - он будет перехватывать уведомления python consumer.py. Далее видим уведомление о созданной задаче в консоль.
#rabbitMQ http://localhost:15672