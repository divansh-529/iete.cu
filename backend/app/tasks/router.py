from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import require_in_service
from app.core.db import get_db
from app.tasks import service
from app.tasks.schemas import (AssigneesIn, CommentIn, ReopenIn, ReviewIn, SubmissionIn, TaskCreateIn,
                               TaskDetailOut, TaskIn, TaskOut)
from app.users.models import User

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

# Assignees, reviewers and event owners work on tasks whatever their grants, so routes only
# require a signed-in user and the service checks the tasks.* permission or involvement.


@router.get("", response_model=list[TaskOut])
def list_tasks(view: Literal["visible", "mine", "review"] = "visible", department_id: int | None = None,
               event_id: int | None = None, status: str | None = None, q: str | None = None,
               user: User = Depends(require_in_service("tasks.view")), db: Session = Depends(get_db)):
    return service.summaries(db, service.list_tasks(db, user, view, department_id, event_id, status, q))


@router.post("", response_model=TaskDetailOut, status_code=201)
def create_task(body: TaskCreateIn, actor: User = Depends(require_in_service("tasks.create")),
                db: Session = Depends(get_db)):
    return service.detail(db, actor, service.create_task(db, actor, body).id)


@router.get("/{task_id}", response_model=TaskDetailOut)
def get_task(task_id: int, user: User = Depends(require_in_service("tasks.view")), db: Session = Depends(get_db)):
    return service.detail(db, user, task_id)


@router.put("/{task_id}", response_model=TaskDetailOut)
def update_task(task_id: int, body: TaskIn, actor: User = Depends(require_in_service("tasks.create")),
                db: Session = Depends(get_db)):
    service.update_task(db, actor, task_id, body)
    return service.detail(db, actor, task_id)


@router.put("/{task_id}/assignees", response_model=TaskDetailOut)
def set_assignees(task_id: int, body: AssigneesIn, actor: User = Depends(require_in_service("tasks.assign")),
                  db: Session = Depends(get_db)):
    service.set_assignees(db, actor, task_id, body)
    return service.detail(db, actor, task_id)


@router.post("/{task_id}/start", response_model=TaskDetailOut)
def start(task_id: int, actor: User = Depends(require_in_service("tasks.view")), db: Session = Depends(get_db)):
    service.start(db, actor, task_id)
    return service.detail(db, actor, task_id)


@router.post("/{task_id}/submissions", response_model=TaskDetailOut, status_code=201)
def submit(task_id: int, body: SubmissionIn, actor: User = Depends(require_in_service("tasks.view")),
           db: Session = Depends(get_db)):
    service.submit(db, actor, task_id, body)
    return service.detail(db, actor, task_id)


@router.post("/{task_id}/review", response_model=TaskDetailOut)
def review(task_id: int, body: ReviewIn, actor: User = Depends(require_in_service("tasks.review")),
           db: Session = Depends(get_db)):
    service.review(db, actor, task_id, body)
    return service.detail(db, actor, task_id)


@router.post("/{task_id}/reopen", response_model=TaskDetailOut)
def reopen(task_id: int, body: ReopenIn, actor: User = Depends(require_in_service("tasks.create")),
           db: Session = Depends(get_db)):
    service.reopen(db, actor, task_id, body)
    return service.detail(db, actor, task_id)


@router.post("/{task_id}/comments", response_model=TaskDetailOut, status_code=201)
def add_comment(task_id: int, body: CommentIn, actor: User = Depends(require_in_service("tasks.view")),
                db: Session = Depends(get_db)):
    service.add_comment(db, actor, task_id, body)
    return service.detail(db, actor, task_id)
