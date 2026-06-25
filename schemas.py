from pydantic import BaseModel, EmailStr,ConfigDict
from typing import Optional, List
from datetime import datetime


# 注册请求（带验证码）
class RegisterWithCode(BaseModel):
    phone: str
    code: str  # 用户输入的验证码
    password: str
    is_admin: bool


# 2. 用户登录时填的表单
class UserLogin(BaseModel):
    phone: str
    password: str


# 3. 登录后发的“通行证”
class Token(BaseModel):
    access_token: str
    token_type: str


# 4. 用户信息展示（不包含密码）
class UserOut(BaseModel):
    id: int
    phone: str
    is_admin: bool
    reg_ip: Optional[str] = None
    last_password_change: Optional[datetime] = None


# --- 下面是新增的套餐相关表单 ---
# 1. 创建套餐时填的表单
class PackageCreate(BaseModel):
    name: str
    description: str
    price: str
    is_active: bool = True


# 2. 更新套餐时填的表单（所有信息都是可选的，改啥填啥）
class PackageUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[str] = None
    is_active: Optional[bool] = None


# 3. 套餐展示给用户看的样子
class PackageOut(BaseModel):
    id: int
    name: str
    description: str
    price: str
    is_active: bool
    # ✅ 加这行：告诉 Pydantic 可以从 ORM 读属性
    model_config = ConfigDict(from_attributes=True)

# --- 下面是新增的订单相关表单 ---
# 1. 用户提交订单时填的表单
class OrderCreate(BaseModel):
    package_id: int  # 选哪个套餐
    customer_name: str  # 姓名
    address: str  # 安装地址
    contact_phone: str  # 联系电话


# 2. 管理员更新订单状态时填的表单
class OrderUpdate(BaseModel):
    status: str  # 比如 "已安装", "已取消"


# 3. 订单展示给用户看的样子
class OrderOut(BaseModel):
    id: int
    customer_name: str
    address: str
    contact_phone: str
    status: str
    package: Optional[PackageOut]=None  # 嵌套显示套餐信息
    created_at: datetime
    owner: Optional[UserOut] = None
    submit_ip: Optional[str] = None
    # 告诉 Pydantic 可以从 ORM 读属性
    model_config = ConfigDict(from_attributes=True)

# 发送注册验证码请求
class SendCodeRequest(BaseModel):
    phone: str


# 发送改密验证码请求
class SendResetCodeRequest(BaseModel):
    phone: str  # 要改密码的手机号


# 执行改密请求
class ResetPasswordRequest(BaseModel):
    phone: str
    code: str  # 短信验证码
    new_password: str  # 新密码


# 分页请求参数（前端传 ?page=1&limit=20）
class PageRequest(BaseModel):
    page: int = 1  # 第几页，默认1
    limit: int = 20  # 每页几条，默认20


# 分页返回包装（把数据+总数+页码一起返回）
class PageResponse(BaseModel):
    data: List[OrderOut]  # ✅ 明确说是 OrderOut 列表
    total: int  # 总共有多少条
    page: int  # 当前页码
    limit: int  # 每页几条
    pages: int  # 总共多少页（自动算）
