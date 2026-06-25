from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

import database, models, schemas
from routers.auth import get_current_user, check_admin

router = APIRouter()


# 1. 获取所有套餐（任何人可见）

@router.get("/", response_model=List[schemas.PackageOut])
def get_packages(show_all: bool = False, db: Session = Depends(database.get_db)):
    if show_all:
        return db.query(models.Package).all()
    return db.query(models.Package).filter(models.Package.is_active == True).all()


# 获取单个套餐详情（前端点套餐进详情页时调用）
@router.get("/{package_id}", response_model=schemas.PackageOut)
def get_package(
        package_id: int,
        db: Session = Depends(database.get_db)
):
    pkg = db.query(models.Package).filter(models.Package.id == package_id).first()
    if not pkg:
        raise HTTPException(status_code=404, detail="套餐不存在")
    return pkg


# 2. 创建套餐（只有管理员）
@router.post("/", response_model=schemas.PackageOut)
def create_package(
        package: schemas.PackageCreate,
        db: Session = Depends(database.get_db),
        admin: models.User = Depends(check_admin)  # 这里验证了管理员身份
):
    db_package = models.Package(**package.model_dump())
    db.add(db_package)
    db.commit()
    db.refresh(db_package)
    return db_package


# 3. 删除套餐（只有管理员）
@router.delete("/{package_id}")
def delete_package(
        package_id: int,
        db: Session = Depends(database.get_db),
        admin: models.User = Depends(check_admin)
):
    db_package = db.query(models.Package).filter(models.Package.id == package_id).first()
    if not db_package:
        raise HTTPException(status_code=404, detail="套餐不存在")

    db.delete(db_package)
    db.commit()
    return {"message": "删除成功"}


# 4. 更新套餐（只有管理员）
@router.put("/{package_id}", response_model=schemas.PackageOut)
def update_package(
        package_id: int,
        package: schemas.PackageUpdate,
        db: Session = Depends(database.get_db),
        admin: models.User = Depends(check_admin)
):
    db_package = db.query(models.Package).filter(models.Package.id == package_id).first()
    if not db_package:
        raise HTTPException(status_code=404, detail="套餐不存在")

    # 更新数据
    for key, value in package.model_dump(exclude_unset=True).items():
        setattr(db_package, key, value)

    db.commit()
    db.refresh(db_package)
    return db_package
