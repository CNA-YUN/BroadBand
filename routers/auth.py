from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from utils.sms import send_sms_code, verify_code, RESET_SEND_KEY, CAPTCHA_KEY_PREFIX
from utils.sms import check_password_reset_limit, record_password_reset
import database, models, schemas
import re
import os
from io import BytesIO
import random
import string
import time
from dotenv import load_dotenv
from fastapi import APIRouter, Request, HTTPException, Depends, status, Request
from fastapi.responses import StreamingResponse
from captcha.image import ImageCaptcha
from utils.redis_client import redis_client

router = APIRouter()

# 密码加密工具
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# 通行证的密钥
load_dotenv('./setting.env')
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")

def get_real_ip(request: Request) -> str:
    """
    从请求头中获取真实客户端 IP
    优先 X-Forwarded-For（标准代理头），其次 X-Real-IP，最后 fallback 到 client.host
    """
    # X-Forwarded-For 可能包含多个 IP，取第一个（最原始客户端）
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host

# 1. 加密密码
def hash_password(password: str):
    return pwd_context.hash(password)


# 2. 验证密码
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


# 3. 生成通行证 (Token)
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=60))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# 定义如何获取令牌
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# 获取当前用户
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # 解码令牌
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        phone: str = payload.get("sub")
        if phone is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # 从数据库找用户
    user = db.query(models.User).filter(models.User.phone == phone).first()
    if user is None:
        raise credentials_exception
    return user


# 检查是不是管理员
def check_admin(current_user: models.User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="权限不足，只有管理员能操作")
    return current_user


# 检查密码是否是强密码
def is_strong_password(password: str) -> bool:
    if len(password) < 8:
        return False
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return False
    return True


# 注册接口（改成带验证码的版本）
@router.post("/register", response_model=schemas.UserOut)
def register(
        req: schemas.RegisterWithCode,  # 改成新表单
        request: Request,
        db: Session = Depends(database.get_db)

    ):
    """
    注册新用户
    :param request: ip
    :param req: 手机号,密码,验证码,是否为管理员
    :param db: 数据库
    :return: new_user
    """
    # 检查是否是强密码
    if not is_strong_password(req.password):
        raise HTTPException(status_code=400, detail="密码至少 8 位，需包含字母和数字")

    # 验证验证码
    if not verify_code(req.phone, req.code):
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    # 验证码通过后，再执行注册逻辑
    db_user = db.query(models.User).filter(models.User.phone == req.phone).first()
    if db_user:
        raise HTTPException(status_code=400, detail="手机号已被注册")
    ip = get_real_ip(request)
    hashed_pw = hash_password(req.password)
    new_user = models.User(
        phone=req.phone,
        hashed_password=hashed_pw,
        is_admin=req.is_admin,
        reg_ip=ip
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


# 登录接口
@router.post("/login", response_model=schemas.Token)
def login(user: schemas.UserLogin, db: Session = Depends(database.get_db)):
    """
    输入手机号和密码进行登录
    :param user: 手机号,密码
    :param db: 数据库
    :return: access_token
    """
    # 找用户
    db_user = db.query(models.User).filter(models.User.phone == user.phone).first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=400, detail="手机号或密码错误")

    # 发通行证
    access_token = create_access_token(data={"sub": db_user.phone,
                                             "id": db_user.id,
                                             "is_admin": db_user.is_admin
                                             }
                                       )
    return {"access_token": access_token,
            "token_type": "Bearer"
            }


