import pytest

from stackarr.media_folder_window import children, new_folder


def test_picker_lists_direct_directories_and_preserves_files(tmp_path):
    (tmp_path / "Movies").mkdir()
    (tmp_path / "a folder").mkdir()
    (tmp_path / ".private").mkdir()
    sentinel = tmp_path / "file.txt"
    sentinel.write_text("preserved")
    assert [path.name for path in children(tmp_path)] == ["a folder", "Movies"]
    assert sentinel.read_text() == "preserved"


@pytest.mark.parametrize("name", ["", ".", "..", "../escape", "C:/escape", "a\\b", "name.", " spaced ", "x\x00"])
def test_new_folder_cannot_escape_or_use_unsafe_names(tmp_path, name):
    with pytest.raises(ValueError):
        new_folder(tmp_path, name)
    assert list(tmp_path.iterdir()) == []


def test_new_folder_does_not_overwrite_an_existing_entry(tmp_path):
    folder = new_folder(tmp_path, "My media")
    sentinel = folder / "keep.txt"
    sentinel.write_text("preserved")
    with pytest.raises(FileExistsError):
        new_folder(tmp_path, "My media")
    assert sentinel.read_text() == "preserved"
