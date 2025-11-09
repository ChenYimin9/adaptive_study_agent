# Import various libraries
import hashlib
from datetime import datetime
from .data_manager import DataManager

class UserManager:
    def __init__(self):
        self.data_manager = DataManager()
    
    @staticmethod
    def _hash_password(password):
        """Password-encrypted storage"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def register_user(self, username, password, email, full_name, interests, learning_style):
        """Register a new user"""
        try:
            hashed_pw = self._hash_password(password)
            user_id = self.data_manager.execute_query('''
                INSERT INTO users (username, password, email, full_name, interests, learning_style)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (username, hashed_pw, email, full_name, interests, learning_style))
            
            # Initialize the learning habit record
            if user_id:
                self.data_manager.execute_query('''
                    INSERT INTO study_streaks (user_id) VALUES (%s)
                ''', (user_id,))
            
            return user_id
        except Exception as e:
            print(f"User registration error: {e}")
            return None
    
    def authenticate_user(self, username, password):
        """Verify the user's identity"""
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
        """Obtain user information"""
        users = self.data_manager.execute_query('''
            SELECT id, username, email, full_name, interests, learning_style, 
                   created_at, last_login 
            FROM users WHERE id = %s
        ''', (user_id,))
        return users[0] if users else None
    
    def update_user_profile(self, user_id, **kwargs):
        """Update user information"""
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
        """Update the consecutive days of study"""
        today = datetime.now().date()
        
        # Get the current consecutive record
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
        
        # Calculate consecutive days
        if last_date is None:
            # The first learning
            current_streak = 1
        elif (today - last_date).days == 1:
            # Continuous learning
            current_streak = streak['current_streak_days'] + 1
        elif (today - last_date).days == 0:
            # The number of consecutive days for studying on the same day remains unchanged
            current_streak = streak['current_streak_days']
        else:
            # Restart after interruption
            current_streak = 1
        
        # Update the longest consecutive record
        longest_streak = max(current_streak, streak['longest_streak_days'])
        
        # Save updates
        self.data_manager.execute_query('''
            UPDATE study_streaks 
            SET current_streak_days = %s, 
                longest_streak_days = %s,
                last_study_date = %s
            WHERE user_id = %s
        ''', (current_streak, longest_streak, today, user_id))
        
        return current_streak

# Example
user_manager = UserManager()