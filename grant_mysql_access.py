import pymysql
import os

# 从环境变量获取数据库连接信息
MYSQL_HOST = os.getenv('MYSQLHOST', 'mysql.railway.internal')
MYSQL_PORT = int(os.getenv('MYSQLPORT', '3306'))
MYSQL_USER = os.getenv('MYSQLUSER', 'root')
MYSQL_PASSWORD = os.getenv('MYSQLPASSWORD', '')
MYSQL_DATABASE = os.getenv('MYSQLDATABASE', 'railway')

# IPv6 地址（从错误日志中获取）
IPV6_ADDRESS = 'fd12:809f:afe1:1:9000:23:2114:2923'

try:
    # 连接到 MySQL（使用内部网络地址）
    connection = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset='utf8mb4'
    )

    print(f"✓ 成功连接到 MySQL: {MYSQL_HOST}:{MYSQL_PORT}")

    with connection.cursor() as cursor:
        # 授权 IPv6 地址
        grant_sql = f"""
        GRANT ALL PRIVILEGES ON {MYSQL_DATABASE}.* 
        TO '{MYSQL_USER}'@'{IPV6_ADDRESS}' 
        IDENTIFIED BY '{MYSQL_PASSWORD}'
        """
        cursor.execute(grant_sql)
        print(f"✓ 已授权 IPv6 地址: {IPV6_ADDRESS}")

        # 授权所有主机（更稳妥）
        grant_all_sql = f"""
        GRANT ALL PRIVILEGES ON *.* 
        TO '{MYSQL_USER}'@'%' 
        IDENTIFIED BY '{MYSQL_PASSWORD}' 
        WITH GRANT OPTION
        """
        cursor.execute(grant_all_sql)
        print("✓ 已授权所有主机 (%)")

        # 刷新权限
        cursor.execute("FLUSH PRIVILEGES")
        print("✓ 已刷新权限")

        # 验证
        cursor.execute("SELECT User, Host FROM mysql.user WHERE User = %s", (MYSQL_USER,))
        results = cursor.fetchall()
        print("\n当前用户权限:")
        for user, host in results:
            print(f"  - {user}@{host}")

    connection.close()
    print("\n✓ 授权完成！")

except Exception as e:
    print(f"✗ 错误: {e}")
    exit(1)