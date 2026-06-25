import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv('./setting.env')
# 邮箱配置
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
# RECEIVER_EMAIL = ["2021211786@stu.cqupt.edu.cn", "zhangyun20210801@163.com"]  # 管理员接收通知的邮箱
# 收件人列表
RECEIVER_EMAILS_STR = os.getenv("RECEIVER_EMAILS", "")
RECEIVER_EMAIL = [email.strip() for email in RECEIVER_EMAILS_STR.split(",") if email.strip()]

def send_order_notification(order_info: dict):
    """
    发送新订单通知邮件
    """
    if not RECEIVER_EMAIL:
        print("⚠️ 没有配置收件人邮箱，跳过发送")
        return False
    # 创建邮件内容
    subject = f"新订单通知 - 宽带预约报装系统"

    body = f"""
    <html>
    <body>
        <h2>🎉 有新订单啦！</h2>
        <table border="1" cellpadding="10">
            <tr><td>📋 订单 ID</td><td>{order_info['order_id']}</td></tr>
            <tr><td>👤 客户姓名</td><td>{order_info['customer_name']}</td></tr>
            <tr><td>📞 联系电话</td><td>{order_info['contact_phone']}</td></tr>
            <tr><td>🏠 安装地址</td><td>{order_info['address']}</td></tr>
            <tr><td>📦 套餐名称</td><td>{order_info['package_name']}</td></tr>
            <tr><td>💰 价格</td><td>{order_info['price']}</td></tr>
            <tr><td>⏰ 提交时间</td><td>{order_info['created_at']}</td></tr>
        </table>
        <br>
        <p>请及时联系客户安排安装！</p>
    </body>
    </html>
    """

    # 发送邮件
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)

        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = ", ".join(RECEIVER_EMAIL)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html", "utf-8"))

        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        server.quit()
        print(f"✅ 邮件通知已发送：{order_info['customer_name']}")
        return True
    except smtplib.SMTPAuthenticationError:
        print("❌ 邮箱授权码错误，请检查 SENDER_PASSWORD")
        return False
    except Exception as e:
        print(f"❌ 发送失败：{e}")
        return False
