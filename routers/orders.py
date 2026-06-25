from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from fastapi import BackgroundTasks
import database, models, schemas
from routers.auth import get_current_user, check_admin, get_real_ip
from fastapi.responses import StreamingResponse
import io
from openpyxl import Workbook  # 用来写 Excel
from utils.notify import send_order_notification  # 邮件通知
from sqlalchemy.orm import joinedload
from fastapi import Request
from sqlalchemy import text
from urllib.parse import quote  # 用来编码中文文件名
router = APIRouter()


# 1. 用户创建订单（提交安装申请）
@router.post("/", response_model=schemas.OrderOut)
def create_order(
        order: schemas.OrderCreate,
        background_tasks: BackgroundTasks,
        request:Request,
        db: Session = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user),  # 只要登录就行，不用管理员

):
    # 检查套餐是否存在且上架
    package = db.query(models.Package).filter(
        models.Package.id == order.package_id,
        models.Package.is_active == True
    ).first()
    if not package:
        raise HTTPException(status_code=404, detail="套餐不存在或已下架")
    ip = get_real_ip(request)
    # 创建订单
    db_order = models.Order(
        **order.model_dump(),
        submit_ip= ip,
        owner_id=current_user.id,  # 自动关联当前用户
        # package_id=order.package_id
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    # 发送通知邮件
    # 后台发送，不阻塞用户

    background_tasks.add_task(send_order_notification, {
        "order_id": db_order.id,
        "customer_name": db_order.customer_name,
        "contact_phone": db_order.contact_phone,
        "address": db_order.address,
        "package_name": db_order.package.name,
        "price": db_order.package.price,
        "created_at": db_order.created_at.strftime("%Y-%m-%d %H:%M:%S")
    })

    # ✅ 手动构造返回数据，让 Pydantic 自动转嵌套对象
    return schemas.OrderOut(
        id=db_order.id,
        customer_name=db_order.customer_name,
        contact_phone=db_order.contact_phone,
        address=db_order.address,
        status=db_order.status,
        created_at=db_order.created_at,
        submit_ip=db_order.submit_ip,
        # 👇 owner 和 package 直接传字典，Pydantic 会自动转成 UserOut/PackageOut
        owner={
            "id": db_order.owner.id,
            "phone": db_order.owner.phone,
            "is_admin": db_order.owner.is_admin,
            "reg_ip": db_order.owner.reg_ip,
            "last_password_change": db_order.owner.last_password_change
        },
        package={
            "id": db_order.package.id,
            "name": db_order.package.name,
            "description": db_order.package.description,
            "price": db_order.package.price,
            "is_active": db_order.package.is_active
        }
    )



# 2. 用户查看自己的订单
@router.get("/my", response_model=List[schemas.OrderOut])
def get_my_orders(
        db: Session = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    orders = db.query(models.Order).filter(
        models.Order.owner_id == current_user.id
    ).all()
    return orders


# 3. 管理员查看所有订单
from sqlalchemy import text  # ✅ 确保顶部有这行


@router.get("/", response_model=schemas.PageResponse)
def get_all_orders(
        page: int = 1,
        limit: int = 20,
        status: str = None,
        db: Session = Depends(database.get_db),
        admin: models.User = Depends(check_admin)
):
    # ✅ 用原生 SQL 完全绕过 ORM 类型转换
    sql_text = """
        SELECT 
            o.id,
            o.customer_name,
            o.contact_phone,
            o.address,
            o.status,
            o.created_at,
            o.owner_id,
            o.package_id,
            o.submit_ip,
            u.phone as owner_phone,
            u.reg_ip as owner_ip,
            p.name as package_name,
            p.price as package_price
        FROM orders o
        LEFT JOIN users u ON o.owner_id = u.id
        LEFT JOIN packages p ON o.package_id = p.id
    """

    # 如果有状态筛选
    if status:
        sql_text += " WHERE o.status = :status"
        result = db.execute(text(sql_text), {"status": status})
    else:
        result = db.execute(text(sql_text))

    # 拿到所有行（元组形式）
    all_rows = result.fetchall()

    # 算总数
    total = len(all_rows)

    # 分页：只取当前页的数据
    start = (page - 1) * limit
    end = start + limit
    page_rows = all_rows[start:end]

    # 算总页数
    pages = (total + limit - 1) // limit

    # 手动把元组转成字典（模拟 OrderOut 结构）
    data = []
    for row in page_rows:
        # row 结构:
        # (id, 0
        # customer_name, 1
        # contact_phone, 2
        # address, 3
        # status, 4
        # created_at, 5
        # owner_id, 6
        # package_id, 7
        # submit_ip, 8
        # owner_phone, 9
        # owner_ip, 10
        # package_name, 11
        # package_price, 12
        # )

        # 安全处理日期
        created_at_str = ""
        if row[5]:  # created_at
            try:
                if isinstance(row[5], datetime):
                    created_at_str = row[5].strftime("%Y-%m-%d %H:%M:%S")
                else:
                    # 字符串直接转
                    created_at_str = str(row[5])
            except:
                created_at_str = str(row[5])

        data.append({
            "id": row[0],
            "customer_name": row[1] or "",
            "contact_phone": row[2] or "",
            "address": row[3] or "",
            "status": row[4] or "待安装",
            "created_at": created_at_str,
            "submit_ip": row[8],
            "owner": {
                "id": row[6],
                "phone": row[9] or "未知",
                "is_admin": False,  # 简化，不查这个字段
                "reg_ip": row[10],
            } if row[6] else None,
            "package": {
                "id": row[7],
                "name": row[11] or "未知",
                "description": "",
                "price": row[12] or "0",
                "is_active": True
            } if row[7] else None
        })

    # 包装返回
    return {
        "data": data,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": pages
    }

# 4. 管理员更新订单状态（比如标记"已安装"）
@router.put("/{order_id}", response_model=schemas.OrderOut)
def update_order(
        order_id: int,
        order_update: schemas.OrderUpdate,
        db: Session = Depends(database.get_db),
        admin: models.User = Depends(check_admin)
):
    db_order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="订单不存在")

    # 更新状态
    db_order.status = order_update.status
    db.commit()
    db.refresh(db_order)
    # ✅ 手动构造返回，嵌套字段传字典
    return schemas.OrderOut(
        id=db_order.id,
        customer_name=db_order.customer_name,
        contact_phone=db_order.contact_phone,
        address=db_order.address,
        status=db_order.status,
        created_at=db_order.created_at,
        submit_ip=db_order.submit_ip,
        # 👇 owner 和 package 传字典，Pydantic 会自动转成 UserOut/PackageOut
        owner={
            "id": db_order.owner.id,
            "phone": db_order.owner.phone,
            "is_admin": db_order.owner.is_admin,
            "reg_ip": db_order.owner.reg_ip,
            "last_password_change": db_order.owner.last_password_change
        } if db_order.owner else None,
        package={
            "id": db_order.package.id,
            "name": db_order.package.name,
            "description": db_order.package.description,
            "price": db_order.package.price,
            "is_active": db_order.package.is_active
        } if db_order.package else None
    )


# 5. 删除订单（只有管理员）
@router.delete("/{order_id}")
def delete_order(
        order_id: int,
        db: Session = Depends(database.get_db),
        admin: models.User = Depends(check_admin)
):
    db_order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="订单不存在")

    db.delete(db_order)
    db.commit()
    return {"message": "✅ 订单已删除"}

