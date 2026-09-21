from pathlib import Path
from unittest.mock import MagicMock

from src.core.modifier import SystemModifier


MANIFEST_XML = """<manifest version="1.0" type="device">
    <hal format="aidl" override="true">
        <name>android.hardware.vibrator</name>
        <fqname>IVibrator/vibratorfeature</fqname>
    </hal>
</manifest>
"""

HOLDER_SMALI = """.class Lcom/android/server/vibrator/VibratorManagerServiceStub$Holder;
.super Ljava/lang/Object;

.field private static instance:Lcom/android/server/vibrator/VibratorManagerServiceStub;

.method static constructor <clinit>()V
    .locals 1

    const-class v0, Lcom/android/server/vibrator/VibratorManagerServiceStub;

    invoke-static {v0}, Lcom/miui/base/MiuiStubUtil;->getImpl(Ljava/lang/Class;)Ljava/lang/Object;

    move-result-object v0

    check-cast v0, Lcom/android/server/vibrator/VibratorManagerServiceStub;

    return-void
.end method
"""


def _modifier(tmp_path, android_version="17"):
    context = MagicMock()
    context.target_dir = tmp_path / "target"
    context.target_dir.mkdir()
    context.port.get_prop.return_value = android_version

    modifier = SystemModifier(context)
    modifier.temp_dir = tmp_path / "temp"
    modifier.temp_dir.mkdir()

    # Isolate from the rest of the pipeline for run()-level tests.
    for name in (
        "_replace_overlays", "_migrate_configs", "_relocate_pangu",
        "_fix_vndk_apex", "_copy_stock_apex", "_merge_mi_ext",
        "_fix_vintf_manifest", "_debloat_system", "_data_app_migration",
        "_install_custom_apps", "_integrate_gms",
    ):
        setattr(modifier, name, MagicMock())

    return modifier


def _make_odm(target_dir: Path, binary_payload: bytes | None = None) -> Path:
    odm = target_dir / "odm"
    manifest_dir = odm / "etc/vintf/manifest"
    bin_dir = odm / "bin/hw"
    manifest_dir.mkdir(parents=True)
    bin_dir.mkdir(parents=True)

    (manifest_dir / "vendor.xiaomi.hardware.vibratorfeature.service.xml").write_text(MANIFEST_XML)

    if binary_payload is None:
        binary_payload = b"\x7fELF" + b"pad" * 4 + b"/vibratorfeature\x00" + b"pad" * 4
    (bin_dir / "vendor.xiaomi.hardware.vibratorfeature.service").write_bytes(binary_payload)

    return odm


def test_vibrator_fix_only_runs_on_android_17(tmp_path):
    modifier = _modifier(tmp_path, android_version="16")
    _make_odm(modifier.ctx.target_dir)

    modifier.run()

    manifest = modifier.ctx.target_dir / "odm/etc/vintf/manifest/vendor.xiaomi.hardware.vibratorfeature.service.xml"
    assert "vibratorfeature" in manifest.read_text()


def test_vibrator_fix_runs_on_android_17(tmp_path):
    modifier = _modifier(tmp_path, android_version="17")
    odm = _make_odm(modifier.ctx.target_dir)

    modifier.run()

    manifest = modifier.ctx.target_dir / "odm/etc/vintf/manifest/vendor.xiaomi.hardware.vibratorfeature.service.xml"
    content = manifest.read_text()
    assert "IVibrator/default" in content
    assert "vibratorfeature" not in content

    binary = (odm / "bin/hw/vendor.xiaomi.hardware.vibratorfeature.service").read_bytes()
    assert b"/vibratorfeature" not in binary
    assert b"/default\x00" in binary


def test_binary_patch_preserves_length_and_swaps_string(tmp_path):
    modifier = _modifier(tmp_path, android_version="17")
    payload = b"\x7fELF" + b"junkjunk" + b"/vibratorfeature\x00" + (b"moarjunk" * 5)
    odm = _make_odm(modifier.ctx.target_dir, binary_payload=payload)

    modifier._patch_vibrator_vintf_manifest(odm)
    modifier._patch_vibrator_hal_binary(odm)

    patched = (odm / "bin/hw/vendor.xiaomi.hardware.vibratorfeature.service").read_bytes()
    assert len(patched) == len(payload)
    assert b"/vibratorfeature" not in patched
    assert b"/default\x00" in patched


