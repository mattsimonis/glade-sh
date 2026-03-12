"""
test_utils.py — Unit tests for pure utility functions: slugify and strip_ansi.

These functions are used in security-sensitive paths (clone directory names,
log search output) so correctness matters beyond the obvious cases.
"""

import api


# ══════════════════════════════════════════════════════════════════════════════
# slugify
# ══════════════════════════════════════════════════════════════════════════════


def test_slugify_lowercases():
    assert api.slugify("MyRepo") == "myrepo"


def test_slugify_replaces_spaces_with_dashes():
    assert api.slugify("my cool repo") == "my-cool-repo"


def test_slugify_replaces_special_chars_with_single_dash():
    assert api.slugify("hello!@#world") == "hello-world"


def test_slugify_collapses_multiple_separators():
    assert api.slugify("a---b___c") == "a-b-c"


def test_slugify_strips_leading_trailing_dashes():
    assert api.slugify("---repo---") == "repo"


def test_slugify_all_special_chars_returns_unnamed():
    assert api.slugify("!@#$%") == "unnamed"


def test_slugify_empty_string_returns_unnamed():
    assert api.slugify("") == "unnamed"


def test_slugify_only_whitespace_returns_unnamed():
    assert api.slugify("   ") == "unnamed"


def test_slugify_already_clean_name_unchanged():
    assert api.slugify("my-repo") == "my-repo"


def test_slugify_dots_become_dashes():
    assert api.slugify("my.project.name") == "my-project-name"


def test_slugify_numbers_preserved():
    assert api.slugify("repo2025") == "repo2025"


def test_slugify_mixed_case_numbers_and_hyphens():
    assert api.slugify("My-Repo-123") == "my-repo-123"


def test_slugify_unicode_collapses_to_dash():
    # Non-ASCII chars are not [a-z0-9], so they become dashes
    result = api.slugify("héllo-wörld")
    assert result == "h-llo-w-rld"


def test_slugify_slash_in_github_repo_name():
    # github_repo is "owner/name"; the caller splits on "/" first —
    # but slugify of the full string should still produce something safe
    assert api.slugify("owner/repo-name") == "owner-repo-name"


# ══════════════════════════════════════════════════════════════════════════════
# strip_ansi
# ══════════════════════════════════════════════════════════════════════════════


def test_strip_ansi_plain_text_unchanged():
    assert api.strip_ansi("hello world") == "hello world"


def test_strip_ansi_removes_sgr_reset():
    assert api.strip_ansi("\x1b[0mhello") == "hello"


def test_strip_ansi_removes_bold():
    assert api.strip_ansi("\x1b[1mbold\x1b[0m") == "bold"


def test_strip_ansi_removes_256_color():
    assert api.strip_ansi("\x1b[38;5;196mred\x1b[0m") == "red"


def test_strip_ansi_removes_truecolor():
    assert api.strip_ansi("\x1b[38;2;255;100;0mcolor\x1b[0m") == "color"


def test_strip_ansi_removes_cursor_movement():
    assert api.strip_ansi("\x1b[2A\x1b[3Chello") == "hello"


def test_strip_ansi_removes_erase_line():
    assert api.strip_ansi("hello\x1b[2K world") == "hello world"


def test_strip_ansi_removes_osc_title_sequence():
    # OSC: ESC ] ... BEL
    assert api.strip_ansi("\x1b]0;My Title\x07hello") == "hello"


def test_strip_ansi_removes_osc_with_st_terminator():
    # OSC terminated by ESC \
    assert api.strip_ansi("\x1b]0;title\x1b\\hello") == "hello"


def test_strip_ansi_removes_c0_control_chars():
    # \x0e (shift-out), \x0f (shift-in) should be stripped
    assert api.strip_ansi("\x0ehello\x0f") == "hello"


def test_strip_ansi_preserves_newlines_and_tabs():
    # \n and \t are NOT in the strip range (\x00-\x08, \x0e-\x1f)
    assert api.strip_ansi("line1\nline2\ttabbed") == "line1\nline2\ttabbed"


def test_strip_ansi_nested_sequences():
    text = "\x1b[1m\x1b[32mGreen Bold\x1b[0m normal"
    assert api.strip_ansi(text) == "Green Bold normal"


def test_strip_ansi_empty_string():
    assert api.strip_ansi("") == ""


def test_strip_ansi_only_escape_sequences_returns_empty():
    assert api.strip_ansi("\x1b[0m\x1b[1m\x1b[32m") == ""
