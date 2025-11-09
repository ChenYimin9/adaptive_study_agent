# Import various libraries
import mysql.connector
from mysql.connector import Error
import os
import json
from datetime import datetime, timedelta
from functools import lru_cache

class Config:
    # Database configuration
    DB_CONFIG = {
        'host': os.environ.get('DB_HOST', 'localhost'),
        'user': os.environ.get('DB_USER', 'root'),
        'password': os.environ.get('DB_PASSWORD', '123456'),
        'database': os.environ.get('DB_NAME', 'adaptive_study_agent')
    }

class DataManager:
    """Data Manager"""
    _instance = None  # Singleton instance storage

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DataManager, cls).__new__(cls)
            cls._instance.config = Config.DB_CONFIG
            cls._instance.connection = None
            cls._instance.cursor = None
            cls._instance._connect()
            cls._instance._initialize_database()
        return cls._instance

    # Transaction-related methods
    def start_transaction(self):
        try:
            # mysql.connector用is_connected()判断连接有效性
            if not self.connection or not self.connection.is_connected():
                self._connect()
            self.connection.autocommit = False  # 关闭自动提交，开启事务
        except mysql.connector.Error as e:  # 异常类型适配
            print(f"Error in starting a transaction: {e}")
            return False
        return True
    
    def commit_transaction(self):
        try:
            if self.connection and self.connection.is_connected():
                self.connection.commit()
                self.connection.autocommit = True
        except mysql.connector.Error as e:  # 异常类型适配
            print(f"Transaction submission error: {e}")
            return False
        return True
    
    def rollback_transaction(self):
        try:
            if self.connection and self.connection.is_connected():
                self.connection.rollback()
                self.connection.autocommit = True
        except mysql.connector.Error as e:  # 异常类型适配
            print(f"Rollback transaction error: {e}")
            return False
        return True
        
    def _connect(self):
        """Establish a database connection (适配mysql.connector)"""
        try:
            # mysql.connector连接参数：password替代passwd，database替代db
            self.connection = mysql.connector.connect(
                host=self.config['host'],
                user=self.config['user'],
                password=self.config['password'],  # 适配参数名
                database=self.config['database'],  # 适配参数名
                port=3306,
                connect_timeout=10,
                # 无需额外配置ssl（默认不强制）
            )
           
            # 创建字典类型游标（mysql.connector用dictionary=True参数）
            self.cursor = self.connection.cursor(dictionary=True)
            # mysql.connector用thread_id属性获取线程ID
            print(f"The database connection was successful.（ThreadID: {self.connection.thread_id}）")
        except mysql.connector.Error as e:  # 异常类型适配
            error_msg = str(e)
            print(f"Database connection error: {error_msg}")
            if "Unknown database" in error_msg:
                # 临时连接创建数据库
                temp_conn = mysql.connector.connect(
                    host=self.config['host'],
                    user=self.config['user'],
                    password=self.config['password'],
                    connect_timeout=10
                )
                temp_cursor = temp_conn.cursor()
                temp_cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.config['database']}")
                temp_cursor.close()
                temp_conn.close()
                print(f"Database {self.config['database']} Creation successful. Reconnect...")
                self._connect()  # 重新连接
            # 清除无效连接对象
            self.connection = None
            self.cursor = None
    
    def _initialize_database(self):
        """Initialize the database table structure"""
        # mysql.connector用is_connected()判断连接有效性
        if not self.cursor or not self.connection.is_connected():
             self._connect()
             if not self.cursor:
                print("The database connection failed and the table structure could not be initialized")
                return
        
        try:
            # User Table
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
            
            # Learning Path table
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
            
            # Learning Activity Schedule
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
            
            # Evaluation Form
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
            
            # Path Evaluation Form
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
            
            # Certificate Form
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
            
            # Learning Habits Chart
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
            
            # Study Schedule
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
            print("The table structure initialization has been completed")
        except mysql.connector.Error as e:  # 异常类型适配
            print(f"The structure of the initialization table is incorrect: {e}")
            self.connection.rollback()
    
    def execute_query(self, query, params=None, commit=True):
        """Execute the query (适配mysql.connector)"""
        max_reconnect = 2
        reconnect_count = 0

        while reconnect_count < max_reconnect:
            try:
                # 连接有效性判断：mysql.connector用is_connected()
                if not self.connection or not self.connection.is_connected():
                    print(f"The connection failed. Try reconnecting（For {reconnect_count+1} times）")
                    self._connect()
                    if not self.connection or not self.connection.is_connected():
                        reconnect_count += 1
                        continue

                # 创建字典类型游标（mysql.connector用dictionary=True）
                with self.connection.cursor(dictionary=True) as cursor:
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

            except mysql.connector.Error as e:  # 异常类型适配
                error_msg = str(e)
                print(f"Query execution error: {error_msg}")
                # 连接错误判断
                if any(keyword in error_msg for keyword in ["Lost connection", "Connection refused", "not connected"]):
                    reconnect_count += 1
                    self.connection = None
                    self.cursor = None
                    continue
                # 事务回滚
                if self.connection and not self.connection.autocommit:
                    self.rollback_transaction()
                return False
    
        print(f"Has been tried {max_reconnect} Each reconnection failed")
        return False

    
    def execute_batch(self, query, data, commit=True):
        """Perform batch insertion (适配mysql.connector)"""
        try:
            # 连接有效性判断
            if not self.connection.is_connected():
                self._connect()
                
            with self.connection.cursor(dictionary=True) as cursor:
                cursor.executemany(query, data)
                
                if commit:
                    self.connection.commit()
                return cursor.rowcount
                
        except mysql.connector.Error as e:  # 异常类型适配
            print(f"Batch query execution error: {e}")
            self.connection.rollback()
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