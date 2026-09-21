import zipfile
from pathlib import Path
from unittest.mock import MagicMock

from src.core.modifier import SystemModifier


def _modifier(tmp_path):
    context = MagicMock()
    context.target_dir = tmp_path / "target"
    context.target_dir.mkdir()
    modifier = SystemModifier(context)
    modifier.temp_dir = tmp_path / "temp"
    modifier.temp_dir.mkdir()
    return modifier


def _make_phonesky_zip(path: Path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("___priv-app___Phonesky/Phonesky.apk", b"apk-bytes")
        z.writestr("___etc___permissions/com.android.vending.xml", b"<permissions/>")
        z.writestr("installer.sh", b"#!/sbin/sh\n# not part of the ROM")
        z.writestr("uninstaller.sh", b"#!/sbin/sh\n# not part of the ROM")


def _make_velvet_zip(path: Path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("___overlay/VelvetOverlay.apk", b"overlay-bytes")
        z.writestr("___priv-app___Velvet/Velvet.apk", b"velvet-bytes")
        z.writestr("___etc___permissions/Velvet.prop", b"")
        z.writestr("___etc___permissions/com.google.android.googlequicksearchbox.xml", b"<permissions/>")
        z.writestr("installer.sh", b"#!/sbin/sh")
        z.writestr("uninstaller.sh", b"#!/sbin/sh")


def test_extract_encoded_addon_zip_decodes_triple_underscore_paths(tmp_path):
    modifier = _modifier(tmp_path)
    zip_path = tmp_path / "phonesky.zip"
    _make_phonesky_zip(zip_path)

    extract_dir = tmp_path / "extracted"
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(extract_dir)

    product_root = tmp_path / "product"
    count = modifier._extract_encoded_addon_zip(extract_dir, product_root)

    assert count == 2  # apk + permissions xml; installer/uninstaller scripts are skipped
    assert (product_root / "priv-app/Phonesky/Phonesky.apk").read_bytes() == b"apk-bytes"
    assert (product_root / "etc/permissions/com.android.vending.xml").exists()
    assert not (product_root / "installer.sh").exists()
    assert not (product_root / "priv-app/Phonesky/installer.sh").exists()


def test_install_custom_apps_places_phonesky_correctly_from_zip(tmp_path, monkeypatch):
    modifier = _modifier(tmp_path)

    gapps_dir = tmp_path / "gapps"
    gapps_dir.mkdir()
    _make_phonesky_zip(gapps_dir / "phonesky.zip")
    _make_velvet_zip(gapps_dir / "velvet.zip")

    monkeypatch.chdir(tmp_path)
    modifier._install_custom_apps()

    product = modifier.ctx.target_dir / "product"

    phonesky_apk = product / "priv-app/Phonesky/Phonesky.apk"
    assert phonesky_apk.exists()
    assert phonesky_apk.read_bytes() == b"apk-bytes"
    assert (product / "etc/permissions/com.android.vending.xml").exists()

    # Regression check: the old fallback used to dump the raw zip contents
    # (including installer.sh and the ___-encoded folder itself) straight
    # into product/priv-app/Phonesky.
    assert not (product / "priv-app/Phonesky/installer.sh").exists()
    assert not (product / "priv-app/Phonesky/___priv-app___Phonesky").exists()

    velvet_apk = product / "priv-app/Velvet/Velvet.apk"
    assert velvet_apk.exists()
    assert (product / "overlay/VelvetOverlay.apk").exists()
    assert (product / "etc/permissions/com.google.android.googlequicksearchbox.xml").exists()
