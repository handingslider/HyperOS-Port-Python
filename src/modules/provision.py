from pathlib import Path
import re
from .base import BaseModule

class ProvisionModule(BaseModule):
    def run(self, work_dir: Path):
        self.logger.info("Processing Provision.apk to enable GMS by default...")
        
        for matched_file in work_dir.rglob("*.smali"):
            content = matched_file.read_text(encoding='utf-8', errors='ignore')
            new_content = content
            file_changed = False
            
            # --- 1. Handle setGmsAppEnabledStateForCn (Enablement Logic) ---
            # In this method, IS_INTERNATIONAL_BUILD check is used to SKIP enablement.
            # We want to force it to 0 (False) so the logic proceeds.
            if "setGmsAppEnabledStateForCn" in new_content:
                self.logger.info(f"  Patching setGmsAppEnabledStateForCn in {matched_file.name}")
                # We target only the block of this method
                method_pattern = r"(\.method.*?setGmsAppEnabledStateForCn\(.*?.end method)"
                def patch_cn_gms(m):
                    block = m.group(1)
                    # Force register to 0 after sget-boolean
                    pattern = r"(sget-boolean\s+([vp]\d+),\s+Lmiui/os/Build;->IS_INTERNATIONAL_BUILD:Z)"
                    return re.sub(pattern, r"\1\n    const/4 \2, 0x0", block)
                
                new_content = re.sub(method_pattern, patch_cn_gms, new_content, flags=re.DOTALL)
                file_changed = True

            # --- 2. Handle GMS support visibility (Settings Toggles) ---
            # In these methods, we want to return true to show the toggle.
            methods = ["isGmsCoreSupport", "isGmsCoreInstalled"]
            for method in methods:
                 if f"{method}()Z" in new_content:
                    self.logger.info(f"  Forcing {method} to return true in {matched_file.name}")
                    # Look for simple boolean getters and force return true
                    simple_getter = rf"(\.method.*?{method}\(\)Z.*?)(return\s+([vp]\d+))(\s+\.end method)"
                    # Note: Using \3 for register and \2 for original return line
                    new_content = re.sub(simple_getter, r"\1const/4 \3, 0x1\n    \2\4", new_content, flags=re.DOTALL)
                    file_changed = True

            if file_changed and new_content != content:
                matched_file.write_text(new_content, encoding='utf-8')

        self.logger.info("Provision.apk patch completed.")