# 导出接口
@router.get("/export")
def export_orders(
        days: int = 30,
        db: Session = Depends(database.get_db),
        admin: models.User = Depends(check_admin)
):
    # ✅ 用原生 SQL + text()，完全绕过 SQLAlchemy 的类型转换
    from sqlalchemy import text

    sql = text("""
        SELECT 
            o.id,
            o.customer_name,
            o.contact_phone,
            o.address,
            o.status,
            o.created_at,
            u.phone as owner_phone,
            p.name as package_name,
            p.price as package_price
        FROM orders o
        LEFT JOIN users u ON o.owner_id = u.id
        LEFT JOIN packages p ON o.package_id = p.id
        ORDER BY o.created_at DESC
    """)

    # ✅ 执行原生查询，拿到的是「原始元组」，不是 ORM 对象
    result = db.execute(sql)
    rows = result.fetchall()

    # 创建内存 Excel
    output = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.title = "订单列表"

    # 写表头
    # headers = ["订单ID", "用户手机号", "姓名", "联系电话", "安装地址", "套餐名称", "价格", "状态", "提交时间"]
    headers = ["订单ID",  "姓名", "联系电话", "安装地址", "套餐名称", "价格", "状态", "提交时间"]
    ws.append(headers)

    # ✅ 手动解析每一行（加 try/except 兜底）
    for row in rows:
        # row 结构: (id, customer_name, contact_phone, address, status, created_at, owner_phone, package_name, package_price)

        # 🔑 关键：安全解析 created_at（SQLite 可能存字符串/空/异常格式）
        created_at_str = ""
        raw_date = row[5]  # created_at 原始值
        if raw_date:
            try:
                # 情况1: 已经是 datetime 对象
                if isinstance(raw_date, datetime):
                    created_at_str = raw_date.strftime("%Y-%m-%d %H:%M:%S")
                # 情况2: 是字符串，尝试解析
                elif isinstance(raw_date, str):
                    # 先清理空白
                    raw_date = raw_date.strip()
                    if raw_date and raw_date != "0000-00-00 00:00:00":
                        # 尝试用 fromisoformat（Python 3.7+）
                        try:
                            dt = datetime.fromisoformat(raw_date.replace(' ', 'T'))
                            created_at_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                        except:
                            # 兜底：直接用原始字符串（至少能显示）
                            created_at_str = raw_date
            except Exception as e:
                # 终极兜底：转字符串 + 记录日志
                created_at_str = str(raw_date)
                print(f"⚠️ 日期解析失败: {raw_date}, 错误: {e}")

        ws.append([
            row[0] or "",  # id
            # row[6] or "未知",  # owner_phone
            row[1] or "",  # customer_name
            row[2] or "",  # contact_phone
            row[3] or "",  # address
            row[7] or "未知",  # package_name
            row[8] or "0",  # package_price
            row[4] or "待安装",  # status
            created_at_str  # ✅ 用安全解析后的日期
        ])

    # 保存并返回
    wb.save(output)
    output.seek(0)

    # ✅ 用 URL 编码处理中文文件名
    filename = "预约报装订单.xlsx"
    encoded_filename = quote(filename)  # 转成 %E9%A2%84...

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )