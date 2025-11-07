from kivy.uix.screenmanager import Screen
from kivy.properties import StringProperty

from src.services import db as db_layer


class ProfileScreen(Screen):
    user_name = StringProperty("")
    user_phone = StringProperty("")

    def on_pre_enter(self, *args):
        self._load_user()
        return super().on_pre_enter(*args)

    def _load_user(self):
        user = db_layer.get_user()
        self.user_name = user.get("name", "") or "Имя"
        self.user_phone = user.get("phone", "") or "+7(000)000-00-00"
    
    def go_back(self):
        """Возврат на предыдущий экран"""
        print('[ProfileScreen.go_back] Called!')
        
        if not self.manager:
            print('[ProfileScreen.go_back] ERROR: No manager!')
            return
        
        # Получаем app
        from kivymd.app import MDApp
        app = MDApp.get_running_app()
        
        if not app:
            print('[ProfileScreen.go_back] ERROR: No app found!')
            # Фолбэк на main
            if self.manager.has_screen('main'):
                self.manager.current = 'main'
            return
        
        # Получаем предыдущий экран из app
        previous_screen = getattr(app, '_previous_screen', None)
        print(f'[ProfileScreen.go_back] Previous screen: {previous_screen}')
        print(f'[ProfileScreen.go_back] Current screen: {self.manager.current}')
        print(f'[ProfileScreen.go_back] Available screens: {list(self.manager.screen_names)}')
        
        # Переключаемся на предыдущий экран или main
        target_screen = previous_screen if previous_screen and self.manager.has_screen(previous_screen) else 'main'
        print(f'[ProfileScreen.go_back] Switching to: {target_screen}')
        self.manager.current = target_screen
        print(f'[ProfileScreen.go_back] Switched! New current: {self.manager.current}')
