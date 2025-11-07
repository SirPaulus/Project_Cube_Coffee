from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import StringProperty, ListProperty
from kivy.clock import Clock


class OrderTabButton(ButtonBehavior, BoxLayout):
    tab_text = StringProperty("")
    bg_color = ListProperty([0.2, 0.8, 0.4, 1])


class PurchaseHistoryScreen(Screen):
    order_type = StringProperty("all")  # "all" or "mobile"
    
    def _update_tab_colors(self):
        """Обновление цветов вкладок"""
        if hasattr(self, 'ids') and 'tab_all' in self.ids and 'tab_mobile' in self.ids:
            tab_all = self.ids.tab_all
            tab_mobile = self.ids.tab_mobile
            
            if self.order_type == "all":
                tab_all.bg_color = (0.2, 0.8, 0.4, 1)  # Ярко-зеленый (активная)
                tab_mobile.bg_color = (0.3, 0.3, 0.3, 1)  # Темно-серый (неактивная)
            else:
                tab_all.bg_color = (0.3, 0.3, 0.3, 1)  # Темно-серый (неактивная)
                tab_mobile.bg_color = (0.2, 0.8, 0.4, 1)  # Ярко-зеленый (активная)
    
    def on_order_type(self, instance, value):
        """Автоматически обновляем цвета вкладок при изменении order_type"""
        Clock.schedule_once(lambda dt: self._update_tab_colors(), 0.1)
    
    def on_kv_post(self, base_widget):
        """Вызывается после загрузки KV файла"""
        super().on_kv_post(base_widget)
        Clock.schedule_once(lambda dt: self._update_tab_colors(), 0.1)
    
    def switch_order_type(self, order_type):
        """Переключение типа заказов"""
        self.order_type = order_type


