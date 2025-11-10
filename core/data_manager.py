import MySQLdb
import MySQLdb.cursors  # Used for the dictionary type Cursor
import os
import json
from datetime import datetime, timedelta
from functools import lru_cache

class Config:
    # 适配 Railway MySQL 的数据库配置
    DB_CONFIG = {
        'host': os.environ.get('RAILWAY_PRIVATE_DOMAIN'),
        'user': os.environ.get('MYSQLUSER', 'root'),
        'password': os.environ.get('MYSQL_ROOT_PASSWORD'),
        'database': os.environ.get('MYSQL_DATABASE', 'railway'),  # 从截图中可知数据库名为 railway
        'port': 3306
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
            if not self.connection or not self.connection.open:  # MySQLdb uses open to determine whether a connection is valid
                self._connect()
            self.connection.autocommit(False)  # Turn off auto-commit and enable transactions
        except MySQLdb.Error as e:  # Change the exception type to MySQLdb.Error
            print(f"Error in starting a transaction: {e}")
            return False
        return True
    
    def commit_transaction(self):
        try:
            if self.connection and self.connection.open:
                self.connection.commit()
                self.connection.autocommit = True
        except MySQLdb.Error as e:  # Change the exception type to MySQLdb.Error
            print(f"Transaction submission error: {e}")
            return False
        return True
    
    def rollback_transaction(self):
        try:
            if self.connection and self.connection.open:
                self.connection.rollback()
                self.connection.autocommit = True
        except MySQLdb.Error as e:  # Change the exception type to MySQLdb.Error
            print(f"Rollback transaction error: {e}")
            return False
        return True
        
    def _connect(self):
        """Establish a database connection"""
        try:
            # Connection parameter mapping: mysql.connector → MySQLdb
            # Key mapping: password → passwd; dictionary=True → cursorclass=DictCursor
            self.connection = MySQLdb.connect(
                host=self.config['host'],
                user=self.config['user'],
                passwd=self.config['password'],  
                db=self.config['database'],     
                port=3306,                      # Explicitly specify the port (default 3306 to avoid implicit errors)
                connect_timeout=10,             # Connection timeout (corresponding to the original connection_timeout)
                cursorclass=MySQLdb.cursors.DictCursor  # Make sure to return a dictionary type result (original dictionary=True)
                # MySQLdb does not require ssl_disabled and does not enforce SSL by default (to solve the problem of the original authenticated secure connection)
            )
                   
            # Create a Cursor (directly using the linked cursor method, with the dictionary type specified)
            self.cursor = self.connection.cursor()
            # To obtain the thread ID: MySQLdb uses the thread_id() method
            print(f"The database connection was successful.（ThreadID: {self.connection.thread_id()}）")
        except MySQLdb.Error as e:  # Change the exception type to MySQLdb.Error
            error_msg = str(e)
            print(f"Database connection error: {error_msg}")
            if "Unknown database" in error_msg:
                # Temporary connection
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
                print(f"Database {self.config['database']} Creation successful. Reconnect...")
                self._connect()  # Reconnect
            # Clear the invalid connection objects
            self.connection = None
            self.cursor = None
    
    def _initialize_database(self):
        """Initialize the database table structure"""
        if not self.cursor or not self.connection.open:  # MySQLdb uses "open" to determine connections
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
        except MySQLdb.Error as e:  # Change the exception type to MySQLdb.Error
            print(f"The structure of the initialization table is incorrect: {e}")
            self.connection.rollback()
    
    def execute_query(self, query, params=None, commit=True):
        """Execute the query: Modify the connection validity judgment, exception type, and Cursor syntax"""
        max_reconnect = 2
        reconnect_count = 0

        while reconnect_count < max_reconnect:
            try:
                # Connection validity determination: MySQLdb uses open
                if not self.connection or not self.connection.open:
                    print(f"The connection failed. Try reconnecting（For {reconnect_count+1} times）")
                    self._connect()
                    if not self.connection or not self.connection.open:
                        reconnect_count += 1
                        continue

                # To execute a query: MySQLdb's Cursor is compatible with the EXECUTE syntax, and there is no need to modify parameters
                with self.connection.cursor(MySQLdb.cursors.DictCursor) as cursor:  # Explicitly specify the dictionary Cursor
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

            except MySQLdb.Error as e:  # Change the exception type to MySQLdb.Error
                error_msg = str(e)
                print(f"Query execution error: {error_msg}")
                # Connection error judgment: Retain the original keywords
                if any(keyword in error_msg for keyword in ["Lost connection", "Connection refused", "not connected"]):
                    reconnect_count += 1
                    self.connection = None
                    self.cursor = None
                    continue
                # Transaction rollback
                if self.connection and not self.connection.autocommit:
                    self.rollback_transaction()
                return False
    
        print(f"Has been tried{max_reconnect} Each reconnection failed")
        return False

    
    def execute_batch(self, query, data, commit=True):
        """Perform batch insertion: Modify the connection judgment and exception type"""
        try:
            if not self.connection.open:
                self._connect()
                
            with self.connection.cursor(MySQLdb.cursors.DictCursor) as cursor:
                cursor.executemany(query, data)
                
                if commit:
                    self.connection.commit()
                return cursor.rowcount
                
        except MySQLdb.Error as e:  # Change the exception type to MySQLdb.Error
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