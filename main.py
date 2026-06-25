from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, engine
from routers import auth, packages, orders, users  # 导入各个模块

# 1. 创建数据库表
Base.metadata.create_all(bind=engine)

# 2. 创建应用实例
app = FastAPI(title="宽带预约系统")
# 允许前端跨域访问（开发环境用 *，生产环境换成具体域名）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产建议改成 ["http://localhost:3000", "https://yourdomain.com"]
    allow_credentials=True,  # 允许带 cookie
    allow_methods=["*"],  # 允许所有方法（GET/POST/PUT/DELETE）
    allow_headers=["*"],  # 允许所有请求头
)
# 3. 把各个模块的接口挂到门上
app.include_router(auth.router, prefix="/auth", tags=["用户认证"])

app.include_router(packages.router, prefix="/packages", tags=["套餐管理"])

app.include_router(orders.router, prefix="/orders", tags=["订单管理"])
app.include_router(users.router, prefix="/users", tags=["用户管理"])


# 4. 欢迎语
@app.get("/")
def read_root():
    return {"message": "欢迎使用宽带预约系统后端！"}
