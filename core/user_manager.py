import hashlib
from datetime import datetime
from .data_manager import DataManager

class UserManager:
    def __init__(self):
        self.data_manager = DataManager()
    
    @staticmethod
    def _hash_password(password):
        """密码加密存储"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def register_user(self, username, password, email, full_name, interests, learning_style):
        """注册新用户"""
        try:
            hashed_pw = self._hash_password(password)
            user_id = self.data_manager.execute_query('''
                INSERT INTO users (username, password, email, full_name, interests, learning_style)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (username, hashed_pw, email, full_name, interests, learning_style))
            
            # 初始化学习习惯记录
            if user_id:
                self.data_manager.execute_query('''
                    INSERT INTO study_streaks (user_id) VALUES (%s)
                ''', (user_id,))
            
            return user_id
        except Exception as e:
            print(f"用户注册错误: {e}")
            return None
    
    def authenticate_user(self, username, password):
        """验证用户身份"""
        hashed_pw = self._hash_password(password)
        users = self.data_manager.execute_query('''
            SELECT * FROM users WHERE username = %s AND password = %s
        ''', (username, hashed_pw))
        if users:
            user = users[0]
            self.data_manager.execute_query('''
                UPDATE users SET last_login = NOW() WHERE id = %s
            ''', (user['id'],))
            return user
        return None
    
    def get_user_profile(self, user_id):
        """获取用户资料"""
        users = self.data_manager.execute_query('''
            SELECT id, username, email, full_name, interests, learning_style, 
                   created_at, last_login 
            FROM users WHERE id = %s
        ''', (user_id,))
        return users[0] if users else None
    
    def update_user_profile(self, user_id, **kwargs):
        """更新用户资料"""
        fields = []
        params = []
        
        for key, value in kwargs.items():
            if key in ['full_name', 'interests', 'learning_style', 'email']:
                fields.append(f"{key} = %s")
                params.append(value)
        
        if not fields:
            return False
            
        params.append(user_id)
        query = f"UPDATE users SET {', '.join(fields)} WHERE id = %s"
        return self.data_manager.execute_query(query, params)
    
    def update_study_streaks(self, user_id):
        """更新学习连续天数"""
        today = datetime.now().date()
        
        # 获取当前连续记录
        streaks = self.data_manager.execute_query('''
            SELECT * FROM study_streaks WHERE user_id = %s
        ''', (user_id,))
        
        if not streaks:
            self.data_manager.execute_query('''
                INSERT INTO study_streaks (user_id, current_streak_days, last_study_date)
                VALUES (%s, 1, %s)
            ''', (user_id, today))
            return 1
            
        streak = streaks[0]
        last_date = streak['last_study_date']
        
        # 计算连续天数
        if last_date is None:
            # 第一次学习
            current_streak = 1
        elif (today - last_date).days == 1:
            # 连续学习
            current_streak = streak['current_streak_days'] + 1
        elif (today - last_date).days == 0:
            # 同一天学习，连续天数不变
            current_streak = streak['current_streak_days']
        else:
            # 中断后重新开始
            current_streak = 1
        
        # 更新最长连续记录
        longest_streak = max(current_streak, streak['longest_streak_days'])
        
        # 保存更新
        self.data_manager.execute_query('''
            UPDATE study_streaks 
            SET current_streak_days = %s, 
                longest_streak_days = %s,
                last_study_date = %s
            WHERE user_id = %s
        ''', (current_streak, longest_streak, today, user_id))
        
        return current_streak

# 单例实例
user_manager = UserManager()