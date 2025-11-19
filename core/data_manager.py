import MySQLdb
import MySQLdb.cursors
import os
import json
import time
from datetime import datetime, timedelta
from functools import lru_cache
from dbutils.pooled_db import PooledDB

class Config:
    # 连接池配置
    POOL_CONFIG = {
        'host': os.environ.get('MYSQLHOST', 'mysql.railway.internal'),
        'user': os.environ.get('MYSQLUSER', 'root'),
        'password': os.environ.get('MYSQLPASSWORD', 'TbmMjnfScHMmjVuLyGGEWbENvudftkPt'),
        'database': os.environ.get('MYSQLDATABASE', 'railway'),
        'port': int(os.environ.get('MYSQLPORT', 3306)),
        'maxconnections': 5,
        'mincached': 2,
        'cursorclass': MySQLdb.cursors.DictCursor
    }

class DataManager:
    """Data Manager - 单例模式 + 延迟初始化连接池"""
    _instance = None
    _pool = None  # 连接池实例，延迟初始化
    _table_initialized = False  # 表初始化标记

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DataManager, cls).__new__(cls)
            cls._instance.config = Config.POOL_CONFIG
            cls._instance.connection = None
            cls._instance.cursor = None
            # 先初始化连接池
            cls._instance._initialize_pool()
            # 延迟确保连接池就绪
            time.sleep(1)
            # 初始化表结构
            cls._instance._initialize_database()
        return cls._instance

    def _initialize_pool(self):
        """延迟初始化连接池，避免服务启动时连接失败"""
        try:
            self._pool = PooledDB(MySQLdb, **self.config)
            print("数据库连接池初始化成功")
        except MySQLdb.OperationalError as e:
            print(f"连接池初始化失败: {e}")
            # 不直接抛出异常，允许后续重试
            self._pool = None

    # Transaction-related methods
    def start_transaction(self):
        try:
            if not self.connection or not self.connection.open:
                self._connect()
            # 使用方法调用而非属性赋值，兼容连接池连接对象
            self.connection.set_autocommit(False)
        except MySQLdb.Error as e:
            print(f"Error in starting a transaction: {e}")
            return False
        return True
    
    def commit_transaction(self):
        try:
            if self.connection and self.connection.open:
                self.connection.commit()
                # 使用方法调用而非属性赋值
                self.connection.set_autocommit(True)
        except MySQLdb.Error as e:
            print(f"Transaction submission error: {e}")
            return False
        return True
    
    def rollback_transaction(self):
        try:
            if self.connection and self.connection.open:
                self.connection.rollback()
                # 使用方法调用而非属性赋值
                self.connection.set_autocommit(True)
        except MySQLdb.Error as e:
            print(f"Rollback transaction error: {e}")
            return False
        return True
        
    def _connect(self):
        """从连接池获取连接（优先使用连接池）"""
        try:
            # 如果连接池已初始化，优先从连接池获取
            if self._pool:
                self.connection = self._pool.connection()
                print(f"从连接池获取连接成功（ThreadID: {self.connection.thread_id()}）")
            else:
                # 备用方案：直接创建连接
                self.connection = MySQLdb.connect(
                    host=self.config['host'],
                    user=self.config['user'],
                    passwd=self.config['password'],
                    db=self.config['database'],
                    port=self.config['port'],
                    connect_timeout=10,
                    cursorclass=MySQLdb.cursors.DictCursor
                )
                print(f"直接创建连接成功（ThreadID: {self.connection.thread_id()}）")
            
            self.cursor = self.connection.cursor()
            
        except MySQLdb.Error as e:
            error_msg = str(e)
            print(f"数据库连接错误: {error_msg}")
            
            # 处理数据库不存在的情况
            if "Unknown database" in error_msg:
                temp_conn = MySQLdb.connect(
                    host=self.config['host'],
                    user=self.config['user'],
                    passwd=self.config['password'],
                    port=self.config['port'],
                    connect_timeout=10
                )
                temp_cursor = temp_conn.cursor()
                temp_cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.config['database']}")
                temp_cursor.close()
                temp_conn.close()
                print(f"数据库 {self.config['database']} 创建成功，重新连接...")
                self._connect()
            
            self.connection = None
            self.cursor = None
    
    def _initialize_database(self):
        """初始化数据库表结构（独立获取连接，兼容连接池）"""
        if self._table_initialized:
            return
            
        # 强制从连接池或创建新连接
        current_conn = None
        try:
            if self._pool:
                current_conn = self._pool.connection()
                print("从连接池获取连接进行表初始化")
            else:
                # 备用方案：直接创建连接
                current_conn = MySQLdb.connect(
                    host=self.config['host'],
                    user=self.config['user'],
                    passwd=self.config['password'],
                    db=self.config['database'],
                    port=self.config['port'],
                    connect_timeout=10,
                    cursorclass=MySQLdb.cursors.DictCursor
                )
                print("直接创建连接进行表初始化")

            with current_conn.cursor() as cursor:
                # User Table
                cursor.execute('''
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
                        is_active BOOLEAN DEFAULT TRUE,
                        version INT DEFAULT 1
                    )
                ''')
                
                # Learning Path table
                cursor.execute('''
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
                        version INT DEFAULT 1,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                        INDEX idx_user_id_subject (user_id, subject),
                        INDEX idx_last_updated (last_updated)
                    )
                ''')
                
                # Learning Activity Schedule
                cursor.execute('''
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
                        version INT DEFAULT 1,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                        FOREIGN KEY (path_id) REFERENCES learning_paths(id) ON DELETE CASCADE,
                        INDEX idx_user_id_activity_date (user_id, activity_date)
                    )
                ''')
                
                # Evaluation Form
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS assessments (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id INT,
                        subject VARCHAR(100),
                        topic_name VARCHAR(100),
                        content JSON,  
                        taken_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  
                        version INT DEFAULT 1,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,  
                        INDEX idx_user_id_subject_topic_name (user_id, subject, topic_name) 
                    )
                ''')
                
                # Path Evaluation Form
                cursor.execute('''
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
                        version INT DEFAULT 1,
                        FOREIGN KEY (learning_path_id) REFERENCES learning_paths(id) ON DELETE CASCADE,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                        INDEX idx_learning_path_id (learning_path_id)
                    )
                ''')
                
                # Certificate Form
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS certifications (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id INT,
                        learning_path_id INT,
                        completion_date DATE,
                        certificate_number VARCHAR(50) UNIQUE,
                        recipient_name VARCHAR(100),
                        version INT DEFAULT 1,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                        FOREIGN KEY (learning_path_id) REFERENCES learning_paths(id) ON DELETE CASCADE,
                        INDEX idx_user_id_cert_date (user_id, completion_date)
                    )
                ''')
                
                # Learning Habits Chart
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS study_streaks (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id INT UNIQUE,
                        current_streak_days INT DEFAULT 0,
                        longest_streak_days INT DEFAULT 0,
                        last_study_date DATE,
                        version INT DEFAULT 1
                    )
                ''')
                
                # Study Schedule
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS study_schedules (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id INT,
                        path_id INT,
                        schedule_json JSON,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        version INT DEFAULT 1,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                        FOREIGN KEY (path_id) REFERENCES learning_paths(id) ON DELETE CASCADE,
                        INDEX idx_user_id_path_id (user_id, path_id)
                    )
                ''')

                # 强制补充version字段（兼容旧表）
                alter_queries = [
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS version INT DEFAULT 1",
                    "ALTER TABLE learning_paths ADD COLUMN IF NOT EXISTS version INT DEFAULT 1",
                    "ALTER TABLE learning_activities ADD COLUMN IF NOT EXISTS version INT DEFAULT 1",
                    "ALTER TABLE assessments ADD COLUMN IF NOT EXISTS version INT DEFAULT 1",
                    "ALTER TABLE path_assessments ADD COLUMN IF NOT EXISTS version INT DEFAULT 1",
                    "ALTER TABLE certifications ADD COLUMN IF NOT EXISTS version INT DEFAULT 1",
                    "ALTER TABLE study_streaks ADD COLUMN IF NOT EXISTS version INT DEFAULT 1",
                    "ALTER TABLE study_schedules ADD COLUMN IF NOT EXISTS version INT DEFAULT 1",
                ]
                for alter_query in alter_queries:
                    cursor.execute(alter_query)

            current_conn.commit()
            self._table_initialized = True
            print("表结构初始化（含version字段）完成！")

        except MySQLdb.Error as e:
            print(f"表结构初始化失败: {e}")
            if current_conn:
                current_conn.rollback()
        finally:
            if current_conn:
                current_conn.close()
    
    def execute_query(self, query, params=None, commit=True):
        """Execute the query with reconnect logic + 表初始化检查"""
        # 确保表已初始化
        if not self._table_initialized:
            self._initialize_database()

        max_reconnect = 2
        reconnect_count = 0

        while reconnect_count < max_reconnect:
            try:
                current_conn = None
                # 优先使用连接池获取连接
                if self._pool:
                    current_conn = self._pool.connection()
                elif not self.connection or not self.connection.open:
                    print(f"Connection failed. Trying to reconnect（Attempt {reconnect_count+1}）")
                    self._connect()
                    current_conn = self.connection
                    if not current_conn or not current_conn.open:
                        reconnect_count += 1
                        continue
                else:
                    current_conn = self.connection

                with current_conn.cursor(MySQLdb.cursors.DictCursor) as cursor:
                    cursor.execute(query, params or ())
                
                    if query.strip().upper().startswith('SELECT'):
                        result = cursor.fetchall()
                    elif query.strip().upper().startswith('INSERT'):
                        result = cursor.lastrowid
                        if commit:
                            current_conn.commit()
                    else:
                        result = cursor.rowcount
                        if commit:
                            current_conn.commit()
                    
                    return result

            except MySQLdb.Error as e:
                error_msg = str(e)
                print(f"Query execution error: {error_msg}")
                
                if any(keyword in error_msg for keyword in ["Lost connection", "Connection refused", "not connected"]):
                    reconnect_count += 1
                    self.connection = None
                    self.cursor = None
                    continue
                
                # 使用getattr安全检查autocommit状态
                if current_conn and not getattr(current_conn, 'autocommit', True):
                    try:
                        current_conn.rollback()
                    except:
                        pass
                return False
    
        print(f"Failed after {max_reconnect} reconnection attempts")
        return False

    
    def execute_batch(self, query, data, commit=True):
        """Perform batch insertion"""
        # 确保表已初始化
        if not self._table_initialized:
            self._initialize_database()
            
        try:
            current_conn = None
            if self._pool:
                current_conn = self._pool.connection()
            elif not self.connection or not self.connection.open:
                self._connect()
                current_conn = self.connection
                
            if not current_conn:
                print("No valid database connection available")
                return False
                
            with current_conn.cursor(MySQLdb.cursors.DictCursor) as cursor:
                cursor.executemany(query, data)
                
                if commit:
                    current_conn.commit()
                return cursor.rowcount
                
        except MySQLdb.Error as e:
            print(f"Batch query execution error: {e}")
            if current_conn:
                try:
                    current_conn.rollback()
                except:
                    pass
            return False
    
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