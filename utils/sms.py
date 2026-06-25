import json

import os
import random

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
from dotenv import load_dotenv

from utils.redis_client import redis_client

load_dotenv('../setting.env')
# 从环境变量中读取阿里云配置
ACCESS_KEY_ID = os.getenv("ACCESS_KEY_ID")
ACCESS_KEY_SECRET = os.getenv("ACCESS_KEY_SECRET")
SIGN_NAME = os.getenv("SIGN_NAME")
TEMPLATE_CODE = os.getenv("TEMPLATE_CODE")

# Redis Key 命名规范（避免冲突）
KEY_PREFIX = "sms:"
CODE_KEY = f"{KEY_PREFIX}code:"  # 验证码
ERROR_KEY = f"{KEY_PREFIX}error:"  # 错误记录
LOCK_KEY = f"{KEY_PREFIX}lock:"  # 锁定
SEND_KEY = f"{KEY_PREFIX}send:"  # 发送记录
IP_KEY = f"{KEY_PREFIX}ip:"  # IP 限流
RESET_SEND_KEY = f"{KEY_PREFIX}reset_send:"  # 改密验证码发送记录
CAPTCHA_KEY_PREFIX = "captcha:image:"


def generate_code(length=6):
    """生成随机验证码"""
    return ''.join([str(random.randint(0, 9)) for _ in range(length)])


def send_sms_code(phone: str, client_ip: str = None) -> bool:
    """
    发送短信验证码（生产级，带限流）
    """
    # 检查手机号发送频率（60 秒 1 次）
    # 同一手机号限制发送频率每20分钟发一次
    send_key = f"{SEND_KEY}{phone}"
    if redis_client.exists(send_key):
        print(f"⚠️ {phone} 发送太频繁，已拦截")
        return False

    # 检查 IP 发送频率（每小时 3 次）
    if client_ip:
        ip_key = f"{IP_KEY}{client_ip}"
        ip_count = redis_client.get(ip_key)
        if ip_count and int(ip_count) >= 3:
            print(f"🚨 IP {client_ip} 发送超限，已拦截")
            return False

        # 记录 IP 请求（1 小时过期）
        redis_client.incr(ip_key)
        redis_client.expire(ip_key, 3600)

    # 生成验证码，存 Redis（5 分钟自动过期）
    code = generate_code()
    code_key = f"{CODE_KEY}{phone}"
    redis_client.setex(code_key, 300, code)  # 300 秒 = 5 分钟

    # 记录发送时间（20分钟过期）
    redis_client.setex(send_key, 1200, "1")

    # 调用阿里云发送
    try:
        client = AcsClient(ACCESS_KEY_ID, ACCESS_KEY_SECRET, "cn-hangzhou")
        request = CommonRequest()
        request.set_method("POST")
        request.set_domain("dysmsapi.aliyuncs.com")
        request.set_version("2017-05-25")
        request.set_action_name("SendSms")

        request.add_query_param("RegionId", "cn-hangzhou")
        request.add_query_param("PhoneNumbers", phone)
        request.add_query_param("SignName", SIGN_NAME)
        request.add_query_param("TemplateCode", TEMPLATE_CODE)
        request.add_query_param("TemplateParam", json.dumps({"code": code}))

        response = client.do_action_with_exception(request)
        result = json.loads(response)

        if result.get("Code") == "OK":
            print(f"✅ 验证码已发送至 {phone}")
            return True
        else:
            print(f"❌ 发送失败：{result.get('Message')}")
            return False

    except Exception as e:
        print(f"❌ 异常：{str(e)}")
        return False


def verify_code(phone: str, input_code: str) -> bool:
    """
    验证验证码（生产级，防爆破）
    """
    code_key = f"{CODE_KEY}{phone}"
    error_key = f"{ERROR_KEY}{phone}"
    lock_key = f"{LOCK_KEY}{phone}"

    # 先检查是否被锁定
    if redis_client.exists(lock_key):
        ttl = redis_client.ttl(lock_key)
        print(f"🔒 {phone} 被锁定，{ttl}秒后可重试")
        return False

    # 检查验证码是否存在
    stored_code = redis_client.get(code_key)
    if not stored_code:
        return False  # 不存在或已过期

    # 比对验证码
    if stored_code == input_code:
        # ✅ 验证成功：清除验证码 + 清除错误记录
        redis_client.delete(code_key)
        redis_client.delete(error_key)
        return True
    else:
        # ❌ 验证失败：记录错误次数
        errors = redis_client.incr(error_key)

        # 第一次错误时，设置 30 分钟过期
        if errors == 1:
            redis_client.expire(error_key, 1800)

        # 🔒 如果错 5 次，锁定 30 分钟
        if errors >= 5:
            redis_client.setex(lock_key, 1800, "1")  # 锁定 30 分钟
            redis_client.delete(code_key)  # 清除验证码
            print(f"🚨 {phone} 输错 5 次，已锁定 30 分钟")

        return False  # 统一返回 False，不暴露信息


def check_password_reset_limit(phone: str) -> tuple[bool, str]:
    """
    检查 24 小时内是否改过密码
    返回：True=可以改，False=被限制
    """
    key = f"{KEY_PREFIX}pwd_reset:{phone}"
    if redis_client.exists(key):
        ttl = redis_client.ttl(key)
        return False, f"24 小时内只能修改一次，请 {ttl / 3600:.1f} 小时后再试"
    return True, ""


def record_password_reset(phone: str):
    """
    记录密码修改时间（24 小时过期）
    """
    key = f"{KEY_PREFIX}pwd_reset:{phone}"
    redis_client.setex(key, 86400, "1")  # 86400 秒 = 24 小时
