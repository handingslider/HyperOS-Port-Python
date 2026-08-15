from pathlib import Path
from unittest.mock import MagicMock

from src.core.modifier import SystemModifier


def _modifier(tmp_path, is_cn):
    context = MagicMock()
    context.target_dir = tmp_path / "target"
    context.target_dir.mkdir()
    context.port.get_prop.return_value = "14"
    context.is_cn = is_cn
    modifier = SystemModifier(context)
    for name in (
        "_replace_overlays", "_migrate_configs", "_relocate_pangu",
        "_fix_vndk_apex", "_copy_stock_apex", "_merge_mi_ext",
        "_fix_vintf_manifest", "_debloat_system", "_data_app_migration",
        "_install_custom_apps",
    ):
        setattr(modifier, name, MagicMock())
    modifier._integrate_gms = MagicMock()
    return modifier


def test_non_cn_build_does_not_add_gms_packages(tmp_path):
    modifier = _modifier(tmp_path, False)
    modifier.run()
    modifier._integrate_gms.assert_not_called()


def test_cn_build_adds_gms_packages(tmp_path):
    modifier = _modifier(tmp_path, True)
    modifier.run()
    modifier._integrate_gms.assert_called_once_with()


def test_workflow_downloads_default_packages_only_for_cn():
    workflow = Path(".github/workflows/port.yml").read_text(encoding="utf-8")
    assert "gms_phonesky_url:" not in workflow
    assert "gms_velvet_url:" not in workflow
    assert "if: ${{ inputs.cn }}" in workflow
    assert "PHONESKY_URL:" in workflow and "phonesky.zip" in workflow
    assert "VELVET_URL:" in workflow and "velvet.zip" in workflow
    assert "--cn" in workflow