def test_binary_patch_skips_when_string_not_found_exactly_once(tmp_path):
    modifier = _modifier(tmp_path, android_version="17")
    # No occurrence of the target string at all.
    odm = _make_odm(modifier.ctx.target_dir, binary_payload=b"\x7fELFnothinghere")

    modifier._patch_vibrator_hal_binary(odm)

    # File must be left completely untouched.
    assert (odm / "bin/hw/vendor.xiaomi.hardware.vibratorfeature.service").read_bytes() == b"\x7fELFnothinghere"


def test_manifest_and_binary_patch_skip_gracefully_when_missing(tmp_path):
    modifier = _modifier(tmp_path, android_version="17")
    odm = modifier.ctx.target_dir / "odm"
    odm.mkdir()

    # Should not raise even though nothing is there to patch.
    modifier._patch_vibrator_vintf_manifest(odm)
    modifier._patch_vibrator_hal_binary(odm)


def test_stub_patch_rewrites_holder_via_apkeditor(tmp_path):
    modifier = _modifier(tmp_path, android_version="17")
    target_dir = modifier.ctx.target_dir

    jar_path = target_dir / "system/framework/services.jar"
    jar_path.parent.mkdir(parents=True)
    jar_path.write_bytes(b"fake-jar-bytes")

    apkeditor_path = modifier.bin_dir / "APKEditor.jar"
    apkeditor_path.parent.mkdir(parents=True, exist_ok=True)
    if not apkeditor_path.exists():
        apkeditor_path.write_bytes(b"fake")

    smali_rel = Path("smali/com/android/server/vibrator/VibratorManagerServiceStub$Holder.smali")

    def fake_run_java_jar(jar, args, **kwargs):
        if args[0] == "d":
            work_dir = Path(args[args.index("-o") + 1])
            smali_path = work_dir / smali_rel
            smali_path.parent.mkdir(parents=True, exist_ok=True)
            smali_path.write_text(HOLDER_SMALI)
        elif args[0] == "b":
            work_dir = Path(args[args.index("-i") + 1])
            out_jar = Path(args[args.index("-o") + 1])
            # Simulate a rebuilt jar so callers can tell the "build" step ran.
            out_jar.write_bytes(b"rebuilt-jar:" + (work_dir / smali_rel).read_bytes())

    modifier.shell.run_java_jar = MagicMock(side_effect=fake_run_java_jar)

    modifier._patch_vibrator_manager_service_stub()

    assert (modifier.temp_dir / "services.jar.bak").read_bytes() == b"fake-jar-bytes"
    assert jar_path.read_bytes().startswith(b"rebuilt-jar:")

    rebuilt_smali = jar_path.read_bytes().decode()
    assert "invoke-static {v0}, Lcom/miui/base/MiuiStubUtil;->getImpl" not in rebuilt_smali
    assert "new-instance v0, Lcom/android/server/vibrator/VibratorManagerServiceStub;" in rebuilt_smali
    assert "invoke-direct {v0}, Lcom/android/server/vibrator/VibratorManagerServiceStub;-><init>()V" in rebuilt_smali
    assert "sput-object v0, Lcom/android/server/vibrator/VibratorManagerServiceStub$Holder;->instance:" in rebuilt_smali


def test_stub_patch_skipped_when_pattern_not_present(tmp_path):
    modifier = _modifier(tmp_path, android_version="17")
    target_dir = modifier.ctx.target_dir

    jar_path = target_dir / "system/framework/services.jar"
    jar_path.parent.mkdir(parents=True)
    jar_path.write_bytes(b"fake-jar-bytes")

    apkeditor_path = modifier.bin_dir / "APKEditor.jar"
    apkeditor_path.parent.mkdir(parents=True, exist_ok=True)
    if not apkeditor_path.exists():
        apkeditor_path.write_bytes(b"fake")

    smali_rel = Path("smali/com/android/server/vibrator/VibratorManagerServiceStub$Holder.smali")

    def fake_run_java_jar(jar, args, **kwargs):
        if args[0] == "d":
            work_dir = Path(args[args.index("-o") + 1])
            smali_path = work_dir / smali_rel
            smali_path.parent.mkdir(parents=True, exist_ok=True)
            # Already using a direct instantiation - nothing to patch.
            smali_path.write_text("new-instance v0, Lcom/android/server/vibrator/VibratorManagerServiceStub;\n")

    modifier.shell.run_java_jar = MagicMock(side_effect=fake_run_java_jar)

    modifier._patch_vibrator_manager_service_stub()

    # "b" (rebuild) should never have been requested, and the jar is untouched.
    build_calls = [c for c in modifier.shell.run_java_jar.call_args_list if c.args[1][0] == "b"]
    assert build_calls == []
    assert jar_path.read_bytes() == b"fake-jar-bytes"
