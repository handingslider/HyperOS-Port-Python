from pathlib import Path
import re
from .base import BaseModule

class ProvisionModule(BaseModule):
    def run(self, work_dir: Path):
        self.logger.info("Processing Provision.apk to enable GMS by default...")
        
        # 1. Search for setGmsAppEnabledStateForCn method
        target_file = None
        for f in work_dir.rglob("*.smali"):
            content = f.read_text(encoding='utf-8', errors='ignore')
            if "setGmsAppEnabledStateForCn" in content:
                target_file = f
                break
        
        if not target_file:
            self.logger.warning("setGmsAppEnabledStateForCn method not found in Provision.apk")
            return

        self.logger.info(f"Patching GMS enablement in {target_file.name}")
        
        # 2. Find IS_INTERNATIONAL_BUILD check and force it to true (const/4 vX, 0x1)
        content = target_file.read_text(encoding='utf-8', errors='ignore')
        
        # Regex to find: sget-boolean vX, Lmiui/os/Build;->IS_INTERNATIONAL_BUILD:Z
        # And inject const/4 vX, 0x1 immediately after
        pattern = r"(sget-boolean\s+([vp]\d+),\s+Lmiui/os/Build;->IS_INTERNATIONAL_BUILD:Z)"
        
        def replace_func(match):
            original_line = match.group(1)
            register = match.group(2)
            return f"{original_line}\n    const/4 {register}, 0x1"

        new_content = re.sub(pattern, replace_func, content)
        
        if new_content != content:
            target_file.write_text(new_content, encoding='utf-8')
            self.logger.info("Successfully patched Provision.apk for GMS enablement.")
        else:
            self.logger.warning("Could not find IS_INTERNATIONAL_BUILD check in target smali.")
