from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models, schemas

router = APIRouter(prefix="/checklist", tags=["checklist"])


@router.get("", response_model=list[schemas.ChecklistOut])
def list_checklist(db: Session = Depends(get_db)):
    return db.query(models.Checklist).order_by(models.Checklist.created_at.desc()).all()


@router.post("", response_model=list[schemas.ChecklistOut])
def add_checklist_items(data: schemas.ChecklistCreate, db: Session = Depends(get_db)):
    items = [
        models.Checklist(content=i.content, importance=i.importance, suggestion=i.suggestion, category=i.category)
        for i in data.items
    ]
    db.add_all(items)
    db.commit()
    for item in items:
        db.refresh(item)
    return items


@router.patch("/{item_id}", response_model=schemas.ChecklistOut)
def update_checklist_item(item_id: int, data: schemas.ChecklistUpdate, db: Session = Depends(get_db)):
    item = db.query(models.Checklist).filter(models.Checklist.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    if data.content is not None:
        item.content = data.content
    if data.status is not None:
        item.status = data.status
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}")
def delete_checklist_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(models.Checklist).filter(models.Checklist.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    db.delete(item)
    db.commit()
    return {"ok": True}
