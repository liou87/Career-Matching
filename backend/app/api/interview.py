from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.core.guard import ai_guard
from app.db.session import get_db
from app.services import interview

router = APIRouter(prefix="/interview", tags=["interview"])


@router.post("/{job_id}", response_model=schemas.InterviewPrepOut, dependencies=[Depends(ai_guard)])
def generate(job_id: int, force: bool = False, db: Session = Depends(get_db)):
    """生成面试题。画像、岗位和参考的分析都没变时复用上次结果，force=true 强制重新生成。"""
    return interview.generate(db, job_id, force=force)


@router.get("/{job_id}/latest", response_model=schemas.InterviewPrepOut)
def latest(job_id: int, db: Session = Depends(get_db)):
    return interview.latest(db, job_id)
