"""Tests for desktop push notifications (mocked subprocess)."""
from __future__ import annotations

import json
import sqlite3
import threading
from unittest.mock import patch, MagicMock
import pytest
from services.storage.db import init_db
from services.notifications.desktop import (
    send_desktop_notification,
    notify_level_up,
    _notify_windows,
    _notify_macos,
    _notify_linux,
)


# ── unit tests for each OS helper ────────────────────────────────────────────

def test_notify_windows_calls_powershell():
    with patch("services.notifications.desktop.subprocess.run") as mock_run:
        _notify_windows("Level Up!", "You reached level 5!")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "powershell"
        script = args[-1]
        assert "Level Up!" in script
        assert "You reached level 5!" in script


def test_notify_macos_calls_osascript():
    with patch("services.notifications.desktop.subprocess.run") as mock_run:
        _notify_macos("Level Up!", "You reached level 3!")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "osascript"
        assert "Level Up!" in args[-1]
        assert "You reached level 3!" in args[-1]


def test_notify_linux_calls_notify_send():
    with patch("services.notifications.desktop.subprocess.run") as mock_run:
        _notify_linux("Level Up!", "Level 7 reached!")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "notify-send"
        assert "Level Up!" in args
        assert "Level 7 reached!" in args


def test_send_notification_silently_handles_errors():
    """Errors inside the notification helper must not propagate out of send_desktop_notification."""
    _real_thread = threading.Thread  # capture before patch
    threads_started: list[threading.Thread] = []

    def capturing_thread(target=None, daemon=None, **kwargs):
        t = _real_thread(target=target, daemon=daemon, **kwargs)
        threads_started.append(t)
        return t

    with patch("services.notifications.desktop.platform.system", return_value="Windows"), \
         patch("services.notifications.desktop._notify_windows", side_effect=FileNotFoundError), \
         patch("services.notifications.desktop.threading.Thread", side_effect=capturing_thread):
        send_desktop_notification("Title", "Msg")

    assert len(threads_started) == 1
    # Thread was already started by send_desktop_notification; wait for it to finish
    threads_started[0].join(timeout=2)
    assert not threads_started[0].is_alive()  # completed without hanging


# ── send_desktop_notification dispatches correctly ────────────────────────────

def test_send_dispatches_to_windows_on_windows():
    with patch("services.notifications.desktop.platform.system", return_value="Windows"), \
         patch("services.notifications.desktop._notify_windows") as mock_win:
        event = threading.Event()

        def set_event(title, message):
            event.set()

        mock_win.side_effect = set_event
        send_desktop_notification("T", "M")
        event.wait(timeout=2)
        mock_win.assert_called_once_with("T", "M")


def test_send_dispatches_to_macos():
    with patch("services.notifications.desktop.platform.system", return_value="Darwin"), \
         patch("services.notifications.desktop._notify_macos") as mock_mac:
        event = threading.Event()
        mock_mac.side_effect = lambda t, m: event.set()
        send_desktop_notification("T", "M")
        event.wait(timeout=2)
        mock_mac.assert_called_once_with("T", "M")


def test_send_dispatches_to_linux():
    with patch("services.notifications.desktop.platform.system", return_value="Linux"), \
         patch("services.notifications.desktop._notify_linux") as mock_lnx:
        event = threading.Event()
        mock_lnx.side_effect = lambda t, m: event.set()
        send_desktop_notification("T", "M")
        event.wait(timeout=2)
        mock_lnx.assert_called_once_with("T", "M")


def test_send_silently_ignores_unsupported_platform():
    with patch("services.notifications.desktop.platform.system", return_value="FreeBSD"):
        # Should not raise
        send_desktop_notification("T", "M")


# ── notify_level_up content ───────────────────────────────────────────────────

def test_notify_level_up_includes_level_number():
    with patch("services.notifications.desktop.send_desktop_notification") as mock_send:
        notify_level_up(12)
        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args if mock_send.call_args.kwargs else (mock_send.call_args.args, {})
        call_args = mock_send.call_args
        title = call_args[0][0] if call_args[0] else call_args.kwargs.get("title", "")
        message = call_args[0][1] if len(call_args[0]) > 1 else call_args.kwargs.get("message", "")
        assert "12" in title or "12" in message


# ── integration: agent fires notify_level_up on level-up ─────────────────────

@pytest.fixture
def agent_db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (visual,),
    )
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.commit()
    return conn


def test_agent_fires_notification_on_level_up(agent_db):
    """notify_level_up is called when XP pushes the player to the next level."""
    from services.sync_agent.agent import SyncAgent
    from services.sync_agent.tracker_client import TrackerClient
    from services.sync_agent.rate_limiter import RateLimiter
    from services.progression.config import XP_PER_LEVEL

    # Level 2 requires 100 XP; put player at 99 so any chunk causes level-up
    level_2_xp = XP_PER_LEVEL[1]  # 100
    agent_db.execute(
        "INSERT OR REPLACE INTO player_category_xp (character_id, category, xp) VALUES (?, ?, ?)",
        ("player_default", "WORK", level_2_xp - 1),
    )
    agent_db.commit()

    # Seed one item definition so drops work
    agent_db.execute(
        "INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
        ("scroll", json.dumps({
            "item_id": "scroll", "name": "Scroll", "rarity": "COMMON",
            "category": "WORK", "icon": "", "effects": [], "description": "",
            "drop_requirement": {},
        })),
    )
    agent_db.commit()

    mock_client = MagicMock(spec=TrackerClient)
    mock_client.fetch_chunks.return_value = (
        [{
            "chunk_id": "c_test",
            "started_at": "2026-01-01T10:00:00+00:00",
            "duration_sec": 120,
            "label": "WORK",
            "confidence": 0.9,
            "time_of_day": "morning",
        }],
        "cursor_1",
    )

    agent = SyncAgent(
        db=agent_db,
        tracker_client=mock_client,
        character_id="player_default",
        rate_limiter=RateLimiter(cooldown_sec=0),
    )

    with patch("services.sync_agent.agent.notify_level_up") as mock_notify:
        from services.sync_agent.agent import PollResult
        result = agent.poll(manual=True)
        assert result == PollResult.OK
        # notify_level_up should have been called at least once
        assert mock_notify.call_count >= 1
        called_levels = [c.args[0] for c in mock_notify.call_args_list]
        assert all(lvl >= 2 for lvl in called_levels)
