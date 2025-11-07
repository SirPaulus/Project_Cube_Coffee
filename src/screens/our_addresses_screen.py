from __future__ import annotations

from dataclasses import dataclass
from typing import List

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from kivy_garden.mapview import MapMarkerPopup
from kivymd.uix.list import TwoLineListItem


@dataclass(frozen=True)
class CafeLocation:
    name: str
    address: str
    latitude: float
    longitude: float


class CafeMarker(MapMarkerPopup):
    """Map marker with a simple popup describing the cafe."""

    def __init__(self, location: CafeLocation, **kwargs) -> None:
        super().__init__(lat=location.latitude, lon=location.longitude, **kwargs)
        self.location = location
        self.source = "assets/icons/jam_coffee.png"
        self.anchor_x = 0.5
        self.anchor_y = 0

        popup = BoxLayout(orientation="vertical", padding=(dp(8), dp(8)), spacing=dp(4))
        popup.size_hint = (None, None)
        popup.bind(minimum_height=popup.setter("height"))
        popup.bind(minimum_width=popup.setter("width"))

        title = Label(
            text=location.name,
            color=(0, 0, 0, 1),
            bold=True,
            halign="left",
            valign="middle",
            text_size=(None, None),
            size_hint=(None, None),
        )
        title.bind(texture_size=title.setter("size"))
        popup.add_widget(title)

        subtitle = Label(
            text=location.address,
            color=(0, 0, 0, 1),
            halign="left",
            valign="middle",
            text_size=(None, None),
            size_hint=(None, None),
        )
        subtitle.bind(texture_size=subtitle.setter("size"))
        popup.add_widget(subtitle)

        self.add_widget(popup)


class OurAddressesScreen(Screen):
    view_mode = StringProperty("map")
    search_text = StringProperty("")

    _INITIAL_LOCATIONS: List[CafeLocation] = [
        CafeLocation("Куб Кофе — Арбат", "ул. Арбат, 12", 55.7522, 37.5928),
        CafeLocation("Куб Кофе — Тверская", "ул. Тверская, 18", 55.7647, 37.6055),
        CafeLocation("Куб Кофе — Белорусская", "площадь Тверская Застава, 2", 55.7722, 37.5822),
        CafeLocation("Куб Кофе — Курская", "ул. Земляной Вал, 33", 55.7579, 37.6670),
        CafeLocation("Куб Кофе — Савёловская", "ул. Бутырская, 10", 55.7921, 37.5824),
        CafeLocation("Куб Кофе — Павелецкая", "ул. Валовая, 11", 55.7312, 37.6384),
        CafeLocation("Куб Кофе — Сокол", "Ленинградский проспект, 76", 55.8046, 37.5166),
        CafeLocation("Куб Кофе — Маяковская", "1-я Тверская-Ямская ул., 2", 55.7700, 37.5978),
        CafeLocation("Куб Кофе — Красные Ворота", "ул. Мясницкая, 24/7", 55.7680, 37.6498),
        CafeLocation("Куб Кофе — Новокузнецкая", "ул. Пятницкая, 25", 55.7435, 37.6306),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._locations: List[CafeLocation] = list(self._INITIAL_LOCATIONS)
        self._visible_locations: List[CafeLocation] = list(self._locations)
        self._map_markers: List[CafeMarker] = []
        self._initialized = False

    # ------------------------------------------------------------------
    # Lifecycle management
    # ------------------------------------------------------------------
    def on_kv_post(self, base_widget) -> None:  # type: ignore[override]
        Clock.schedule_once(self._ensure_initialized, 0)

    def on_pre_enter(self, *args) -> None:  # type: ignore[override]
        Clock.schedule_once(self._ensure_initialized, 0)

    def _ensure_initialized(self, *_args) -> None:
        if self._initialized:
            self.apply_filters()
            self.on_view_mode(self, self.view_mode)
            return

        if "map_view" not in self.ids or "address_list" not in self.ids:
            return

        self._initialized = True
        self.apply_filters()
        self.on_view_mode(self, self.view_mode)

    # ------------------------------------------------------------------
    # View control
    # ------------------------------------------------------------------
    def on_toggle_state(self, mode: str, state: str) -> None:
        if state != "down" or mode == self.view_mode:
            return
        self.view_mode = mode

    def _sync_toggle_buttons(self) -> None:
        map_toggle = self.ids.get("map_toggle")
        list_toggle = self.ids.get("list_toggle")
        if map_toggle:
            map_toggle.state = "down" if self.view_mode == "map" else "normal"
        if list_toggle:
            list_toggle.state = "down" if self.view_mode == "list" else "normal"

    def on_view_mode(self, _instance, _value) -> None:
        self._sync_toggle_buttons()
        view_manager = self.ids.get("addresses_view_manager")
        if view_manager and view_manager.current != self.view_mode:
            view_manager.current = self.view_mode

    # ------------------------------------------------------------------
    # Search handling
    # ------------------------------------------------------------------
    def on_search_text(self, _instance, _value) -> None:  # type: ignore[override]
        self.apply_filters()

    def update_search(self, text: str) -> None:
        if self.search_text == text:
            return
        self.search_text = text

    def apply_filters(self) -> None:
        query = self.search_text.strip().lower()
        if not query:
            self._visible_locations = list(self._locations)
        else:
            self._visible_locations = [
                loc
                for loc in self._locations
                if query in loc.name.lower() or query in loc.address.lower()
            ]

        self._populate_map()
        self._populate_list()

    # ------------------------------------------------------------------
    # Map management
    # ------------------------------------------------------------------
    def _populate_map(self) -> None:
        map_view = self.ids.get("map_view")
        if not map_view:
            return

        for marker in self._map_markers:
            map_view.remove_marker(marker)
        self._map_markers.clear()

        if not self._visible_locations:
            return

        for location in self._visible_locations:
            marker = CafeMarker(location)
            marker.bind(on_release=lambda _marker, loc=location: self._focus_location(loc))
            map_view.add_marker(marker)
            self._map_markers.append(marker)

        primary = self._visible_locations[0]
        map_view.center_on(primary.latitude, primary.longitude)

    # ------------------------------------------------------------------
    # List management
    # ------------------------------------------------------------------
    def _populate_list(self) -> None:
        list_container = self.ids.get("address_list")
        if not list_container:
            return

        list_container.clear_widgets()

        if not self._visible_locations:
            list_container.add_widget(
                TwoLineListItem(
                    text="Ничего не найдено",
                    secondary_text="Измените поисковый запрос",
                )
            )
            return

        for location in self._visible_locations:
            item = TwoLineListItem(text=location.name, secondary_text=location.address)
            item.bind(on_release=lambda _item, loc=location: self._focus_location(loc))
            list_container.add_widget(item)

    def _focus_location(self, location: CafeLocation) -> None:
        map_view = self.ids.get("map_view")
        if not map_view:
            return

        self.view_mode = "map"
        map_view.center_on(location.latitude, location.longitude)
        map_view.zoom = max(map_view.zoom, 13)


