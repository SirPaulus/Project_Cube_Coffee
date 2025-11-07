from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.screenmanager import Screen
from kivymd.app import MDApp

from src.services import db as db_layer


class RegistrationScreen(Screen):
    """Экран регистрации пользователя."""

    user_name = StringProperty("")
    user_phone = StringProperty("")
    error_text = StringProperty("")
    is_saving = BooleanProperty(False)

    def on_pre_enter(self, *args):
        self._prefill_from_db()
        return super().on_pre_enter(*args)

    def _prefill_from_db(self) -> None:
        """Заполняет форму данными, если они уже есть в базе."""
        try:
            user = db_layer.get_user()
        except Exception:
            user = {"name": "", "phone": ""}
        self.user_name = user.get("name", "") or ""
        self.user_phone = user.get("phone", "") or ""

    def submit(self) -> None:
        """Сохраняет данные пользователя и завершает регистрацию."""
        if self.is_saving:
            return

        name = (self.user_name or "").strip()
        phone = (self.user_phone or "").strip()

        if not name:
            self.error_text = "Введите имя"
            return

        if len(phone) < 8:
            self.error_text = "Введите корректный телефон"
            return

        self.error_text = ""
        self.is_saving = True
        try:
            db_layer.update_user(name=name, phone=phone)
            app = MDApp.get_running_app()
            if app:
                app.on_registration_complete()
        except Exception:
            self.error_text = "Не удалось сохранить данные"
        finally:
            self.is_saving = False

    def on_cancel(self) -> None:
        """Возврат на предыдущий экран без сохранения."""
        app = MDApp.get_running_app()
        if app:
            app.go_back()

