# 1. 导入模块修改：删除 mysql.connector，改用 MySQLdb
import MySQLdb
import MySQLdb.cursors  # 用于字典类型 Cursor
import os
import json
from datetime import datetime, timedelta
from functools import lru_cache

class Config:
    # 数据库配置：保持不变（后续连接时映射参数）
    DB_CONFIG = {
        'host': os.environ.get('DB_HOST', 'localhost'),
        'user': os.environ.get('DB_USER', 'root'),
        'password': os.environ.get('DB_PASSWORD', '123456'),
        'database': os.environ.get('DB_NAME', 'adaptive_study_agent')
    }

class DataManager:
    """数据管理器（单例模式，确保全局仅一个实例，避免多连接）"""
    _instance = None  # 单例实例存储

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DataManager, cls).__new__(cls)
            cls._instance.config = Config.DB_CONFIG
            cls._instance.connection = None
            cls._instance.cursor = None
            cls._instance._connect()
            cls._instance._initialize_database()
        return cls._instance

    # 事务相关方法：保持不变（MySQLdb 兼容 autocommit 逻辑）
    def start_transaction(self):
        try:
            if not self.connection or not self.connection.open:  # MySQLdb 用 open 判断连接是否有效
                self._connect()
            self.connection.autocommit(False)  # 关闭自动提交，开启事务
        except MySQLdb.Error as e:  # 异常类型改为 MySQLdb.Error
            print(f"开启事务错误: {e}")
            return False
        return True
    
    def commit_transaction(self):
        try:
            if self.connection and self.connection.open:
                self.connection.commit()
                self.connection.autocommit = True
        except MySQLdb.Error as e:  # 异常类型改为 MySQLdb.Error
            print(f"提交事务错误: {e}")
            return False
        return True
    
    def rollback_transaction(self):
        try:
            if self.connection and self.connection.open:
                self.connection.rollback()
                self.connection.autocommit = True
        except MySQLdb.Error as e:  # 异常类型改为 MySQLdb.Error
            print(f"回滚事务错误: {e}")
            return False
        return True
        
    def _connect(self):
        """建立数据库连接：核心修改处（替换为 MySQLdb 语法）"""
        try:
            # 2. 连接参数映射：mysql.connector → MySQLdb
            # 关键映射：password → passwd；dictionary=True → cursorclass=DictCursor
            self.connection = MySQLdb.connect(
                host=self.config['host'],
                user=self.config['user'],
                passwd=self.config['password'],  # MySQLdb 用 passwd 而非 password
                db=self.config['database'],     # MySQLdb 用 db 而非 database
                port=3306,                      # 显式指定端口（默认3306，避免隐式错误）
                connect_timeout=10,             # 连接超时（对应原 connection_timeout）
                cursorclass=MySQLdb.cursors.DictCursor  # 确保返回字典类型结果（原 dictionary=True）
                # MySQLdb 无需 ssl_disabled，默认不强制 SSL（解决原认证安全连接问题）
            )
                   
            # 3. 创建 Cursor（直接用连接的 cursor 方法，已指定字典类型）
            self.cursor = self.connection.cursor()
            # 获取线程ID：MySQLdb 用 thread_id() 方法（原 connection_id 改为 thread_id()）
            print(f"数据库连接成功（线程ID: {self.connection.thread_id()}）")
        except MySQLdb.Error as e:  # 异常类型改为 MySQLdb.Error
            error_msg = str(e)
            print(f"数据库连接错误: {error_msg}")
            # 保留「不存在数据库则创建」逻辑：临时连接也改用 MySQLdb
            if "Unknown database" in error_msg:
                # 临时连接：不指定 db（避免数据库不存在报错）
                temp_conn = MySQLdb.connect(
                    host=self.config['host'],
                    user=self.config['user'],
                    passwd=self.config['password'],
                    connect_timeout=10
                )
                temp_cursor = temp_conn.cursor()
                temp_cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.config['database']}")
                temp_cursor.close()
                temp_conn.close()
                print(f"数据库 {self.config['database']} 创建成功，重新连接...")
                self._connect()  # 重新连接
            # 清空无效连接对象
            self.connection = None
            self.cursor = None
    
    def _initialize_database(self):
        """初始化数据库表结构：仅修改连接有效性判断和异常类型"""
        if not self.cursor or not self.connection.open:  # MySQLdb 用 open 判断连接
             self._connect()
             if not self.cursor:
                print("数据库连接失败，无法初始化表结构")
                return
        
        # 以下「表创建逻辑完全不变」（SQL 语法通用）
        try:
            # 用户表
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) UNIQUE,
                    password VARCHAR(255),
                    email VARCHAR(100) UNIQUE,
                    full_name VARCHAR(100),
                    interests TEXT,
                    learning_style TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP NULL,
                    is_active BOOLEAN DEFAULT TRUE
                )
            ''')
            
            # 学习路径表
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS learning_paths (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT,
                    subject VARCHAR(100),
                    progress FLOAT DEFAULT 0.0,
                    difficulty_level VARCHAR(10),
                    content JSON,
                    target_completion_date DATE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    INDEX idx_user_id_subject (user_id, subject),
                    INDEX idx_last_updated (last_updated)
                )
            ''')
            
            # 学习活动表
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS learning_activities (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT,
                    path_id INT,
                    topic_name VARCHAR(100),
                    progress FLOAT DEFAULT 0.0,
                    total_score FLOAT DEFAULT 0.0,
                    total_minutes DECIMAL(10,2) DEFAULT 0.00,
                    content JSON,
                    activity_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (path_id) REFERENCES learning_paths(id) ON DELETE CASCADE,
                    INDEX idx_user_id_activity_date (user_id, activity_date)
                )
            ''')
            
            # 评估表
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS assessments (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT,
                    subject VARCHAR(100),
                    topic_name VARCHAR(100),
                    content JSON,  
                    taken_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,  
                    INDEX idx_user_id_subject_topic_name (user_id, subject, topic_name) 
                )
            ''')
            
            # 路径评估表
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS path_assessments (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    learning_path_id INT,
                    user_id INT,
                    question TEXT,
                    user_answer TEXT,
                    score FLOAT,
                    feedback TEXT,
                    difficulty_level VARCHAR(10),
                    question_type VARCHAR(10),
                    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (learning_path_id) REFERENCES learning_paths(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    INDEX idx_learning_path_id (learning_path_id)
                )
            ''')
            
            # 证书表
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS certifications (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT,
                    learning_path_id INT,
                    completion_date DATE,
                    certificate_number VARCHAR(50) UNIQUE,
                    recipient_name VARCHAR(100),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (learning_path_id) REFERENCES learning_paths(id) ON DELETE CASCADE,
                    INDEX idx_user_id_cert_date (user_id, completion_date)
                )
            ''')
            
            # 学习习惯表
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS study_streaks (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT UNIQUE,
                    current_streak_days INT DEFAULT 0,
                    longest_streak_days INT DEFAULT 0,
                    last_study_date DATE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
            
            # 学习计划表
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS study_schedules (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT,
                    path_id INT,
                    schedule_json JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (path_id) REFERENCES learning_paths(id) ON DELETE CASCADE,
                    INDEX idx_user_id_path_id (user_id, path_id)
                )
            ''')
            
            self.connection.commit()
            print("表结构初始化完成")
        except MySQLdb.Error as e:  # 异常类型改为 MySQLdb.Error
            print(f"初始化表结构错误: {e}")
            self.connection.rollback()
    
    def execute_query(self, query, params=None, commit=True):
        """执行查询：修改连接有效性判断、异常类型、Cursor 语法"""
        max_reconnect = 2
        reconnect_count = 0

        while reconnect_count < max_reconnect:
            try:
                # 连接有效性判断：MySQLdb 用 open
                if not self.connection or not self.connection.open:
                    print(f"连接失效，尝试重新连接（第 {reconnect_count+1} 次）")
                    self._connect()
                    if not self.connection or not self.connection.open:
                        reconnect_count += 1
                        continue

                # 执行查询：MySQLdb 的 Cursor 兼容 execute 语法，无需改参数
                with self.connection.cursor(MySQLdb.cursors.DictCursor) as cursor:  # 显式指定字典 Cursor
                    cursor.execute(query, params or ())
                
                    if query.strip().upper().startswith('SELECT'):
                        return cursor.fetchall()
                    elif query.strip().upper().startswith('INSERT'):
                        result = cursor.lastrowid
                        if commit and self.connection.autocommit:
                            self.connection.commit()
                        return result
                    else:
                        if commit and self.connection.autocommit:
                            self.connection.commit()
                        return cursor.rowcount

            except MySQLdb.Error as e:  # 异常类型改为 MySQLdb.Error
                error_msg = str(e)
                print(f"查询执行错误: {error_msg}")
                # 连接错误判断：保留原有关键词
                if any(keyword in error_msg for keyword in ["Lost connection", "Connection refused", "not connected"]):
                    reconnect_count += 1
                    self.connection = None
                    self.cursor = None
                    continue
                # 事务回滚
                if self.connection and not self.connection.autocommit:
                    self.rollback_transaction()
                return False
    
        print(f"已尝试 {max_reconnect} 次重新连接，均失败")
        return False

    
    def execute_batch(self, query, data, commit=True):
        """执行批量插入：修改连接判断和异常类型"""
        try:
            if not self.connection.open:
                self._connect()
                
            with self.connection.cursor(MySQLdb.cursors.DictCursor) as cursor:
                cursor.executemany(query, data)
                
                if commit:
                    self.connection.commit()
                return cursor.rowcount
                
        except MySQLdb.Error as e:  # 异常类型改为 MySQLdb.Error
            print(f"批量查询执行错误: {e}")
            self.connection.rollback()
            return False
    
    # 以下「业务方法完全不变」（SQL 逻辑通用）
    def get_user_by_id(self, user_id):
        query = "SELECT * FROM users WHERE id = %s"
        result = self.execute_query(query, (user_id,))
        return result[0] if result else None
    
    @lru_cache(maxsize=32)
    def get_learning_paths(self, user_id):
        query = "SELECT * FROM learning_paths WHERE user_id = %s ORDER BY last_updated DESC"
        return self.execute_query(query, (user_id,))
    
    def update_study_streak(self, user_id):
        today = datetime.now().date()
        
        query = "SELECT * FROM study_streaks WHERE user_id = %s"
        streak = self.execute_query(query, (user_id,))
        
        if not streak:
            query = "INSERT INTO study_streaks (user_id, current_streak_days, longest_streak_days, last_study_date) VALUES (%s, %s, %s, %s)"
            self.execute_query(query, (user_id, 1, 1, today))
            return 1
        
        streak = streak[0]
        last_study_date = streak['last_study_date']
        
        if last_study_date == today:
            return streak['current_streak_days']
        
        if (today - last_study_date).days == 1:
            new_streak = streak['current_streak_days'] + 1
            longest_streak = max(new_streak, streak['longest_streak_days'])
            
            query = "UPDATE study_streaks SET current_streak_days = %s, longest_streak_days = %s, last_study_date = %s WHERE user_id = %s"
            self.execute_query(query, (new_streak, longest_streak, today, user_id))
            
            return new_streak
        else:
            query = "UPDATE study_streaks SET current_streak_days = %s, last_study_date = %s WHERE user_id = %s"
            self.execute_query(query, (1, today, user_id))
            return 1