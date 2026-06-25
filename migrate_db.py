from database import engine
from sqlalchemy import text

with engine.connect() as conn:
    # 加注册 IP
    conn.execute(text("ALTER TABLE users ADD COLUMN reg_ip TEXT"))
    # 加订单 IP
    conn.execute(text("ALTER TABLE orders ADD COLUMN submit_ip TEXT"))
    conn.commit()
print("字段添加成功，可删除此脚本")