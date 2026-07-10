from PIL import Image

from core.composer import resize_cover, resize_fit, set_opacity


def test_resize_fit_preserves_aspect_inside_canvas():
    img = Image.new("RGBA", (200, 100), (255, 0, 0, 255))
    resized = resize_fit(img, 100, 100)
    assert resized.size == (100, 50)


def test_resize_cover_preserves_aspect_and_crops_to_canvas():
    img = Image.new("RGBA", (200, 100), (255, 0, 0, 255))
    resized = resize_cover(img, 100, 100)
    assert resized.size == (100, 100)


def test_set_opacity_updates_alpha_channel():
    img = Image.new("RGBA", (2, 2), (10, 20, 30, 200))
    result = set_opacity(img, 0.5)
    assert result.getpixel((0, 0)) == (10, 20, 30, 100)


def test_set_opacity_clamps_values():
    img = Image.new("RGBA", (1, 1), (10, 20, 30, 128))
    assert set_opacity(img.copy(), 2.0).getpixel((0, 0))[3] == 128
    assert set_opacity(img.copy(), -1.0).getpixel((0, 0))[3] == 0
