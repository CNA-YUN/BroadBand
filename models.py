from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime


# 1. 用户账本
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, unique=True, index=True)  # 手机号
    hashed_password = Column(String)  # 加密后的密码
    is_admin = Column(Boolean, default=False)  # 是不是管理员
    last_password_change = Column(DateTime, default=datetime.now)  # 记录上次改密时间
    reg_ip = Column(String, nullable=True)  # 注册 IP
    # 一个用户可以有多个订单
    orders = relationship("Order", back_populates="owner")


# 2. 套餐菜单
class Package(Base):
    __tablename__ = "packages"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)  # 套餐名
    description = Column(String)  # 描述
    price = Column(String)  # 价格
    is_active = Column(Boolean, default=True)  # 是否上架

    # 一个套餐可以被多个订单选择
    orders = relationship("Order", back_populates="package")


# 3. 订单记录
class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String)  # 姓名
    address = Column(String)  # 安装地址
    contact_phone = Column(String)  # 联系电话
    status = Column(String, default="待安装")  # 状态
    created_at = Column(DateTime, default=datetime.now)  # 提交时间
    submit_ip = Column(String, nullable=True)  # 提交订单 IP
    # 关联谁买的
    owner_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="orders")

    # 关联买的啥
    package_id = Column(Integer, ForeignKey("packages.id"))
    package = relationship("Package", back_populates="orders")
