from utils.redis_client import test_connection, redis_client

if __name__ == "__main__":
    # 测试连接
    if test_connection():
        # 测试读写
        print()
        redis_client.setex("test:key", 60, "hello redis")
        value = redis_client.get("test:key")
        print(f"✅ 读写测试：{value}")

        # 清理测试数据
        redis_client.delete("test:key")
        print("✅ 所有测试通过！")
    else:
        print("❌ 请先启动 Redis 服务器")