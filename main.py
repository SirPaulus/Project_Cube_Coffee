import os
import threading
from pathlib import Path
import time

from kivy.lang import Builder
from kivymd.app import MDApp
from kivy.uix.screenmanager import Screen
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.logger import Logger

from src.services import db as db_layer


class RootApp(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._previous_screen = None  # Запоминаем предыдущий экран
        self._bootstrap_started = False
        self._bootstrap_status = ""
        self._bootstrap_thread = None
        self._bootstrap_cancel = threading.Event()
        self._bootstrap_ready = False
        self._bootstrap_result_success = False
        self._bootstrap_video_finished = False
        self._bootstrap_transitioned = False
        self._bootstrap_video_source = os.path.join(
            os.path.dirname(__file__),
            "assets",
            "bootstrup",
            "CustomBootstrup.mp4",
        )
    
    def build(self):
        main_kv = os.path.join(os.path.dirname(__file__), "main.kv")
        if os.path.exists(main_kv):
            root = Builder.load_file(main_kv)
            # Закрытие активных оверлеев по Esc/Back
            try:
                Window.bind(on_key_down=self._on_key_down)
            except Exception:
                pass
            # Отслеживаем изменения экранов для запоминания предыдущего
            try:
                root.bind(current=self._on_screen_changed)
            except Exception:
                pass
            # Показываем экран загрузки, если доступен
            try:
                if root.has_screen('bootstrup'):
                    root.current = 'bootstrup'
            except Exception:
                Logger.exception("Не удалось переключиться на экран загрузки")
            return root

    @property
    def bootstrap_video_source(self) -> str:
        return self._bootstrap_video_source
    
    def _on_screen_changed(self, screen_manager, current_screen_name):
        """Запоминаем предыдущий экран при переключении"""
        # Не обновляем _previous_screen здесь, так как он уже установлен в open_screen_by_name
        pass
    
    def go_back(self):
        """Возврат на предыдущий экран"""
        print(f"[go_back] Called! _previous_screen={self._previous_screen}")
        sm = self.root
        
        if not sm:
            print("[go_back] ERROR: No screen manager!")
            return
        
        print(f"[go_back] Current screen: {sm.current}")
        print(f"[go_back] Available screens: {list(sm.screen_names)}")
        
        # Если есть предыдущий экран и он отличается от текущего
        if self._previous_screen:
            if self._previous_screen != sm.current and sm.has_screen(self._previous_screen):
                print(f"[go_back] Switching to previous screen: {self._previous_screen}")
                try:
                    sm.current = self._previous_screen
                    print(f"[go_back] Successfully switched! New current: {sm.current}")
                    return
                except Exception as e:
                    print(f"[go_back] Error switching to {self._previous_screen}: {e}")
        
        # Фолбэк на главный экран
        print(f"[go_back] Falling back to 'main'")
        if sm.has_screen('main'):
            try:
                sm.current = 'main'
                print(f"[go_back] Successfully switched to main! Current: {sm.current}")
            except Exception as e:
                print(f"[go_back] ERROR switching to main: {e}")
        else:
            print(f"[go_back] ERROR: 'main' screen not found!")
    
    def profile_logout(self):
        """Кнопка выхода в профиле - пока просто выводит в лог"""
        print("Hello world")

    # ----------------------- BOOTSTRAP FLOW -----------------------
    def start_bootstrap(self):
        """Запускаем асинхронную загрузку данных при показе стартового ролика"""
        if self._bootstrap_started:
            return
        self._bootstrap_started = True
        self._bootstrap_cancel.clear()
        self._bootstrap_ready = False
        self._bootstrap_result_success = False
        self._bootstrap_video_finished = False
        self._bootstrap_transitioned = False

        if not os.path.exists(self._bootstrap_video_source):
            Logger.warning(
                "Bootstrup: видео %s не найдено", self._bootstrap_video_source
            )

        self._set_bootstrap_status("Подготовка...")
        try:
            self._bootstrap_thread = threading.Thread(
                target=self._bootstrap_worker,
                name="CubeCoffeeBootstrapWorker",
                daemon=True,
            )
            self._bootstrap_thread.start()
        except Exception:
            Logger.exception("Bootstrup: не удалось запустить поток загрузки")
            self._finish_bootstrap(success=False)

    def _bootstrap_worker(self):
        try:
            steps = (
                ("Инициализация базы данных...", self._init_db_sync),
                ("Предзагрузка модулей экранов...", self._preload_screen_modules),
                ("Чтение шаблонов интерфейса...", self._preload_kv_templates),
                ("Загрузка профиля пользователя...", self._warmup_user_profile),
            )
            for message, func in steps:
                if self._bootstrap_cancel.is_set():
                    return
                self._set_bootstrap_status(message)
                func()
            self._set_bootstrap_status("Завершение загрузки...")
            time.sleep(0.2)
            self._schedule_bootstrap_complete(success=True)
        except Exception:
            Logger.exception("Bootstrup: ошибка в процессе загрузки")
            self._schedule_bootstrap_complete(success=False)

    def _schedule_bootstrap_complete(self, success: bool):
        Clock.schedule_once(lambda *_: self._handle_bootstrap_complete(success), 0)

    def _handle_bootstrap_complete(self, success: bool):
        sm = self.root
        if not sm:
            return
        try:
            boot_screen = sm.get_screen('bootstrup')
        except Exception:
            boot_screen = None
        if boot_screen:
            video = boot_screen.ids.get('boot_video') if hasattr(boot_screen, 'ids') else None
            if video:
                try:
                    video.state = 'stop'
                except Exception:
                    pass
            spinner = boot_screen.ids.get('loading_spinner') if hasattr(boot_screen, 'ids') else None
            if spinner:
                spinner.active = False
            label = boot_screen.ids.get('status_label') if hasattr(boot_screen, 'ids') else None
            if label:
                label.text = "Готово" if success else "Ошибка загрузки"
        self._bootstrap_ready = True
        self._bootstrap_result_success = success
        self._try_transition_after_bootstrap()

    def on_bootstrap_video_end(self, *args):
        self._bootstrap_video_finished = True
        self._try_transition_after_bootstrap(force=True)

    def _try_transition_after_bootstrap(self, force: bool = False):
        if self._bootstrap_transitioned:
            return
        if not force and not (self._bootstrap_ready and self._bootstrap_video_finished):
            return
        sm = self.root
        if not sm:
            return
        try:
            boot_screen = sm.get_screen('bootstrup')
        except Exception:
            boot_screen = None
        if boot_screen:
            video = boot_screen.ids.get('boot_video') if hasattr(boot_screen, 'ids') else None
            if video:
                try:
                    video.state = 'stop'
                except Exception:
                    pass
        try:
            target_screen = self._select_post_bootstrap_screen()
            if target_screen == 'registration':
                if sm.has_screen('registration'):
                    sm.current = 'registration'
                else:
                    self.open_screen_by_name('registration')
                self._bootstrap_transitioned = True
                return

            if sm.has_screen(target_screen):
                sm.current = target_screen
                self._bootstrap_transitioned = True
        except Exception:
            Logger.exception("Bootstrup: не удалось переключиться на основной экран")

    def _select_post_bootstrap_screen(self) -> str:
        try:
            if not db_layer.is_user_profile_completed():
                return 'registration'
        except Exception:
            Logger.exception("Bootstrup: ошибка проверки профиля пользователя")
        return 'main'

    def on_registration_complete(self):
        sm = self.root
        if not sm:
            return
        try:
            sm.current = 'main'
        except Exception:
            Logger.exception("Регистрация: не удалось перейти на основной экран")
        self._previous_screen = None

    def _set_bootstrap_status(self, message: str):
        self._bootstrap_status = message
        Clock.schedule_once(lambda *_: self._apply_bootstrap_status(message), 0)

    def _apply_bootstrap_status(self, message: str):
        sm = self.root
        if not sm or not sm.has_screen('bootstrup'):
            return
        try:
            screen = sm.get_screen('bootstrup')
        except Exception:
            return
        label = screen.ids.get('status_label') if hasattr(screen, 'ids') else None
        if label:
            label.text = message

    @staticmethod
    def _init_db_sync():
        try:
            from src.services.db import init_db

            init_db()
        except Exception:
            Logger.exception("Bootstrup: не удалось инициализировать базу данных")

    @staticmethod
    def _preload_screen_modules():
        screens_dir = Path(__file__).parent / "src" / "screens"
        for module_path in screens_dir.glob("*_screen.py"):
            module_name = f"src.screens.{module_path.stem}"
            try:
                __import__(module_name)
            except Exception:
                Logger.exception("Bootstrup: не удалось предзагрузить модуль %s", module_name)

    @staticmethod
    def _preload_kv_templates():
        widgets_dir = Path(__file__).parent / "src" / "widgets"
        for kv_path in widgets_dir.glob("*.kv"):
            try:
                kv_path.read_text(encoding="utf-8")
            except Exception:
                Logger.exception("Bootstrup: ошибка чтения KV файла %s", kv_path)

    @staticmethod
    def _warmup_user_profile():
        try:
            from src.services import db as db_layer

            db_layer.get_user()
        except Exception:
            Logger.exception("Bootstrup: не удалось прочитать профиль пользователя")

    # ----------------------- END BOOTSTRAP FLOW -----------------------

    def open_screen_by_name(self, screen_name):
        sm = self.root
        # Запоминаем текущий экран как предыдущий ПЕРЕД переключением
        # Но только если мы не переключаемся на тот же экран
        if sm.current and sm.current != screen_name:
            self._previous_screen = sm.current
            print(f"[open_screen_by_name] Saved previous screen: {self._previous_screen}")
        # Проверяем: уже есть такой экран? Тогда просто переключим
        if sm.has_screen(screen_name):
            sm.current = screen_name
            print(f"[open_screen_by_name] Switched to existing screen: {screen_name}")
            return
        # Динамически импортируем py и kv классы
        import importlib
        # Сопоставление коротких имён из меню к реальным файлам экранов
        alias_map = {
            'registration': 'registration',
            'profile': 'profile',
            'history': 'purchase_history',
            'loyalty': 'loyalty_program',
            'news': 'news',
            'our_menu': 'our_menu',
            'promo': 'promo_input',
            'referral': 'referral',
            'addresses': 'our_addresses',
            'faq': 'faq',
            'about': 'about_company',
            'work': 'work_on_us',
            'write_us': 'write_us',
            'contacts': 'contacts',
            'privacy_policy': 'agreement',
        }
        base_name = alias_map.get(screen_name, screen_name)
        screen_py = f"src.screens.{base_name}_screen"
        screen_kv = os.path.join("src", "widgets", f"{base_name}_screen.kv")
        module = importlib.import_module(screen_py)
        # Имя класса строим из base_name: words -> PascalCase + 'Screen'
        class_name = ''.join(part.capitalize() for part in base_name.split('_')) + 'Screen'
        # Берём именно наш класс экрана, а не импортированный в модуле kivy.uix.screenmanager.Screen
        try:
            ScreenClass = getattr(module, class_name)
        except AttributeError:
            # Фолбэк на базовый Screen на случай отсутствия пользовательского класса
            from kivy.uix.screenmanager import Screen as _KivyScreen
            ScreenClass = _KivyScreen
        Builder.load_file(os.path.join("src", "widgets", "base_screen.kv"))
        Builder.load_file(screen_kv)
        # Экземпляр дочернего экрана
        new_screen = ScreenClass(name=screen_name)
        sm.add_widget(new_screen)
        # Убеждаемся, что предыдущий экран сохранен перед переключением
        if sm.current and sm.current != screen_name:
            self._previous_screen = sm.current
            print(f"[open_screen_by_name] Saved previous screen before creating new: {self._previous_screen}")
        sm.current = screen_name
        print(f"[open_screen_by_name] Created and switched to new screen: {screen_name}")

    def open_overlay(self):
        overlay, panel = self._overlay_refs()
        if not overlay or not panel:
            return
        # Close mail overlay if open to avoid conflicts
        mail_overlay, _, _ = self._mail_refs()
        if mail_overlay and mail_overlay.opacity > 0 and not mail_overlay.disabled:
            self.close_mail_overlay()
        overlay.size_hint = (1, 1)
        overlay.size = overlay.parent.size if overlay.parent else overlay.size
        overlay.opacity = 1
        try:
            panel.x = -panel.width
        except Exception:
            pass
        def _enable_and_animate(*_):
            overlay.disabled = False
            from kivy.animation import Animation
            Animation(x=0, d=0.22, t='out_cubic').start(panel)
        from kivy.clock import Clock
        Clock.schedule_once(_enable_and_animate, 0)

    def overlay_nav(self, screen_name):
        self.close_overlay()
        from kivy.clock import Clock
        Clock.schedule_once(lambda *_: self.open_screen_by_name(screen_name), 0.25)

    def logout(self):
        # Простая заглушка выхода — возвращаемся на главный экран
        try:
            self.close_mail_overlay()
        except Exception:
            pass
        try:
            self.close_overlay()
        except Exception:
            pass
        try:
            self.root.current = 'main'
        except Exception:
            pass

    def close_overlay(self):
        overlay, panel = self._overlay_refs()
        if not overlay or overlay.opacity == 0 or overlay.size == (0, 0):
            return
        try:
            if not panel or getattr(panel, 'parent', None) is None:
                raise Exception("Открытие overlay невозможно — panel не валиден!")
            from kivy.animation import Animation
            def _hide(*_):
                if overlay:
                    overlay.opacity = 0
                    overlay.disabled = True
                    overlay.size_hint = (None, None)
                    overlay.size = (0, 0)
                if panel:
                    panel.x = -panel.width
            Animation(x=-panel.width, d=0.18, t='in_cubic').start(panel)
            Animation(d=0.18).bind(on_complete=_hide).start(panel)
        except Exception as e:
            print(f'[overlay] Animation fail: {e}')
            overlay.opacity = 0
            overlay.disabled = True
            overlay.size_hint = (None, None)
            overlay.size = (0, 0)

    def _overlay_refs(self):
        sm = self.root
        if hasattr(sm, 'current_screen') and sm.current_screen:
            root = getattr(sm.current_screen, 'children', [])[0]  # MainRoot внутри MainScreen
            try:
                return root.ids['overlay_root'], root.ids['overlay_panel']
            except Exception:
                return None, None
        return None, None

    # ----------------------- MAIL OVERLAY -----------------------
    def _mail_refs(self):
        sm = self.root
        if not sm or not hasattr(sm, 'current'):
            return None, None, None
        
        # Получаем текущий экран более надежным способом
        try:
            current_screen = sm.get_screen(sm.current) if hasattr(sm, 'get_screen') else (sm.current_screen if hasattr(sm, 'current_screen') else None)
        except Exception as e:
            print(f'[mail_refs] Error getting current screen: {e}')
            current_screen = None
        
        if not current_screen:
            print(f'[mail_refs] No current screen found')
            return None, None, None
        
        # Получаем корневой виджет экрана (обычно первый дочерний элемент)
        root = None
        if hasattr(current_screen, 'children') and len(current_screen.children) > 0:
            root = current_screen.children[0]
        
        if not root:
            print(f'[mail_refs] No root widget found in current screen')
            return None, None, None
        
        print(f'[mail_refs] Root widget type: {type(root).__name__}')
        print(f'[mail_refs] Root has ids: {hasattr(root, "ids")}')
        
        # Ищем overlay по id - пробуем разные способы
        overlay = None
        panel = None
        mail_list = None
        
        # Способ 1: прямой доступ через ids словарь корневого виджета
        if hasattr(root, 'ids'):
            try:
                print(f'[mail_refs] Available ids in root: {list(root.ids.keys())}')
                # Пробуем прямой доступ
                if 'mail_overlay_root' in root.ids:
                    overlay = root.ids['mail_overlay_root']
                if 'mail_panel' in root.ids:
                    panel = root.ids['mail_panel']
                if 'mail_list' in root.ids:
                    mail_list = root.ids['mail_list']
            except Exception as e:
                print(f'[mail_refs] Error accessing ids directly: {e}')
        
        # Способ 1.5: проверяем ids самого экрана (может быть ids там)
        if not overlay or not panel or not mail_list:
            try:
                if hasattr(current_screen, 'ids'):
                    print(f'[mail_refs] Available ids in screen: {list(current_screen.ids.keys())}')
                    if 'mail_overlay_root' in current_screen.ids and not overlay:
                        overlay = current_screen.ids['mail_overlay_root']
                    if 'mail_panel' in current_screen.ids and not panel:
                        panel = current_screen.ids['mail_panel']
                    if 'mail_list' in current_screen.ids and not mail_list:
                        mail_list = current_screen.ids['mail_list']
            except Exception as e:
                print(f'[mail_refs] Error accessing screen ids: {e}')
        
        # Способ 2: рекурсивный поиск по всему дереву виджетов
        if not overlay or not panel or not mail_list:
            def find_widget_by_id(widget, widget_id, depth=0, visited=None):
                """Рекурсивный поиск виджета по id"""
                if visited is None:
                    visited = set()
                
                if depth > 20 or id(widget) in visited:  # Защита от бесконечной рекурсии
                    return None
                
                visited.add(id(widget))
                
                # Проверяем ids текущего виджета
                if hasattr(widget, 'ids'):
                    try:
                        ids_dict = widget.ids
                        if isinstance(ids_dict, dict) and widget_id in ids_dict:
                            found = ids_dict[widget_id]
                            if found is not None:
                                return found
                    except Exception as e:
                        pass
                
                # Также проверяем, может быть id хранится как атрибут
                if hasattr(widget, 'ids'):
                    try:
                        # Пробуем получить через getattr
                        if hasattr(widget.ids, 'get'):
                            result = widget.ids.get(widget_id)
                            if result is not None:
                                return result
                    except:
                        pass
                
                # Проверяем дочерние виджеты
                if hasattr(widget, 'children'):
                    for child in widget.children:
                        result = find_widget_by_id(child, widget_id, depth + 1, visited)
                        if result:
                            return result
                
                return None
            
            if not overlay:
                overlay = find_widget_by_id(root, 'mail_overlay_root')
                print(f'[mail_refs] Recursive search for overlay: {overlay is not None}')
            if not panel:
                panel = find_widget_by_id(root, 'mail_panel')
                print(f'[mail_refs] Recursive search for panel: {panel is not None}')
            if not mail_list:
                mail_list = find_widget_by_id(root, 'mail_list')
                print(f'[mail_refs] Recursive search for mail_list: {mail_list is not None}')
            
            # Способ 3: поиск по типу и характеристикам - ищем все FloatLayout и проверяем их ids
            if not overlay or not panel or not mail_list:
                from kivy.uix.floatlayout import FloatLayout
                from kivy.uix.boxlayout import BoxLayout
                from kivymd.uix.boxlayout import MDBoxLayout
                
                def find_all_widgets_by_type(widget, widget_type, depth=0, visited=None):
                    """Найти все виджеты определенного типа"""
                    if visited is None:
                        visited = set()
                    if depth > 30 or id(widget) in visited:
                        return []
                    visited.add(id(widget))
                    
                    results = []
                    if isinstance(widget, widget_type):
                        results.append(widget)
                    
                    if hasattr(widget, 'children'):
                        for child in widget.children:
                            results.extend(find_all_widgets_by_type(child, widget_type, depth + 1, visited))
                    
                    return results
                
                # Ищем все FloatLayout и проверяем их ids
                all_float_layouts = find_all_widgets_by_type(root, FloatLayout)
                print(f'[mail_refs] Found {len(all_float_layouts)} FloatLayout widgets')
                
                for fl in all_float_layouts:
                    # Проверяем ids
                    if hasattr(fl, 'ids'):
                        try:
                            if 'mail_overlay_root' in fl.ids and not overlay:
                                overlay = fl.ids['mail_overlay_root']
                                print(f'[mail_refs] Found overlay by FloatLayout ids search!')
                        except:
                            pass
                    
                    # Также проверяем по характеристикам: FloatLayout с opacity=0, disabled=True, size=(0,0)
                    if not overlay:
                        try:
                            if (hasattr(fl, 'opacity') and hasattr(fl, 'disabled') and 
                                hasattr(fl, 'size') and hasattr(fl, 'size_hint')):
                                if (fl.opacity == 0 and fl.disabled == True and 
                                    fl.size == [0, 0] and fl.size_hint == [None, None]):
                                    # Проверяем, есть ли внутри BoxLayout с id='mail_panel'
                                    if hasattr(fl, 'children'):
                                        for child in fl.children:
                                            if isinstance(child, BoxLayout):
                                                # Проверяем, есть ли внутри MDBoxLayout с id='mail_list'
                                                if hasattr(child, 'children'):
                                                    for grandchild in child.children:
                                                        if isinstance(grandchild, MDBoxLayout):
                                                            # Это похоже на наш overlay!
                                                            overlay = fl
                                                            print(f'[mail_refs] Found overlay by characteristics!')
                                                            break
                                                if overlay:
                                                    break
                                    if overlay:
                                        break
                        except Exception as e:
                            pass
                
                # Если нашли overlay, ищем panel и mail_list внутри него
                if overlay and (not panel or not mail_list):
                    if hasattr(overlay, 'children'):
                        for child in overlay.children:
                            if isinstance(child, BoxLayout):
                                # Проверяем ids
                                if hasattr(child, 'ids') and 'mail_panel' in child.ids and not panel:
                                    panel = child.ids['mail_panel']
                                # Если не нашли по ids, используем сам виджет
                                if not panel:
                                    # Проверяем характеристики: BoxLayout с orientation='vertical'
                                    if hasattr(child, 'orientation') and child.orientation == 'vertical':
                                        panel = child
                                        print(f'[mail_refs] Found panel by characteristics!')
                                
                                # Ищем mail_list внутри panel - он находится внутри ScrollView
                                if panel and hasattr(panel, 'children'):
                                    from kivy.uix.scrollview import ScrollView
                                    for grandchild in panel.children:
                                        # Ищем ScrollView
                                        if isinstance(grandchild, ScrollView):
                                            # Внутри ScrollView должен быть MDBoxLayout с id='mail_list'
                                            if hasattr(grandchild, 'children'):
                                                for great_grandchild in grandchild.children:
                                                    if isinstance(great_grandchild, MDBoxLayout):
                                                        # Проверяем ids
                                                        if hasattr(great_grandchild, 'ids') and 'mail_list' in great_grandchild.ids and not mail_list:
                                                            mail_list = great_grandchild.ids['mail_list']
                                                        # Если не нашли по ids, используем сам виджет
                                                        if not mail_list:
                                                            mail_list = great_grandchild
                                                            print(f'[mail_refs] Found mail_list by characteristics!')
                                                        break
                                        # Также проверяем напрямую MDBoxLayout (на случай другой структуры)
                                        elif isinstance(grandchild, MDBoxLayout):
                                            # Проверяем ids
                                            if hasattr(grandchild, 'ids') and 'mail_list' in grandchild.ids and not mail_list:
                                                mail_list = grandchild.ids['mail_list']
                                            # Если не нашли по ids, используем сам виджет
                                            if not mail_list:
                                                mail_list = grandchild
                                                print(f'[mail_refs] Found mail_list by characteristics (direct)!')
                                break
        
        if overlay and panel and mail_list:
            print(f'[mail_refs] Successfully found all components!')
            return overlay, panel, mail_list
        else:
            print(f'[mail_refs] Not all components found: overlay={overlay is not None}, panel={panel is not None}, mail_list={mail_list is not None}')
            # Попробуем найти через поиск по всем виджетам экрана
            def find_all_widgets(widget, widget_type=None):
                """Найти все виджеты определенного типа"""
                results = []
                if widget_type is None or isinstance(widget, widget_type):
                    results.append(widget)
                if hasattr(widget, 'children'):
                    for child in widget.children:
                        results.extend(find_all_widgets(child, widget_type))
                return results
            
            all_float_layouts = find_all_widgets(root)
            print(f'[mail_refs] Total widgets in tree: {len(all_float_layouts)}')
        return None, None, None

    def open_mail_overlay(self):
        # Пробуем найти overlay с небольшой задержкой, чтобы убедиться, что виджеты построены
        from kivy.clock import Clock
        def _try_open(*args):
            overlay, panel, mail_list = self._mail_refs()
            if not overlay or not panel or not mail_list:
                print(f'[open_mail_overlay] Failed to find overlay components. overlay={overlay}, panel={panel}, mail_list={mail_list}')
                print(f'[open_mail_overlay] Current screen: {self.root.current if self.root else "None"}')
                return
            
            # Close left menu overlay if open to avoid conflicts
            menu_overlay, _ = self._overlay_refs()
            if menu_overlay and menu_overlay.opacity > 0 and not menu_overlay.disabled:
                self.close_overlay()
            # Show overlay and slide panel from right
            overlay.size_hint = (1, 1)
            overlay.size = overlay.parent.size if overlay.parent else overlay.size
            overlay.opacity = 1
            overlay.disabled = False
            try:
                root = overlay.parent
                if root:
                    panel.x = root.width
            except Exception:
                pass
            from kivy.animation import Animation
            Animation(x=(overlay.parent.width - panel.width) if overlay.parent else 0, d=0.22, t='out_cubic').start(panel)
            # Populate with random messages every time it's opened
            self._populate_random_mail(mail_list)
        
        # Пробуем сразу, если не получится - с задержкой
        overlay, panel, mail_list = self._mail_refs()
        if not overlay or not panel or not mail_list:
            Clock.schedule_once(_try_open, 0.01)
        else:
            _try_open()

    def close_mail_overlay(self):
        overlay, panel, _ = self._mail_refs()
        if not overlay:
            return
        if not panel:
            # Фолбэк: просто скрываем затемнение
            overlay.opacity = 0
            overlay.disabled = True
            overlay.size_hint = (None, None)
            overlay.size = (0, 0)
            return
        from kivy.animation import Animation
        def _hide(*_):
            overlay.opacity = 0
            overlay.disabled = True
            overlay.size_hint = (None, None)
            overlay.size = (0, 0)
        target_x = overlay.parent.width if overlay.parent else (panel.x + panel.width)
        anim = Animation(x=target_x, d=0.18, t='in_cubic')
        anim.bind(on_complete=lambda *_: _hide())
        anim.start(panel)

    def _populate_random_mail(self, mail_list):
        from datetime import datetime, timedelta
        import random
        from kivymd.uix.card import MDCard
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.anchorlayout import AnchorLayout
        from kivy.uix.label import Label

        # Clear existing
        mail_list.clear_widgets()

        # Russian months gen
        months = [
            'января','февраля','марта','апреля','мая','июня',
            'июля','августа','сентября','октября','ноября','декабря'
        ]

        sample_sentences = [
            'Предварительные выводы неутешительны: рост активности впечатляет.',
            'Задача организации в особенности актуальна в современных условиях.',
            'Повседневная практика показывает необходимость глубоких размышлений.',
            'Намеченные планы требуют уточнения деталей и сроков.',
            'Синергия усилий команды приносит ощутимый результат.',
            'Новые горизонты открываются при поддержке наших гостей.',
            'Мы ценим обратную связь и учитываем все предложения.',
            'Напоминаем о сезонном меню — загляните на витрину.',
            'Ваши бонусы ждут: оплачивайте кофе быстрее и выгоднее.',
            'Спасибо, что вы с нами!'
        ]

        now = datetime.now()
        num_messages = random.randint(5, 9)
        dates = [now - timedelta(days=i) for i in range(num_messages)]

        for dt in dates:
            # Date header
            date_text = f"{dt.day} {months[dt.month-1]} {dt.year} г."
            date_lbl = Label(
                text=date_text,
                color=(0, 0, 0, 1),
                size_hint_y=None,
                height=28,
                halign='center',
                valign='middle'
            )
            date_lbl.bind(size=lambda inst, *_: setattr(inst, 'text_size', inst.size))
            mail_list.add_widget(date_lbl)

            # Message card
            text = ' '.join(random.sample(sample_sentences, random.randint(2, 4)))
            time_text = dt.strftime('%H:%M')

            card = MDCard(
                size_hint=(1, None),
                radius=[12, 12, 12, 12],
                padding=(12, 10),
                md_bg_color=(0.92, 0.92, 0.92, 1)
            )
            # Vertical content
            content = BoxLayout(orientation='vertical', size_hint_y=None, spacing=4)

            msg_lbl = Label(
                text=text,
                color=(0, 0, 0, 1),
                size_hint_y=None,
                halign='left',
                valign='top'
            )
            msg_lbl.bind(
                texture_size=lambda inst, *_: (
                    setattr(inst, 'size', (card.width - 24, inst.texture_size[1]))
                )
            )
            msg_lbl.bind(size=lambda inst, *_: setattr(inst, 'text_size', inst.size))

            time_row = AnchorLayout(anchor_x='right', anchor_y='center', size_hint_y=None, height=18)
            time_lbl = Label(
                text=time_text,
                color=(0.2, 0.2, 0.2, 1),
                font_size='11sp',
                size_hint=(None, None),
                size=(60, 18)
            )
            time_row.add_widget(time_lbl)

            # compute dynamic height after text updates via Clock
            content.add_widget(msg_lbl)
            content.add_widget(time_row)
            card.add_widget(content)
            mail_list.add_widget(card)

            # Adjust heights on next frame
            from kivy.clock import Clock
            def _fix_heights(*_):
                content.height = msg_lbl.height + time_row.height + 4
                card.height = content.height + 20
            Clock.schedule_once(_fix_heights, 0)

    def footer_addresses_click(self):
        """Обработчик нажатия на кнопку 'Наши кофейни'"""
        self.open_screen_by_name('addresses')
    
    def footer_invite_click(self):
        """Обработчик нажатия на кнопку 'Пригласить'"""
        self.open_screen_by_name('referral')

    # ----------------------- LOYALTY OVERLAY -----------------------
    def _loyalty_refs(self):
        """Получить ссылки на элементы оверлея программы лояльности"""
        sm = self.root
        if not sm or not hasattr(sm, 'current'):
            return None, None, None
        
        try:
            current_screen = sm.get_screen(sm.current) if hasattr(sm, 'get_screen') else (sm.current_screen if hasattr(sm, 'current_screen') else None)
        except Exception:
            current_screen = None
        
        if not current_screen:
            return None, None, None
        
        root = None
        if hasattr(current_screen, 'children') and len(current_screen.children) > 0:
            root = current_screen.children[0]
        
        if not root:
            return None, None, None
        
        overlay = None
        panel = None
        
        if hasattr(root, 'ids') and 'loyalty_overlay_root' in root.ids:
            overlay = root.ids['loyalty_overlay_root']
            if 'loyalty_panel' in root.ids:
                panel = root.ids['loyalty_panel']
        if overlay and not panel and hasattr(overlay, 'ids'):
            panel = overlay.ids.get('loyalty_panel')
        
        return overlay, panel, None
    
    def open_loyalty_overlay(self):
        """Открыть оверлей программы лояльности"""
        overlay, panel, _ = self._loyalty_refs()
        if not overlay:
            return
        
        # Закрываем другие оверлеи
        mail_overlay, _, _ = self._mail_refs()
        if mail_overlay and mail_overlay.opacity > 0 and not mail_overlay.disabled:
            self.close_mail_overlay()
        menu_overlay, _ = self._overlay_refs()
        if menu_overlay and menu_overlay.opacity > 0 and not menu_overlay.disabled:
            self.close_overlay()
        
        # Получаем код пользователя и обновляем label
        try:
            from src.services import db as db_layer
            user = db_layer.get_user()
            user_code = user.get("phone", "").replace("+", "").replace("(", "").replace(")", "").replace("-", "").replace(" ", "")
            if not user_code:
                user_code = "13037"  # Дефолтный код
            
            # Ищем label с кодом и обновляем оба
            code_text = user_code[:5] if len(user_code) >= 5 else user_code.zfill(5)
            if hasattr(overlay, 'ids'):
                if 'loyalty_code_label' in overlay.ids:
                    code_label = overlay.ids['loyalty_code_label']
                    code_label.text = code_text
                if 'loyalty_code_label_small' in overlay.ids:
                    code_label_small = overlay.ids['loyalty_code_label_small']
                    code_label_small.text = code_text
        except Exception:
            pass
        
        # Показываем overlay
        overlay.size_hint = (1, 1)
        overlay.size = overlay.parent.size if overlay.parent else overlay.size
        overlay.opacity = 1
        overlay.disabled = False
        
        # Подготовка панели: старт снизу и анимация вверх
        try:
            if panel and overlay:
                panel.height = overlay.height * 0.8
                panel.y = -panel.height
                from kivy.animation import Animation
                Animation(y=0, d=0.22, t='out_cubic').start(panel)
        except Exception:
            pass
    
    def close_loyalty_overlay(self):
        """Закрыть оверлей программы лояльности"""
        overlay, panel, _ = self._loyalty_refs()
        if not overlay:
            return
        
        try:
            if panel:
                from kivy.animation import Animation
                def _hide(*_):
                    overlay.opacity = 0
                    overlay.disabled = True
                    overlay.size_hint = (None, None)
                    overlay.size = (0, 0)
                Animation(y=-panel.height, d=0.18, t='in_cubic').bind(on_complete=lambda *_: _hide()).start(panel)
                return
        except Exception:
            pass
        overlay.opacity = 0
        overlay.disabled = True
        overlay.size_hint = (None, None)
        overlay.size = (0, 0)
    
    # ----------------------- LOYALTY PROGRAM INFO OVERLAY -----------------------
    def _loyalty_program_refs(self):
        """Получить ссылки на элементы оверлея информации о программе лояльности"""
        sm = self.root
        if not sm or not hasattr(sm, 'current'):
            return None, None
        
        try:
            current_screen = sm.get_screen(sm.current) if hasattr(sm, 'get_screen') else (sm.current_screen if hasattr(sm, 'current_screen') else None)
        except Exception:
            current_screen = None
        
        if not current_screen:
            return None, None
        
        root = None
        if hasattr(current_screen, 'children') and len(current_screen.children) > 0:
            root = current_screen.children[0]
        
        if not root:
            return None, None
        
        overlay = None
        panel = None
        
        if hasattr(root, 'ids') and 'loyalty_program_overlay_root' in root.ids:
            overlay = root.ids['loyalty_program_overlay_root']
            if 'loyalty_program_panel' in root.ids:
                panel = root.ids['loyalty_program_panel']
        
        return overlay, panel
    
    def open_loyalty_program_overlay(self):
        """Открыть оверлей информации о программе лояльности"""
        overlay, panel = self._loyalty_program_refs()
        if not overlay:
            return
        
        # Закрываем другие оверлеи
        loyalty_overlay, _, _ = self._loyalty_refs()
        if loyalty_overlay and loyalty_overlay.opacity > 0 and not loyalty_overlay.disabled:
            self.close_loyalty_overlay()
        referral_overlay, _ = self._referral_refs()
        if referral_overlay and referral_overlay.opacity > 0 and not referral_overlay.disabled:
            self.close_referral_overlay()
        mail_overlay, _, _ = self._mail_refs()
        if mail_overlay and mail_overlay.opacity > 0 and not mail_overlay.disabled:
            self.close_mail_overlay()
        menu_overlay, _ = self._overlay_refs()
        if menu_overlay and menu_overlay.opacity > 0 and not menu_overlay.disabled:
            self.close_overlay()
        
        # Показываем overlay
        overlay.size_hint = (1, 1)
        overlay.size = overlay.parent.size if overlay.parent else overlay.size
        overlay.opacity = 1
        overlay.disabled = False
        
        # Подготовка панели: старт снизу и анимация вверх
        try:
            if panel and overlay:
                panel.height = overlay.height * 0.8
                panel.y = -panel.height
                from kivy.animation import Animation
                Animation(y=0, d=0.22, t='out_cubic').start(panel)
        except Exception:
            pass
    
    def close_loyalty_program_overlay(self):
        """Закрыть оверлей информации о программе лояльности"""
        overlay, panel = self._loyalty_program_refs()
        if not overlay:
            return
        
        try:
            if panel:
                from kivy.animation import Animation
                def _hide(*_):
                    overlay.opacity = 0
                    overlay.disabled = True
                    overlay.size_hint = (None, None)
                    overlay.size = (0, 0)
                Animation(y=-panel.height, d=0.18, t='in_cubic').bind(on_complete=lambda *_: _hide()).start(panel)
                return
        except Exception:
            pass
        overlay.opacity = 0
        overlay.disabled = True
        overlay.size_hint = (None, None)
        overlay.size = (0, 0)

    # ----------------------- REFERRAL OVERLAY -----------------------
    def _referral_refs(self):
        """Получить ссылки на элементы оверлея приглашения друга"""
        sm = self.root
        if not sm or not hasattr(sm, 'current'):
            return None, None
        
        try:
            current_screen = sm.get_screen(sm.current) if hasattr(sm, 'get_screen') else (sm.current_screen if hasattr(sm, 'current_screen') else None)
        except Exception:
            current_screen = None
        
        if not current_screen:
            return None, None
        
        root = None
        if hasattr(current_screen, 'children') and len(current_screen.children) > 0:
            root = current_screen.children[0]
        
        if not root:
            return None, None
        
        overlay = None
        panel = None
        
        if hasattr(root, 'ids') and 'referral_overlay_root' in root.ids:
            overlay = root.ids['referral_overlay_root']
            if 'referral_panel' in root.ids:
                panel = root.ids['referral_panel']
        
        return overlay, panel
    
    def open_referral_overlay(self):
        """Открыть оверлей приглашения друга"""
        overlay, panel = self._referral_refs()
        if not overlay:
            return
        
        # Закрываем другие оверлеи
        loyalty_overlay, _, _ = self._loyalty_refs()
        if loyalty_overlay and loyalty_overlay.opacity > 0 and not loyalty_overlay.disabled:
            self.close_loyalty_overlay()
        loyalty_program_overlay, _ = self._loyalty_program_refs()
        if loyalty_program_overlay and loyalty_program_overlay.opacity > 0 and not loyalty_program_overlay.disabled:
            self.close_loyalty_program_overlay()
        mail_overlay, _, _ = self._mail_refs()
        if mail_overlay and mail_overlay.opacity > 0 and not mail_overlay.disabled:
            self.close_mail_overlay()
        menu_overlay, _ = self._overlay_refs()
        if menu_overlay and menu_overlay.opacity > 0 and not menu_overlay.disabled:
            self.close_overlay()
        
        # Показываем overlay
        overlay.size_hint = (1, 1)
        overlay.size = overlay.parent.size if overlay.parent else overlay.size
        overlay.opacity = 1
        overlay.disabled = False
        
        # Подготовка панели: старт снизу и анимация вверх
        try:
            if panel and overlay:
                panel.height = overlay.height * 0.8
                panel.y = -panel.height
                from kivy.animation import Animation
                Animation(y=0, d=0.22, t='out_cubic').start(panel)
        except Exception:
            pass
    
    def close_referral_overlay(self):
        """Закрыть оверлей приглашения друга"""
        overlay, panel = self._referral_refs()
        if not overlay:
            return
        
        try:
            if panel:
                from kivy.animation import Animation
                def _hide(*_):
                    overlay.opacity = 0
                    overlay.disabled = True
                    overlay.size_hint = (None, None)
                    overlay.size = (0, 0)
                Animation(y=-panel.height, d=0.18, t='in_cubic').bind(on_complete=lambda *_: _hide()).start(panel)
                return
        except Exception:
            pass
        overlay.opacity = 0
        overlay.disabled = True
        overlay.size_hint = (None, None)
        overlay.size = (0, 0)

    # ----------------------- DRINKS MENU OVERLAY -----------------------
    def _drinks_menu_refs(self):
        """Получить ссылки на элементы оверлея меню напитков"""
        sm = self.root
        if not sm or not hasattr(sm, 'current'):
            return None, None
        
        try:
            current_screen = sm.get_screen(sm.current) if hasattr(sm, 'get_screen') else (sm.current_screen if hasattr(sm, 'current_screen') else None)
        except Exception:
            current_screen = None
        
        if not current_screen:
            return None, None
        
        root = None
        if hasattr(current_screen, 'children') and len(current_screen.children) > 0:
            root = current_screen.children[0]
        
        if not root:
            return None, None
        
        overlay = None
        panel = None
        
        if hasattr(root, 'ids') and 'drinks_menu_overlay_root' in root.ids:
            overlay = root.ids['drinks_menu_overlay_root']
            if 'drinks_menu_panel' in root.ids:
                panel = root.ids['drinks_menu_panel']
        
        return overlay, panel
    
    def open_drinks_menu_overlay(self):
        """Открыть оверлей меню напитков"""
        overlay, panel = self._drinks_menu_refs()
        if not overlay:
            return
        
        # Закрываем другие оверлеи
        referral_overlay, _ = self._referral_refs()
        if referral_overlay and referral_overlay.opacity > 0 and not referral_overlay.disabled:
            self.close_referral_overlay()
        loyalty_program_overlay, _ = self._loyalty_program_refs()
        if loyalty_program_overlay and loyalty_program_overlay.opacity > 0 and not loyalty_program_overlay.disabled:
            self.close_loyalty_program_overlay()
        loyalty_overlay, _, _ = self._loyalty_refs()
        if loyalty_overlay and loyalty_overlay.opacity > 0 and not loyalty_overlay.disabled:
            self.close_loyalty_overlay()
        mail_overlay, _, _ = self._mail_refs()
        if mail_overlay and mail_overlay.opacity > 0 and not mail_overlay.disabled:
            self.close_mail_overlay()
        menu_overlay, _ = self._overlay_refs()
        if menu_overlay and menu_overlay.opacity > 0 and not menu_overlay.disabled:
            self.close_overlay()
        
        # Показываем overlay
        overlay.size_hint = (1, 1)
        overlay.size = overlay.parent.size if overlay.parent else overlay.size
        overlay.opacity = 1
        overlay.disabled = False
        
        # Подготовка панели: старт снизу и анимация вверх
        try:
            if panel and overlay:
                panel.height = overlay.height * 0.8
                panel.y = -panel.height
                from kivy.animation import Animation
                Animation(y=0, d=0.22, t='out_cubic').start(panel)
        except Exception:
            pass
    
    def close_drinks_menu_overlay(self):
        """Закрыть оверлей меню напитков"""
        overlay, panel = self._drinks_menu_refs()
        if not overlay:
            return
        
        try:
            if panel:
                from kivy.animation import Animation
                def _hide(*_):
                    overlay.opacity = 0
                    overlay.disabled = True
                    overlay.size_hint = (None, None)
                    overlay.size = (0, 0)
                Animation(y=-panel.height, d=0.18, t='in_cubic').bind(on_complete=lambda *_: _hide()).start(panel)
                return
        except Exception:
            pass
        overlay.opacity = 0
        overlay.disabled = True
        overlay.size_hint = (None, None)
        overlay.size = (0, 0)

    # ----------------------- GIFT OVERLAY (10-й напиток) -----------------------
    def _gift_refs(self):
        """Получить ссылки на элементы оверлея подарочного напитка"""
        sm = self.root
        if not sm or not hasattr(sm, 'current'):
            return None, None

        try:
            current_screen = sm.get_screen(sm.current) if hasattr(sm, 'get_screen') else (
                sm.current_screen if hasattr(sm, 'current_screen') else None
            )
        except Exception:
            current_screen = None

        if not current_screen:
            return None, None

        root = None
        if hasattr(current_screen, 'children') and len(current_screen.children) > 0:
            root = current_screen.children[0]

        if not root:
            return None, None

        overlay = None
        panel = None

        if hasattr(root, 'ids'):
            try:
                if 'gift_overlay_root' in root.ids:
                    overlay = root.ids['gift_overlay_root']
                if 'gift_panel' in root.ids:
                    panel = root.ids['gift_panel']
            except Exception:
                pass

        if (not overlay or not panel) and hasattr(current_screen, 'ids'):
            try:
                if 'gift_overlay_root' in current_screen.ids and not overlay:
                    overlay = current_screen.ids['gift_overlay_root']
                if 'gift_panel' in current_screen.ids and not panel:
                    panel = current_screen.ids['gift_panel']
            except Exception:
                pass

        def find_widget_by_id(widget, widget_id, depth=0, visited=None):
            if visited is None:
                visited = set()

            if depth > 40 or id(widget) in visited:
                return None

            visited.add(id(widget))

            if hasattr(widget, 'ids'):
                try:
                    ids_dict = widget.ids
                    if isinstance(ids_dict, dict) and widget_id in ids_dict:
                        found = ids_dict[widget_id]
                        if found is not None:
                            return found
                except Exception:
                    pass

            if hasattr(widget, 'children'):
                for child in widget.children:
                    result = find_widget_by_id(child, widget_id, depth + 1, visited)
                    if result:
                        return result

            return None

        if not overlay:
            overlay = find_widget_by_id(root, 'gift_overlay_root')
        if not panel:
            panel = find_widget_by_id(root, 'gift_panel')

        if not overlay or not panel:
            from kivy.uix.floatlayout import FloatLayout
            from kivy.uix.boxlayout import BoxLayout

            def find_all_widgets_by_type(widget, widget_type, depth=0, visited=None):
                if visited is None:
                    visited = set()
                if depth > 40 or id(widget) in visited:
                    return []
                visited.add(id(widget))

                results = []
                if isinstance(widget, widget_type):
                    results.append(widget)

                if hasattr(widget, 'children'):
                    for child in widget.children:
                        results.extend(find_all_widgets_by_type(child, widget_type, depth + 1, visited))

                return results

            all_float_layouts = find_all_widgets_by_type(root, FloatLayout)
            for fl in all_float_layouts:
                if overlay and panel:
                    break

                if hasattr(fl, 'ids'):
                    try:
                        if 'gift_overlay_root' in fl.ids and not overlay:
                            overlay = fl.ids['gift_overlay_root']
                        if 'gift_panel' in fl.ids and not panel:
                            panel = fl.ids['gift_panel']
                    except Exception:
                        pass

                size_val = getattr(fl, 'size', None)
                size_match = False
                if size_val is not None:
                    try:
                        size_match = tuple(size_val) == (0, 0)
                    except Exception:
                        size_match = False

                if (not overlay and hasattr(fl, 'opacity') and hasattr(fl, 'disabled') and size_match and
                        getattr(fl, 'disabled', True) and getattr(fl, 'opacity', 0) == 0):
                    if hasattr(fl, 'children'):
                        for child in fl.children:
                            if isinstance(child, BoxLayout):
                                if hasattr(child, 'ids') and 'gift_panel' in child.ids:
                                    overlay = fl
                                    panel = child.ids['gift_panel']
                                    break
                                if not panel and getattr(child, 'orientation', '') == 'vertical':
                                    panel = child
                                    overlay = fl
                                    break

        return overlay, panel

    def open_gift_overlay(self):
        """Открыть оверлей акции "10-й напиток в подарок" (50% высоты)"""
        from kivy.clock import Clock

        def _try_open(*_):
            overlay, panel = self._gift_refs()
            if not overlay or not panel:
                return

            try:
                drinks_overlay, _ = self._drinks_menu_refs()
                if drinks_overlay and drinks_overlay.opacity > 0 and not drinks_overlay.disabled:
                    self.close_drinks_menu_overlay()
                referral_overlay, _ = self._referral_refs()
                if referral_overlay and referral_overlay.opacity > 0 and not referral_overlay.disabled:
                    self.close_referral_overlay()
                loyalty_program_overlay, _ = self._loyalty_program_refs()
                if loyalty_program_overlay and loyalty_program_overlay.opacity > 0 and not loyalty_program_overlay.disabled:
                    self.close_loyalty_program_overlay()
                loyalty_overlay, _, _ = self._loyalty_refs()
                if loyalty_overlay and loyalty_overlay.opacity > 0 and not loyalty_overlay.disabled:
                    self.close_loyalty_overlay()
                mail_overlay, _, _ = self._mail_refs()
                if mail_overlay and mail_overlay.opacity > 0 and not mail_overlay.disabled:
                    self.close_mail_overlay()
                menu_overlay, _ = self._overlay_refs()
                if menu_overlay and menu_overlay.opacity > 0 and not menu_overlay.disabled:
                    self.close_overlay()
                status_overlay, _ = self._status_refs()
                if status_overlay and status_overlay.opacity > 0 and not status_overlay.disabled:
                    self.close_status_overlay()
            except Exception:
                pass

            overlay.size_hint = (1, 1)
            overlay.size = overlay.parent.size if overlay.parent else overlay.size
            overlay.opacity = 1
            overlay.disabled = False

            try:
                if panel and overlay:
                    panel.height = overlay.height * 0.8
                    panel.y = -panel.height
                    from kivy.animation import Animation
                    Animation(y=0, d=0.22, t='out_cubic').start(panel)
            except Exception:
                pass

        overlay, panel = self._gift_refs()
        if not overlay or not panel:
            Clock.schedule_once(_try_open, 0.01)
        else:
            _try_open()

    def close_gift_overlay(self):
        """Закрыть оверлей акции "10-й напиток в подарок"""
        overlay, panel = self._gift_refs()
        if not overlay:
            return

        try:
            if panel:
                from kivy.animation import Animation

                def _hide(*_):
                    overlay.opacity = 0
                    overlay.disabled = True
                    overlay.size_hint = (None, None)
                    overlay.size = (0, 0)

                Animation(y=-panel.height, d=0.18, t='in_cubic').bind(on_complete=lambda *_: _hide()).start(panel)
                return
        except Exception:
            pass

        overlay.opacity = 0
        overlay.disabled = True
        overlay.size_hint = (None, None)
        overlay.size = (0, 0)

    # ----------------------- STATUS OVERLAY -----------------------
    def _status_refs(self):
        """Получить ссылки на элементы оверлея статусов"""
        sm = self.root
        if not sm or not hasattr(sm, 'current'):
            return None, None
        
        try:
            current_screen = sm.get_screen(sm.current) if hasattr(sm, 'get_screen') else (sm.current_screen if hasattr(sm, 'current_screen') else None)
        except Exception as e:
            print(f'[_status_refs] Error getting current screen: {e}')
            current_screen = None
        
        if not current_screen:
            print(f'[_status_refs] No current screen found')
            return None, None
        
        root = None
        if hasattr(current_screen, 'children') and len(current_screen.children) > 0:
            root = current_screen.children[0]
        
        if not root:
            print(f'[_status_refs] No root widget found in current screen')
            return None, None
        
        overlay = None
        panel = None
        
        # Способ 1: прямой доступ через ids словарь корневого виджета
        if hasattr(root, 'ids'):
            try:
                print(f'[_status_refs] Available ids in root: {list(root.ids.keys())}')
                if 'status_overlay_root' in root.ids:
                    overlay = root.ids['status_overlay_root']
                    print(f'[_status_refs] Found overlay by direct ids access')
                if 'status_panel' in root.ids:
                    panel = root.ids['status_panel']
                    print(f'[_status_refs] Found panel by direct ids access')
            except Exception as e:
                print(f'[_status_refs] Error accessing ids directly: {e}')
        
        # Способ 1.5: проверяем ids самого экрана (может быть ids там)
        if not overlay or not panel:
            try:
                if hasattr(current_screen, 'ids'):
                    print(f'[_status_refs] Available ids in screen: {list(current_screen.ids.keys())}')
                    if 'status_overlay_root' in current_screen.ids and not overlay:
                        overlay = current_screen.ids['status_overlay_root']
                        print(f'[_status_refs] Found overlay by screen ids access')
                    if 'status_panel' in current_screen.ids and not panel:
                        panel = current_screen.ids['status_panel']
                        print(f'[_status_refs] Found panel by screen ids access')
            except Exception as e:
                print(f'[_status_refs] Error accessing screen ids: {e}')
        
        # Способ 2: рекурсивный поиск по всему дереву виджетов
        if not overlay or not panel:
            def find_widget_by_id(widget, widget_id, depth=0, visited=None):
                """Рекурсивный поиск виджета по id"""
                if visited is None:
                    visited = set()
                
                if depth > 30 or id(widget) in visited:
                    return None
                
                visited.add(id(widget))
                
                # Проверяем ids текущего виджета
                if hasattr(widget, 'ids'):
                    try:
                        ids_dict = widget.ids
                        if isinstance(ids_dict, dict) and widget_id in ids_dict:
                            found = ids_dict[widget_id]
                            if found is not None:
                                return found
                    except Exception:
                        pass
                
                # Проверяем дочерние виджеты
                if hasattr(widget, 'children'):
                    for child in widget.children:
                        result = find_widget_by_id(child, widget_id, depth + 1, visited)
                        if result:
                            return result
                
                return None
            
            if not overlay:
                overlay = find_widget_by_id(root, 'status_overlay_root')
                print(f'[_status_refs] Recursive search for overlay: {overlay is not None}')
            if not panel:
                panel = find_widget_by_id(root, 'status_panel')
                print(f'[_status_refs] Recursive search for panel: {panel is not None}')
        
        # Способ 3: поиск по типу виджета (как в _mail_refs)
        if not overlay or not panel:
            from kivy.uix.floatlayout import FloatLayout
            from kivy.uix.boxlayout import BoxLayout
            
            def find_all_widgets_by_type(widget, widget_type, depth=0, visited=None):
                """Найти все виджеты определенного типа"""
                if visited is None:
                    visited = set()
                if depth > 30 or id(widget) in visited:
                    return []
                visited.add(id(widget))
                
                results = []
                if isinstance(widget, widget_type):
                    results.append(widget)
                
                if hasattr(widget, 'children'):
                    for child in widget.children:
                        results.extend(find_all_widgets_by_type(child, widget_type, depth + 1, visited))
                
                return results
            
            # Ищем все FloatLayout и проверяем их ids
            all_float_layouts = find_all_widgets_by_type(root, FloatLayout)
            print(f'[_status_refs] Found {len(all_float_layouts)} FloatLayout widgets')
            
            for fl in all_float_layouts:
                # Проверяем ids
                if hasattr(fl, 'ids'):
                    try:
                        if 'status_overlay_root' in fl.ids and not overlay:
                            overlay = fl.ids['status_overlay_root']
                            print(f'[_status_refs] Found overlay by FloatLayout ids search!')
                    except:
                        pass
                
                # Также проверяем по характеристикам: FloatLayout с opacity=0, disabled=True, size=(0,0)
                if not overlay:
                    try:
                        if (hasattr(fl, 'opacity') and hasattr(fl, 'disabled') and 
                            hasattr(fl, 'size') and hasattr(fl, 'size_hint')):
                            # Проверяем size как кортеж или список
                            size_match = (fl.size == (0, 0) or fl.size == [0, 0] or 
                                         (hasattr(fl.size, '__len__') and len(fl.size) == 2 and fl.size[0] == 0 and fl.size[1] == 0))
                            size_hint_match = (fl.size_hint == (None, None) or fl.size_hint == [None, None] or
                                               (hasattr(fl.size_hint, '__len__') and len(fl.size_hint) == 2 and 
                                                fl.size_hint[0] is None and fl.size_hint[1] is None))
                            if (fl.opacity == 0 and fl.disabled == True and size_match and size_hint_match):
                                # Проверяем, есть ли внутри BoxLayout с id='status_panel'
                                if hasattr(fl, 'children'):
                                    for child in fl.children:
                                        if isinstance(child, BoxLayout):
                                            # Проверяем ids
                                            if hasattr(child, 'ids') and 'status_panel' in child.ids:
                                                overlay = fl
                                                panel = child.ids['status_panel']
                                                print(f'[_status_refs] Found overlay and panel by characteristics!')
                                                break
                                    if overlay:
                                        break
                    except Exception as e:
                        print(f'[_status_refs] Error in characteristics check: {e}')
                        pass
            
            # Если нашли overlay, ищем panel внутри него
            if overlay and not panel:
                if hasattr(overlay, 'children'):
                    for child in overlay.children:
                        if isinstance(child, BoxLayout):
                            # Проверяем ids
                            if hasattr(child, 'ids') and 'status_panel' in child.ids:
                                panel = child.ids['status_panel']
                            # Если не нашли по ids, используем сам виджет
                            if not panel:
                                # Проверяем характеристики: BoxLayout с orientation='vertical'
                                if hasattr(child, 'orientation') and child.orientation == 'vertical':
                                    panel = child
                                    print(f'[_status_refs] Found panel by characteristics!')
                            break
        
        if overlay and panel:
            print(f'[_status_refs] Successfully found all components!')
        else:
            print(f'[_status_refs] Not all components found: overlay={overlay is not None}, panel={panel is not None}')
        
        return overlay, panel
    
    def open_status_overlay(self):
        """Открыть оверлей информации о статусах"""
        # Пробуем найти overlay с небольшой задержкой, чтобы убедиться, что виджеты построены
        from kivy.clock import Clock
        def _try_open(*args):
            overlay, panel = self._status_refs()
            if not overlay or not panel:
                print(f'[open_status_overlay] Failed to find overlay components. overlay={overlay}, panel={panel}')
                print(f'[open_status_overlay] Current screen: {self.root.current if self.root else "None"}')
                return
            
            # Закрываем другие оверлеи
            drinks_overlay, _ = self._drinks_menu_refs()
            if drinks_overlay and drinks_overlay.opacity > 0 and not drinks_overlay.disabled:
                self.close_drinks_menu_overlay()
            referral_overlay, _ = self._referral_refs()
            if referral_overlay and referral_overlay.opacity > 0 and not referral_overlay.disabled:
                self.close_referral_overlay()
            loyalty_program_overlay, _ = self._loyalty_program_refs()
            if loyalty_program_overlay and loyalty_program_overlay.opacity > 0 and not loyalty_program_overlay.disabled:
                self.close_loyalty_program_overlay()
            loyalty_overlay, _, _ = self._loyalty_refs()
            if loyalty_overlay and loyalty_overlay.opacity > 0 and not loyalty_overlay.disabled:
                self.close_loyalty_overlay()
            mail_overlay, _, _ = self._mail_refs()
            if mail_overlay and mail_overlay.opacity > 0 and not mail_overlay.disabled:
                self.close_mail_overlay()
            menu_overlay, _ = self._overlay_refs()
            if menu_overlay and menu_overlay.opacity > 0 and not menu_overlay.disabled:
                self.close_overlay()
            
            # Показываем overlay
            overlay.size_hint = (1, 1)
            overlay.size = overlay.parent.size if overlay.parent else overlay.size
            overlay.opacity = 1
            overlay.disabled = False
            
            # Подготовка панели: старт снизу и анимация вверх
            try:
                if panel and overlay:
                    panel.height = overlay.height * 0.8
                    panel.y = -panel.height
                    from kivy.animation import Animation
                    Animation(y=0, d=0.22, t='out_cubic').start(panel)
            except Exception as e:
                print(f'[open_status_overlay] Error animating panel: {e}')
        
        # Пробуем сразу, если не получится - с задержкой
        overlay, panel = self._status_refs()
        if not overlay or not panel:
            Clock.schedule_once(_try_open, 0.01)
        else:
            _try_open()
    
    def close_status_overlay(self):
        """Закрыть оверлей информации о статусах"""
        overlay, panel = self._status_refs()
        if not overlay:
            return
        
        try:
            if panel:
                from kivy.animation import Animation
                def _hide(*_):
                    overlay.opacity = 0
                    overlay.disabled = True
                    overlay.size_hint = (None, None)
                    overlay.size = (0, 0)
                Animation(y=-panel.height, d=0.18, t='in_cubic').bind(on_complete=lambda *_: _hide()).start(panel)
                return
        except Exception:
            pass
        overlay.opacity = 0
        overlay.disabled = True
        overlay.size_hint = (None, None)
        overlay.size = (0, 0)

    # ---- Global keyboard handler ----
    def _on_key_down(self, _window, key, scancode, codepoint, modifiers):
        # Esc on desktop, Back on mobile (27 or 1001 depending on platform)
        if key in (27, 1001):
            # Try to close status overlay first
            overlay, _ = self._status_refs()
            if overlay and overlay.opacity > 0 and not overlay.disabled:
                self.close_status_overlay()
                return True
            # Try to close gift overlay
            overlay, _ = self._gift_refs()
            if overlay and overlay.opacity > 0 and not overlay.disabled:
                self.close_gift_overlay()
                return True
            # Try to close drinks menu overlay first
            overlay, _ = self._drinks_menu_refs()
            if overlay and overlay.opacity > 0 and not overlay.disabled:
                self.close_drinks_menu_overlay()
                return True
            # Try to close referral overlay
            overlay, _ = self._referral_refs()
            if overlay and overlay.opacity > 0 and not overlay.disabled:
                self.close_referral_overlay()
                return True
            # Try to close loyalty program overlay
            overlay, _ = self._loyalty_program_refs()
            if overlay and overlay.opacity > 0 and not overlay.disabled:
                self.close_loyalty_program_overlay()
                return True
            # Try to close loyalty overlay (code overlay)
            overlay, _, _ = self._loyalty_refs()
            if overlay and overlay.opacity > 0 and not overlay.disabled:
                self.close_loyalty_overlay()
                return True
            # Try to close mail overlay
            overlay, _, _ = self._mail_refs()
            if overlay and overlay.opacity > 0 and not overlay.disabled:
                self.close_mail_overlay()
                return True
            # Close left overlay if open
            overlay_root, _ = self._overlay_refs()
            if overlay_root and overlay_root.opacity > 0 and not overlay_root.disabled:
                self.close_overlay()
                return True
        return False

    def on_stop(self):
        self._bootstrap_cancel.set()
        thread = self._bootstrap_thread
        if thread and thread.is_alive():
            try:
                thread.join(timeout=1.0)
            except Exception:
                pass
        self._bootstrap_thread = None


if __name__ == "__main__":
    RootApp().run()
