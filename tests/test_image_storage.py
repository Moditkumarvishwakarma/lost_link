from io import BytesIO

import pytest
from PIL import Image

import image_storage


def make_png() -> bytes:
    image = Image.new("RGB", (2, 2), color="teal")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_saved_image_is_persisted_and_resolvable(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(image_storage, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(image_storage, "PROJECT_DIR", tmp_path)

    relative_path = image_storage.save_uploaded_image(make_png())

    saved_path = image_storage.get_uploaded_image_path(relative_path)
    assert saved_path is not None
    assert saved_path.is_file()
    assert saved_path.parent == uploads


def test_invalid_image_is_rejected():
    with pytest.raises(ValueError, match="valid PNG or JPEG"):
        image_storage.save_uploaded_image(b"not an image")


def test_image_path_cannot_escape_upload_directory(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    outside_file = tmp_path / "private.txt"
    outside_file.write_text("private")
    monkeypatch.setattr(image_storage, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(image_storage, "PROJECT_DIR", tmp_path)

    assert image_storage.get_uploaded_image_path("private.txt") is None
