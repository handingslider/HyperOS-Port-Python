import os
import shutil
import time
import re
import logging
from pathlib import Path
from datetime import datetime, timezone

class PropertyModifier:
    def __init__(self, context):
        """
        :param context: PortingContext object
        """
        self.ctx = context
        self.logger = logging.getLogger("PropModifier")
        
        # Custom build info (can be passed from external parameters)
        self.build_user = os.getenv("BUILD_USER", "Bruce")
        self.build_host = os.getenv("BUILD_HOST", "HyperOS-Port")

    def run(self):
        """Execute all property modification logic"""
        self.logger.info("Starting build.prop modifications...")
        
        # 1. Global replacement (time, code, fingerprint, etc.)
        self._update_general_info()
        
        # 2. Screen density (DPI) migration
        self._update_density()
        
        # 3. Apply specific fixes (Millet, Blur, Cgroup)
        self._apply_specific_fixes()
        
        # 4. mi_ext prop migration
        self._migrate_mi_ext_props()
        
        self._apply_performance_props()
        
        self._regenerate_fingerprint()
        
        self.logger.info("Build.prop modifications completed.")

    def _update_general_info(self):
        """Corresponds to most logic in Shell script 'modifying build.prop'"""
        
        # Generate timestamp
        now = datetime.now(timezone.utc)
        build_date = now.strftime("%a %b %d %H:%M:%S UTC %Y")
        build_utc = str(int(now.timestamp()))
        
        base_code = self.ctx.stock_rom_code
        rom_version = self.ctx.target_rom_version
        
        self.logger.debug(f"General Info Update: BaseCode={base_code}, ROMVersion={rom_version}")
        
        # Key-value mapping to replace
        replacements = {
            "ro.build.date=": f"ro.build.date={build_date}",
            "ro.build.date.utc=": f"ro.build.date.utc={build_utc}",
            "ro.odm.build.date=": f"ro.odm.build.date={build_date}",
            "ro.odm.build.date.utc=": f"ro.odm.build.date.utc={build_utc}",
            "ro.vendor.build.date=": f"ro.vendor.build.date={build_date}",
            "ro.vendor.build.date.utc=": f"ro.vendor.build.date.utc={build_utc}",
            "ro.system.build.date=": f"ro.system.build.date={build_date}",
            "ro.system.build.date.utc=": f"ro.system.build.date.utc={build_utc}",
            "ro.product.build.date=": f"ro.product.build.date={build_date}",
            "ro.product.build.date.utc=": f"ro.product.build.date.utc={build_utc}",
            "ro.system_ext.build.date=": f"ro.system_ext.build.date={build_date}",
            "ro.system_ext.build.date.utc=": f"ro.system_ext.build.date.utc={build_utc}",
            
            # Device code replacement
            "ro.product.device=": f"ro.product.device={base_code}",
            "ro.product.product.name=": f"ro.product.product.name={base_code}",
            "ro.product.odm.device=": f"ro.product.odm.device={base_code}",
            "ro.product.vendor.device=": f"ro.product.vendor.device={base_code}",
            "ro.product.system.device=": f"ro.product.system.device={base_code}",
            "ro.product.board=": f"ro.product.board={base_code}",
            "ro.product.system_ext.device=": f"ro.product.system_ext.device={base_code}",
            "ro.mi.os.version.incremental=" : f"ro.mi.os.version.incremental={rom_version}",
            "ro.build.version.incremental=" : f"ro.build.version.incremental={rom_version}",
            "ro.product.build.version.incremental=" : f"ro.product.build.version.incremental={rom_version}",
            
            # Other misc
            "persist.sys.timezone=": "persist.sys.timezone=Asia/Shanghai",
            "ro.build.user=": f"ro.build.user={self.build_user}",
            "ro.miui.has_gmscore=": "ro.miui.has_gmscore=1",
        }

        # EU version check
        is_eu = getattr(self.ctx, "is_port_eu_rom", False)
        if is_eu:
            replacements["ro.product.mod_device="] = f"ro.product.mod_device={base_code}_xiaomieu_global"
            replacements["ro.build.host="] = "ro.build.host=xiaomi.eu"
        else:
            replacements["ro.product.mod_device="] = f"ro.product.mod_device={base_code}"
            replacements["ro.build.host="] = f"ro.build.host={self.build_host}"

        # Iterate all build.prop and modify
        for prop_file in self.ctx.target_dir.rglob("build.prop"):
            # [NEW] Skip mi_ext to preserve original port properties for migration source
            if "mi_ext" in str(prop_file.relative_to(self.ctx.target_dir)):
                self.logger.debug(f"Skipping global update for {prop_file.name} in mi_ext")
                continue

            lines = []
            with open(prop_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            new_lines = []
            file_changed = False
            for line in lines:
                original_line = line
                line = line.strip()
                
                # 1. Dictionary replacement logic
                replaced = False
                for prefix, new_val in replacements.items():
                    if line.startswith(prefix):
                        if original_line.strip() != new_val:
                            self.logger.debug(f"[{prop_file.name}] Replace: {line} -> {new_val}")
                            new_lines.append(new_val + "\n")
                            file_changed = True
                        else:
                             new_lines.append(original_line)
                        replaced = True
                        break
                if replaced: continue

                # 2. Delete logic
                if line.startswith("ro.miui.density.primaryscale="):
                    self.logger.debug(f"[{prop_file.name}] Remove: {line}")
                    file_changed = True
                    continue

                new_lines.append(original_line)
            
            # Write back file
            if file_changed:
                self.logger.debug(f"Writing changes to {prop_file.relative_to(self.ctx.target_dir)}")
                with open(prop_file, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)

    def _update_density(self):
        """Screen density modification"""
        self.logger.info("Updating screen density...")
        
        # 1. Get density from base
        base_density = None
        for part in ["product", "system"]:
            val = self.ctx.stock.get_prop("ro.sf.lcd_density")
            if val:
                base_density = val
                break
        
        if not base_density:
            if self.ctx.stock_rom_code == "duchamp":
                base_density = "480"
            else:
                base_density = "440"
            self.logger.warning(f"Base density not found, defaulting to {base_density}")
        else:
            if self.ctx.stock_rom_code == "duchamp":
                base_density = "480"
            self.logger.info(f"Found Base density: {base_density}")

        # 2. Modify porting package
        found_in_port = False
        target_props = list(self.ctx.target_dir.rglob("build.prop"))
        
        for prop_file in target_props:
            content = prop_file.read_text(encoding='utf-8', errors='ignore')
            new_content = content
            
            # Replace ro.sf.lcd_density
            if "ro.sf.lcd_density=" in content:
                self.logger.debug(f"[{prop_file.name}] Updating ro.sf.lcd_density to {base_density}")
                new_content = re.sub(r"ro\.sf\.lcd_density=.*", f"ro.sf.lcd_density={base_density}", new_content)
                found_in_port = True
            
            # Replace persist.miui.density_v2
            if "persist.miui.density_v2=" in content:
                 self.logger.debug(f"[{prop_file.name}] Updating persist.miui.density_v2 to {base_density}")
                 new_content = re.sub(r"persist\.miui\.density_v2=.*", f"persist.miui.density_v2={base_density}", new_content)
            
            if content != new_content:
                prop_file.write_text(new_content, encoding='utf-8')

        # 3. If not found, append to product/etc/build.prop
        if not found_in_port:
            product_prop = self.ctx.target_dir / "product/etc/build.prop"
            if product_prop.exists():
                with open(product_prop, "a", encoding='utf-8') as f:
                    f.write(f"\nro.sf.lcd_density={base_density}\n")
                    self.logger.info(f"Appended ro.sf.lcd_density={base_density} to {product_prop.relative_to(self.ctx.target_dir)}")
            else:
                self.logger.warning(f"Could not find product/etc/build.prop to append density.")

    def _apply_specific_fixes(self):
        """Device-specific fixes (Millet, Blur, Cgroup, etc.)"""
        self.logger.info("Applying device-specific fixes...")

        # --- 1. cust_erofs ---
        product_prop = self.ctx.target_dir / "product/etc/build.prop"
        if product_prop.exists():
            self._update_or_append_prop(product_prop, "ro.miui.cust_erofs", "0")

        # --- 2. Millet Fix ---
        millet_ver = self.ctx.stock.get_prop("ro.millet.netlink")
        if not millet_ver:
            self.logger.warning("ro.millet.netlink not found in base, defaulting to 29")
            millet_ver = "29"
        else:
            self.logger.debug(f"Found base millet version: {millet_ver}")
        
        self._update_or_append_prop(product_prop, "ro.millet.netlink", millet_ver)

        # --- 3. Blur Fix ---
        self._update_or_append_prop(product_prop, "persist.sys.background_blur_supported", "true")
        self._update_or_append_prop(product_prop, "persist.sys.background_blur_version", "2")

        # --- 4. Vendor Fixes (Cgroup) ---
        vendor_prop = self.ctx.target_dir / "vendor/build.prop"
        if vendor_prop.exists():
            content = vendor_prop.read_text(encoding='utf-8', errors='ignore')
            if "persist.sys.millet.cgroup1" in content and "#persist" not in content:
                self.logger.debug(f"[{vendor_prop.name}] Commenting out persist.sys.millet.cgroup1")
                content = content.replace("persist.sys.millet.cgroup1", "#persist.sys.millet.cgroup1")
                vendor_prop.write_text(content, encoding='utf-8')

    def _migrate_mi_ext_props(self):
        """Migrate specific properties from mi_ext to product build.prop as requested"""
        self.logger.info("Migrating mi_ext properties to product/etc/build.prop...")
        
        mi_ext_prop = self.ctx.target_dir / "mi_ext/etc/build.prop"
        product_prop = self.ctx.target_dir / "product/etc/build.prop"
        
        if not mi_ext_prop.exists() or not product_prop.exists():
            self.logger.warning("mi_ext or product build.prop not found, skipping property migration.")
            return
            
        mi_props_keys = [
            "ro.miui.support.system.app.uninstall.v2",
            "ro.mi.os.version.code",
            "ro.mi.os.version.name",
            "ro.mi.os.version.incremental"
        ]
        
        # Extract values from mi_ext
        extracted = {}
        try:
            content = mi_ext_prop.read_text(encoding='utf-8', errors='ignore')
            for key in mi_props_keys:
                match = re.search(f"^{re.escape(key)}=(.*)", content, re.MULTILINE)
                if match:
                    extracted[key] = match.group(1).strip()
        except Exception as e:
            self.logger.error(f"Failed to read mi_ext props: {e}")
            return
            
        # Apply to product
        if extracted:
            for key, value in extracted.items():
                self._update_or_append_prop(product_prop, key, value)
            self.logger.info(f"Successfully migrated {len(extracted)} properties from mi_ext.")

        # Aggressive Cleanup: Delete mi_ext source folder now that migration is complete
        # This ensures it's NOT packed into super.img/payload.bin
        mi_ext_dir = self.ctx.target_dir / "mi_ext"
        if mi_ext_dir.exists():
            self.logger.info("Aggressive Cleanup: Removing mi_ext directory after property migration.")
            shutil.rmtree(mi_ext_dir)

    def _update_or_append_prop(self, file_path: Path, key: str, value: str):
        """Helper function: update or append property"""
        if not file_path.exists(): return
        
        content = file_path.read_text(encoding='utf-8', errors='ignore')
        pattern = f"{re.escape(key)}=.*"
        replacement = f"{key}={value}"
        
        match = re.search(pattern, content)
        if match:
            if match.group(0) != replacement:
                self.logger.debug(f"[{file_path.name}] Update: {key} -> {value}")
                new_content = re.sub(pattern, replacement, content)
                file_path.write_text(new_content, encoding='utf-8')
        else:
            self.logger.debug(f"[{file_path.name}] Append: {key}={value}")
            new_content = content + f"\n{replacement}\n"
            file_path.write_text(new_content, encoding='utf-8')
    
    def _regenerate_fingerprint(self):
        """
        Regenerate ro.build.fingerprint and ro.build.description based on modified properties
        Format: Brand/Name/Device:Release/ID/Incremental:Type/Tags
        """
        self.logger.info("Regenerating build fingerprint...")

        def get_current_prop(key, default=""):
            # Priority: product -> system -> vendor
            for part in ["product", "system", "vendor","mi_ext"]:
                for prop_file in (self.ctx.target_dir / part).rglob("build.prop"):
                    try:
                        with open(prop_file, 'r', errors='ignore') as f:
                            for line in f:
                                if line.strip().startswith(f"{key}="):
                                    return line.split("=", 1)[1].strip()
                    except: pass
            return default

        # Read components
        brand = get_current_prop("ro.product.brand", "Xiaomi")
        name = get_current_prop("ro.product.mod_device")
        device = get_current_prop("ro.product.device", "miproduct")
        version = get_current_prop("ro.build.version.release")
        build_id = get_current_prop("ro.build.id")
        incremental = get_current_prop("ro.build.version.incremental")
        build_type = get_current_prop("ro.build.type", "user")
        tags = get_current_prop("ro.build.tags", "release-keys")

        self.logger.debug(f"Fingerprint components: Brand={brand}, Name={name}, Device={device}, Ver={version}, ID={build_id}, Inc={incremental}")

        # Construct Fingerprint
        new_fingerprint = f"{brand}/{name}/{device}:{version}/{build_id}/{incremental}:{build_type}/{tags}"
        self.logger.info(f"New Fingerprint: {new_fingerprint}")

        # Construct Description
        new_description = f"{name}-{build_type} {version} {build_id} {incremental} {tags}"
        self.logger.debug(f"New Description: {new_description}")

        # Write to all build.prop files
        replacements = {
            "ro.build.fingerprint=": f"ro.build.fingerprint={new_fingerprint}",
            "ro.bootimage.build.fingerprint=": f"ro.bootimage.build.fingerprint={new_fingerprint}",
            "ro.system.build.fingerprint=": f"ro.system.build.fingerprint={new_fingerprint}",
            "ro.product.build.fingerprint=": f"ro.product.build.fingerprint={new_fingerprint}",
            "ro.system_ext.build.fingerprint=": f"ro.system_ext.build.fingerprint={new_fingerprint}",
            "ro.vendor.build.fingerprint=": f"ro.vendor.build.fingerprint={new_fingerprint}",
            "ro.odm.build.fingerprint=": f"ro.odm.build.fingerprint={new_fingerprint}",
            
            "ro.build.description=": f"ro.build.description={new_description}",
            "ro.system.build.description=": f"ro.system.build.description={new_description}"
        }

        for prop_file in self.ctx.target_dir.rglob("build.prop"):
            lines = []
            try:
                with open(prop_file, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
            except: continue

            new_lines = []
            file_changed = False
            for line in lines:
                original = line
                line = line.strip()
                replaced = False
                for prefix, new_val in replacements.items():
                    if line.startswith(prefix):
                        if original.strip() != new_val:
                            new_lines.append(new_val + "\n")
                            file_changed = True
                        else:
                            new_lines.append(original)
                        replaced = True
                        break
                if not replaced:
                    new_lines.append(original)
            
            if file_changed:
                self.logger.debug(f"Updated fingerprint in {prop_file.relative_to(self.ctx.target_dir)}")
                with open(prop_file, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)    


    def _apply_performance_props(self):
        """Append a comprehensive list of performance, battery, and security properties to product/etc/build.prop"""
        self.logger.info("Applying performance and battery tuning properties...")
        
        prop_file = self.ctx.target_dir / "product" / "etc" / "build.prop"
        if not prop_file.exists():
            # Fallback to system/build.prop if product one doesn't exist
            prop_file = self.ctx.target_dir / "system" / "system" / "build.prop"
            if not prop_file.exists():
                prop_file = self.ctx.target_dir / "system" / "build.prop"
                if not prop_file.exists():
                    self.logger.warning("Target build.prop for performance tweaks not found.")
                    return

        props_to_add = [
            "\n# Performance, Battery, and Security Tuning",
            "ro.control_privapp_permissions=",
            "ro.miui.has_gmscore=1",
            "ro.boot.veritymode=enforcing",
            "ro.boot.verifiedbootstate=green",
            "vendor.boot.verifiedbootstate=green",
            "vendor.boot.vbmeta.device_state=locked",
            "ro.boot.vbmeta.device_state=locked",
            "ro.boot.flash.locked=1",
            "ro.secureboot.lockstate=locked",
            "vendor.boot.vbmeta.device_state=locked",
            "ro.boot.selinux=enforcing",
            "ro.build.tags=release-keys",
            "ro.boot.warranty_bit=0",
            "ro.vendor.boot.warranty_bit=0",
            "ro.vendor.warranty_bit=0",
            "ro.warranty_bit=0",
            "ro.is_ever_orange=0",
            "ro.build.type=user",
            "ro.debuggable=0",
            "ro.secure=1",
            "ro.crypto.state=encrypted",
            "ro.oem_unlock_supported=0",
            "androidboot.flash.locked=1",
            "\n# Dk",
            "ro.surface_flinger.use_content_detection_for_refresh_rate=true",
            "ro.surface_flinger.set_idle_timer_ms=2147483647",
            "ro.surface_flinger.set_touch_timer_ms=2147483647",
            "ro.surface_flinger.set_display_power_timer_ms=2147483647",
            "\n# Anim",
            "persist.sys.miui_animator_sched.bigcores=4-6",
            "persist.sys.miui_animator_sched.sched_threads=2",
            "persist.sys.miui.sf_cores=4-7",
            "persist.vendor.display.miui.composer_boost=4-7",
            "persist.sys.miui_animator_sched.big_prime_cores=4-7",
            "persist.sys.minfree_def=73728,92160,110592,154832,482560,579072",
            "persist.sys.minfree_6g=73728,92160,110592,258048,663552,903168",
            "persist.sys.minfree_8g=73728,92160,110592,387072,1105920,1451520",
            "persist.sys.first.frame.accelerates=true",
            "ro.miui.affinity.sfui=4-6",
            "ro.miui.affinity.sfre=4-6",
            "ro.miui.affinity.sfuireset=0-6",
            "persist.sys.power.default.powermode=1",
            "\n# RAMBOOST PROPS",
            "persist.vendor.sys.memplus.enable=true",
            "persist.sys.purgeable_assets=1",
            "persist.service.pcsync.enable=0",
            "persist.service.lgospd.enable=0",
            "\n# Better Scrolling",
            "ro.min_pointer_dur=8",
            "ro.max.fling_velocity=12000",
            "windowsmgr.max_events_per_sec=120",
            "\n# Improved performance",
            "debug.performance.tuning=1",
            "debug.mdpcomp.logs=0",
            "\n# ------------BATTERY-------------",
            "wifi.supplicant_scan_interval=180",
            "\n# Remain launcher in memory",
            "ro.HOME_APP_ADJ=1",
            "ro.HOME_APP_MEM=4096",
            "ro.FOREGROUND_APP_ADJ=0",
            "ro.VISIBLE_APP_ADJ=1",
            "ro.PERCEPTIBLE_APP_ADJ=2",
            "ro.HEAVY_WEIGHT_APP_ADJ=4",
            "ro.SECONDARY_SERVER_ADJ=5",
            "ro.BACKUP_APP_ADJ=6",
            "ro.HIDDEN_APP_MIN_ADJ=7",
            "ro.EMPTY_APP_ADJ=15",
            "ro.FOREGROUND_APP_MEM=128",
            "ro.VISIBLE_APP_MEM=256",
            "ro.PERCEPTIBLE_APP_MEM=384",
            "ro.HEAVY_WEIGHT_APP_MEM=64",
            "ro.SECONDARY_SERVER_MEM=768",
            "ro.BACKUP_APP_MEM=896",
            "ro.HIDDEN_APP_MEM=128",
            "ro.CONTENT_PROVIDER_MEM=1536",
            "ro.EMPTY_APP_MEM=2048",
            "\n# Disable vendor ram dumps",
            "persist.sys.ssr.enable_ramdumps=1",
            "\n# Disable DPM debugging",
            "persist.vendor.dpm.loglevel=0",
            "persist.vendor.dpmhalservice.loglevel=0",
            "\n# Increase GPU buffer count, does make rendering faster",
            "debug.egl.buffcount=4",
            "\n# Background process Limit",
            "ro.sys.fw.bg_apps_limit=10",
            "ro.sys.fw.use_trimming=1",
            "persist.sys.use_dithering=0",
            "\n# Enable ZRAM",
            "ro.config.zram=true",
            "ro.ril.power_collapse=1",
            "pm.sleep_mode=1",
            "wifi.supplicant_scan_interval=180",
            "ro.mot.eri.losalert.delay=1000",
            "ro.config.hw_quickpoweron=true",
            "\n# RAM",
            "persist.service.pcsync.enable=0",
            "persist.service.lgospd.enable=0",
            "\n# lmkd stuff ",
            "ro.lmk.debug=false",
            "persist.sys.lmk.reportkills=false",
            "sys.lmk.reportkills=false",
            "ro.lmk.log_stats=false",
            "\n# Art (thanks random dts)",
            "dalvik.vm.minidebuginfo=false",
            "dalvik.vm.dex2oat-minidebuginfo=false",
            "dalvik.vm.checkjni=false",
            "\n# all the battery stuff i could find that helped",
            "persist.radio.add_power_save=1",
            "ro.ril.power.collapse=1",
            "ro.ril.sensor.sleep.control=1",
            "pm.sleep_mode=1",
            "ro.ril.disable.power.collapse=0",
            "\n# Increase GPU buffer count, does make rendering faster",
            "debug.egl.buffcount=4",
            "\n# Optimize Network",
            "net.ipv4.tcp_sack=1",
            "net.ipv4.tcp_fack=1",
            "net.ipv4.tcp_no_metrics_save=1",
            "net.ipv4.icmp_echo_ignore_all=1",
            "net.ipv4.tcp_moderate_rcvbuf=1",
            "net.ipv4.conf.default.accept_redirects=0",
            "net.ipv4.conf.all.rp_filter=1",
            "persist.cust.tel.eons=1",
            "persist.cust.tel.adapt=1",
            "\n# Set Dalvik heap growth limit to 128MB",
            "dalvik.vm.heapgrowthlimit=128m",
            "\n# Set the maximum heap size to 256MB",
            "dalvik.vm.heapsize=256m",
            "\n# Enable JIT compiler for Dalvik dalvik.vm.execution-mode=int:jit",
            "# Increase the number of JIT compilation threads to 4",
            "dalvik.vm.jit-threads=4",
            "\n# Set the maximum bytecode verification depth to 10",
            "dalvik.vm.checkjni=false",
            "\n# Disable the inline optimization of method calls",
            "dalvik.vm.dexopt-flags=m=y",
            "\n# Qs lag fix",
            "dalvik.vm.image-dex2oat-threads=8",
            "dalvik.vm.image-dex2oat-filter=speed",
            "\n# Fast Reboot",
            "ro.config.hw_quickpoweron=true",
            "persist.sys.shutdown.mode=hibernate",
            "\n# Random",
            "dalvik.vm.heapminfree=2m",
            "dalvik.vm.heapmaxfree=8m"
        ]

        try:
            with open(prop_file, "a", encoding='utf-8') as f:
                f.write("\n".join(props_to_add) + "\n")
            self.logger.info(f"Successfully appended performance props to {prop_file.name}")
        except Exception as e:
            self.logger.error(f"Failed to append performance props: {e}")