# 发送注册验证码接口（任何人可调用）
@router.post("/send-code")
def send_code(req: schemas.SendCodeRequest,
              request: Request,
              # captcha: str,
              db: Session = Depends(database.get_db)):
    """
    发送注册验证码
    60秒内只能发一次
    发送验证码前检查手机号格式以及是否注册

    :param captcha:用户输入的图形验证码
    :param request:http请求
    :param req:手机号
    :param db:数据库
    :return:{message:str}
    """
    # 验证图形验证码
    # if captcha.upper() != getattr(get_captcha, "last_code", ""):
    #     raise HTTPException(status_code=400, detail="图形验证码错误")

    # 获取用户 IP
    client_ip = get_real_ip(request)
    print(f"📍 请求来自真实IP：{client_ip}")

    # 简单校验手机号格式
    if not req.phone.startswith("1") or len(req.phone) != 11:
        raise HTTPException(status_code=400, detail="手机号格式不正确")

    # 检查是否已注册
    if db.query(models.User).filter(models.User.phone == req.phone).first():
        raise HTTPException(status_code=400, detail="该手机号已注册")

    # 发送短信（加个简单限流：60 秒内只能发一次）
    if not hasattr(send_code, "last_send"):
        send_code.last_send = {}

    last_time = send_code.last_send.get(req.phone, 0)
    if time.time() - last_time < 60:
        raise HTTPException(status_code=429, detail="请稍后再试（60 秒限制）")

    # 将用户IP传给发送函数
    success = send_sms_code(req.phone, client_ip=client_ip)

    if success:
        send_code.last_send[req.phone] = time.time()
        return {"message": "验证码已发送"}
    else:
        raise HTTPException(status_code=500, detail="发送失败，请稍后重试")


# 发送"改密验证码"
@router.post("/send-reset-code")
def send_reset_code(
        req: schemas.SendResetCodeRequest,
        request: Request,  # 加这个参数，获取 IP
        db: Session = Depends(database.get_db)
):
    """
    发送忘记密码的验证码
    限制：同 1个手机号 24 小时内只能改一次密码，24 小时内只能发一次验证码；同 1 个 ip 一天内只能发 3 次验证码
    """

    # 1. 检查手机号是否存在
    user = db.query(models.User).filter(models.User.phone == req.phone).first()
    if not user:
        raise HTTPException(status_code=404, detail="该手机号未注册")

    # 2. 检查 24 小时内是否改过密码（数据库记录）
    if user.last_password_change:
        time_since_last_change = datetime.now() - user.last_password_change
        if time_since_last_change < timedelta(hours=24):
            remaining = 24 - time_since_last_change.total_seconds() / 3600
            raise HTTPException(
                status_code=429,
                detail=f"24 小时内只能修改一次密码，请 {remaining:.1f} 小时后再试"
            )

    # 3. 检查 24 小时内是否发过改密验证码（Redis 记录）
    send_key = f"{RESET_SEND_KEY}{req.phone}"
    if redis_client.exists(send_key):
        ttl = redis_client.ttl(send_key)  # 获取剩余过期时间
        remaining = ttl / 3600  # 转成小时
        raise HTTPException(
            status_code=429,
            detail=f"24 小时内只能发送一次改密验证码，请 {remaining:.1f} 小时后再试"
        )

    # 4. 检查 IP 频率限制，防止同一 IP 狂试不同手机号
    client_ip =get_real_ip(request)
    ip_key = f"sms:reset_ip:{client_ip}"
    ip_count = redis_client.get(ip_key)
    if ip_count and int(ip_count) >= 3:  # 单 IP 每天最多 3 次
        raise HTTPException(status_code=429, detail="请求太频繁，请稍后再试")

    # 5. 发送短信验证码
    success = send_sms_code(req.phone)
    if success:
        # ✅ 记录发送时间，24 小时自动过期
        redis_client.setex(send_key, 86400, "1")  # 86400 秒 = 24 小时

        # 记录 IP 请求（每天限 3 次）
        redis_client.incr(ip_key)
        redis_client.expire(ip_key, 86400)

        return {"message": "验证码已发送，请检查短信"}
    else:
        raise HTTPException(status_code=500, detail="发送失败，请稍后重试")


