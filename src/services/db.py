import os
import sqlite3
from typing import Dict, Optional


DB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "user.db")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                name TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                spent_rub INTEGER NOT NULL DEFAULT 0,
                bonus INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # Ensure single row exists
        cur = conn.execute("SELECT COUNT(*) AS c FROM user_profile")
        if cur.fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO user_profile (id, name, phone, spent_rub, bonus) VALUES (1, '', '', 0, 0)"
            )
        conn.commit()
    finally:
        conn.close()


def get_user() -> Dict[str, object]:
    conn = _connect()
    try:
        row = conn.execute("SELECT name, phone, spent_rub, bonus FROM user_profile WHERE id = 1").fetchone()
        if not row:
            return {"name": "", "phone": "", "spent_rub": 0, "bonus": 0}
        return dict(row)
    finally:
        conn.close()


def update_user(name: Optional[str] = None, phone: Optional[str] = None) -> None:
    if name is None and phone is None:
        return
    sets = []
    params = []
    if name is not None:
        sets.append("name = ?")
        params.append(name)
    if phone is not None:
        sets.append("phone = ?")
        params.append(phone)
    params.append(1)
    conn = _connect()
    try:
        conn.execute(f"UPDATE user_profile SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
    finally:
        conn.close()


def add_spent(amount: int) -> None:
    conn = _connect()
    try:
        conn.execute("UPDATE user_profile SET spent_rub = spent_rub + ? WHERE id = 1", (int(amount),))
        conn.commit()
    finally:
        conn.close()


def add_bonus(points: int) -> None:
    conn = _connect()
    try:
        conn.execute("UPDATE user_profile SET bonus = bonus + ? WHERE id = 1", (int(points),))
        conn.commit()
    finally:
        conn.close()


def is_user_profile_completed() -> bool:
    """Проверяет, заполнены ли обязательные данные профиля."""
    user = get_user()
    return bool(user.get("name")) and bool(user.get("phone"))


