from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import database, models
from routers.auth import check_admin, get_current_user

router = APIRouter()



@router.get("/", response_model=list)
def get_users(
        db: Session = Depends(database.get_db),
        admin: models.User = Depends(check_admin)
):
    users = db.query(models.User).all()
    return [
        {
            "id": u.id,
            "phone": u.phone,
            "is_admin": u.is_admin,
            "reg_ip": u.reg_ip,
            "last_password_change": u.last_password_change
        }
        for u in users
    ]


@router.delete("/{user_id}")
def delete_user(
        user_id: int,
        db: Session = Depends(database.get_db),
        admin: models.User = Depends(check_admin)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.is_admin:
        raise HTTPException(status_code=400, detail="不能删除管理员")

    db.delete(user)
    db.commit()
    return {"msg": "删除成功"}


# 提升为管理员（只有管理员能操作）
@router.put("/{user_id}/promote")
def promote_to_admin(
        user_id: int,
        db: Session = Depends(database.get_db),
        admin: models.User = Depends(check_admin)  # 只有管理员能调用
):
    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target_user.is_admin:
        raise HTTPException(status_code=400, detail="该用户已经是管理员")

    target_user.is_admin = True
    db.commit()
    return {"message": "✅ 已提升为管理员"}
# 降级为普通用户（只有管理员能操作，且不能降级自己）
@router.put("/{user_id}/demote")
def demote_from_admin(
        user_id: int,
        db: Session = Depends(database.get_db),
        admin: models.User = Depends(check_admin),      # 当前操作的管理员
        current_user: models.User = Depends(get_current_user)  # 可选，用于获取当前登录用户（实际 admin 已经是当前用户）
):
    # 注意：check_admin 已经返回了当前登录的管理员对象，所以可以直接使用 admin.id
    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not target_user.is_admin:
        raise HTTPException(status_code=400, detail="该用户已经是普通用户")
    # 禁止降级自己
    if target_user.id == admin.id:
        raise HTTPException(status_code=400, detail="不能降级自己的管理员权限")
    target_user.is_admin = False
    db.commit()
    return {"message": "✅ 已降级为普通用户"}