# 执行"重置密码"
@router.post("/reset-password")
def reset_password(req: schemas.ResetPasswordRequest, db: Session = Depends(database.get_db)):
    # 1. 验证短信验证码
    if not verify_code(req.phone, req.code):
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    # 2. 检查 24 小时限制
    allowed, message = check_password_reset_limit(req.phone)
    if not allowed:
        raise HTTPException(status_code=429, detail=message)

    # 3. 更新密码
    user = db.query(models.User).filter(models.User.phone == req.phone).first()
    user.hashed_password = hash_password(req.new_password)
    user.last_password_change = datetime.now()
    db.commit()

    # 4. 记录改密时间（Redis）
    record_password_reset(req.phone)

    return {"message": "密码修改成功"}


@router.get("/captcha")
def get_captcha(phone: str = None, request: Request = None):
    """
    生成图形验证码（生产级优化）
    :param phone: 可选，绑定手机号（改密/注册时用）
    :param request: 自动注入，获取 IP 做限流
    """

    # 1. IP 频率限制（防脚本狂刷）
    client_ip = get_real_ip(request)
    ip_key = f"captcha:ip:{client_ip}"
    ip_count = redis_client.get(ip_key)

    if ip_count and int(ip_count) >= 100:  # 单 IP 每小时最多 10 次
        raise HTTPException(status_code=429, detail="请求太频繁，请稍后再试")

    # 2. 生成 4 位随机字符（大小写 + 数字，增加难度）
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

    # 3. 生成图片（增加干扰线，防 OCR）
    image = ImageCaptcha(
        width=150,  # 加宽
        height=50,  # 加高
        font_sizes=(28, 32)  # 随机字体大小
    )
    image_data = image.generate(code)

    # 4. 存到内存
    buf = BytesIO()
    image_data.write(buf)
    buf.seek(0)

    # 5. 验证码存 Redis（
    # 生成唯一 session_id（如果没传 phone）
    session_id = phone if phone else f"session:{client_ip}:{int(time.time())}"
    captcha_key = f"{CAPTCHA_KEY_PREFIX}{session_id}"

    # 存验证码，5 分钟自动过期
    redis_client.setex(captcha_key, 300, code.upper())  # 统一转大写

    # 6. 记录 IP 请求（限流）
    redis_client.incr(ip_key)
    redis_client.expire(ip_key, 3600)  # 1 小时过期

    print(f"✅ 验证码已生成：{session_id} (测试用：{code})")

    # 7. 返回图片
    return StreamingResponse(buf, media_type="image/png", headers={
        "Cache-Control": "no-store, no-cache, must-revalidate",  # 禁止缓存
        "Pragma": "no-cache",
        "Expires": "0"
    })


@router.post("/verify-captcha")
def verify_captcha(
        session_id: str,  # 手机号或 session_id
        code: str,
        action: str = "register"  # 用途：register/reset/send_sms
):
    """
    验证图形验证码
    :param session_id: 手机号（绑定用）或 session_id
    :param code: 用户输入的验证码
    :param action: 用途（用于区分不同场景）
    """
    captcha_key = f"{CAPTCHA_KEY_PREFIX}{session_id}"

    # 1. 从 Redis 取验证码
    stored_code = redis_client.get(captcha_key)

    if not stored_code:
        raise HTTPException(status_code=400, detail="验证码已过期，请刷新")

    # 2. 比对（统一转大写，不区分大小写）
    if stored_code.upper() == code.upper():
        # ✅ 验证成功：立即删除验证码（一次性使用）
        redis_client.delete(captcha_key)
        return {"message": "验证通过"}
    else:
        # 验证失败：记录错误次数（防爆破）
        error_key = f"captcha:error:{session_id}"
        errors = redis_client.incr(error_key)
        redis_client.expire(error_key, 1800)  # 30 分钟过期

        if errors >= 5:
            # 错 5 次，锁定 30 分钟
            lock_key = f"captcha:lock:{session_id}"
            redis_client.setex(lock_key, 1800, "1")
            raise HTTPException(status_code=429, detail="错误次数过多，请 30 分钟后再试")

        raise HTTPException(status_code=400, detail="验证码错误")
