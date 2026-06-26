"""Directory-browser backend tests. Fully offline, tmp_path only."""

from __future__ import annotations

from pathlib import Path

import pytest

from iron_jarvis.fsbrowser import (
    FsEntry,
    detect_project,
    drives,
    home,
    list_dir,
)


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A small tree: a git project subdir (with a file), a plain subdir, and a
    top-level hidden file."""
    root = tmp_path

    gitproj = root / "gitproj"
    gitproj.mkdir()
    (gitproj / ".git").mkdir()
    (gitproj / "main.py").write_text("print('hi')\n", encoding="utf-8")

    plain = root / "plain"
    plain.mkdir()

    (root / "readme.txt").write_text("hello world\n", encoding="utf-8")
    (root / ".secret").write_text("ssshh\n", encoding="utf-8")

    return root


# -- list_dir ---------------------------------------------------------------


def test_list_dir_basic_shape(tree: Path) -> None:
    result = list_dir(tree)
    assert result["path"] == str(tree.resolve())
    assert result["parent"] == str(tree.resolve().parent)
    names = [e["name"] for e in result["entries"]]
    # Both subdirs present; hidden .secret skipped by default.
    assert "gitproj" in names
    assert "plain" in names
    assert "readme.txt" in names
    assert ".secret" not in names


def test_list_dir_dirs_first_then_name(tree: Path) -> None:
    # Add another dir/file to exercise ordering within each group.
    (tree / "alpha").mkdir()
    (tree / "ZZZ.txt").write_text("z\n", encoding="utf-8")
    entries = list_dir(tree)["entries"]
    dir_flags = [e["is_dir"] for e in entries]
    # All directories come before all files.
    assert dir_flags == sorted(dir_flags, reverse=True)
    dir_names = [e["name"] for e in entries if e["is_dir"]]
    file_names = [e["name"] for e in entries if not e["is_dir"]]
    assert dir_names == sorted(dir_names, key=str.lower)
    assert file_names == sorted(file_names, key=str.lower)


def test_list_dir_marks_git_project(tree: Path) -> None:
    by_name = {e["name"]: e for e in list_dir(tree)["entries"]}
    assert by_name["gitproj"]["is_project"] == "git"
    assert by_name["gitproj"]["is_dir"] is True
    assert by_name["gitproj"]["size"] is None
    # A plain dir is not a project.
    assert by_name["plain"]["is_project"] is None


def test_list_dir_files_have_size(tree: Path) -> None:
    by_name = {e["name"]: e for e in list_dir(tree)["entries"]}
    entry = by_name["readme.txt"]
    assert entry["is_dir"] is False
    assert entry["is_project"] is None
    assert isinstance(entry["size"], int)
    assert entry["size"] == (tree / "readme.txt").stat().st_size


def test_list_dir_entry_paths_are_absolute(tree: Path) -> None:
    for e in list_dir(tree)["entries"]:
        assert Path(e["path"]).is_absolute()
        assert Path(e["path"]).name == e["name"]


def test_list_dir_show_hidden(tree: Path) -> None:
    names = [e["name"] for e in list_dir(tree, show_hidden=True)["entries"]]
    assert ".secret" in names


def test_list_dir_dirs_only(tree: Path) -> None:
    entries = list_dir(tree, dirs_only=True)["entries"]
    assert all(e["is_dir"] for e in entries)
    names = [e["name"] for e in entries]
    assert "readme.txt" not in names
    assert "gitproj" in names and "plain" in names


def test_list_dir_nested_single_level(tree: Path) -> None:
    # Listing a child only returns that child's contents, not recursive.
    result = list_dir(tree / "gitproj")
    names = {e["name"] for e in result["entries"]}
    assert names == {"main.py"}  # .git is hidden, skipped
    assert result["parent"] == str(tree.resolve())


def test_list_dir_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        list_dir(tmp_path / "does-not-exist")


def test_list_dir_on_file_raises(tree: Path) -> None:
    with pytest.raises(NotADirectoryError):
        list_dir(tree / "readme.txt")


def test_fsentry_dict_shape(tree: Path) -> None:
    entry: FsEntry = list_dir(tree)["entries"][0]
    assert set(entry.keys()) == {"name", "path", "is_dir", "is_project", "size"}


# -- detect_project ---------------------------------------------------------


@pytest.mark.parametrize(
    ("marker", "is_dir", "expected"),
    [
        (".git", True, "git"),
        ("pyproject.toml", False, "python"),
        ("package.json", False, "node"),
        ("Cargo.toml", False, "rust"),
        ("go.mod", False, "go"),
    ],
)
def test_detect_project_markers(
    tmp_path: Path, marker: str, is_dir: bool, expected: str
) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    target = proj / marker
    if is_dir:
        target.mkdir()
    else:
        target.write_text("x\n", encoding="utf-8")
    assert detect_project(proj) == expected


def test_detect_project_none(tmp_path: Path) -> None:
    assert detect_project(tmp_path) is None


def test_detect_project_priority(tmp_path: Path) -> None:
    # .git takes priority over pyproject.toml (checked first).
    (tmp_path / ".git").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert detect_project(tmp_path) == "git"


# -- drives / home ----------------------------------------------------------


def test_drives_nonempty_and_existing(tree: Path) -> None:
    result = drives()
    assert result, "drives() must return at least one root"
    for d in result:
        assert set(d.keys()) == {"path", "label"}
        assert Path(d["path"]).exists()


def test_home_exists() -> None:
    h = home()
    assert isinstance(h, str)
    assert Path(h).exists()
    assert Path(h) == Path.home()
