import redis
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv('./setting.env')

# Redis 配置（从环境变量读取）
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT"))
REDIS_DB = int(os.getenv("REDIS_DB"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")  # 生产环境建议设密码

# 创建连接池
pool = redis.ConnectionPool(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    password=REDIS_PASSWORD,
    decode_responses=True,  # 自动把字节转字符串
    max_connections=50  # 最大连接数
)

# 创建 Redis 客户端
redis_client = redis.Redis(connection_pool=pool)

# 测试连接
def test_connection():
    try:
        redis_client.ping()
        print("✅ Redis 连接成功！")
        return True
    except redis.ConnectionError as e:
        print(f"❌ Redis 连接失败：{e}")
        return False

# 清理所有数据（开发调试用，生产别用！）
def clear_all():
    redis_client.flushdb()
    print("已清空 Redis 数据库")