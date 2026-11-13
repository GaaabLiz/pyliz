"""Destructive path checks inspect lexical components before parent normalization."""

from pathlib import Path

import pytest

from pylizlib.core.os.paths.safety import assert_no_link_components


def test_component_check_allows_real_and_missing_paths_without_collapsing_parents(tmp_path):
    """Creation targets and ordinary parent components require no link traversal."""
    (tmp_path / "real/anchor").mkdir(parents=True)
    assert assert_no_link_components(tmp_path / "real/anchor/../missing/target") is None


@pytest.mark.parametrize("relative", [False, True])
def test_component_check_catches_a_link_before_parent_components(tmp_path, monkeypatch, relative):
    """A later '..' must not hide a linked lexical component from inspection."""
    (tmp_path / "real/anchor").mkdir(parents=True)
    (tmp_path / "route").mkdir()
    try:
        (tmp_path / "route/link").symlink_to(tmp_path / "real/anchor", target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"directory symlinks are unavailable: {error}")
    monkeypatch.chdir(tmp_path)
    path = Path("route/link/../data") if relative else tmp_path / "route/link/../data"
    with pytest.raises(ValueError, match="symbolic link or junction"):
        assert_no_link_components(path)


def test_component_check_rejects_a_dangling_leaf_link(tmp_path):
    """An absent target cannot hide a link at the destructive destination itself."""
    link = tmp_path / "dangling"
    try:
        link.symlink_to(tmp_path / "absent", target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"directory symlinks are unavailable: {error}")
    with pytest.raises(ValueError, match="symbolic link or junction"):
        assert_no_link_components(link)
