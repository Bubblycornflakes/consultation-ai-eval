"""Is the machine short of memory? A run that starts while the Mac is swapping heavily can stall."""
import re
import subprocess

SWAP_WARN_FRACTION = 0.85


def parse_swap(text: str) -> dict | None:
    """Parse the output of `sysctl vm.swapusage`, for example
    'vm.swapusage: total = 8192.00M  used = 7639.94M  free = 552.06M  (encrypted)'."""
    m = re.search(r"total = ([\d.]+)M\s+used = ([\d.]+)M\s+free = ([\d.]+)M", text)
    if not m:
        return None
    total, used, free = (float(x) for x in m.groups())
    return {"total_mb": total, "used_mb": used, "free_mb": free, "used_fraction": used / total if total else 0.0}


def swap_status() -> dict | None:
    try:
        out = subprocess.run(["sysctl", "vm.swapusage"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_swap(out)


def memory_warning(status: dict | None) -> str | None:
    """A plain-words warning when swap is nearly full, otherwise None."""
    if not status or status["used_fraction"] < SWAP_WARN_FRACTION:
        return None
    return (f"WARNING: swap is {status['used_fraction']:.0%} full ({status['used_mb'] / 1024:.1f} of "
            f"{status['total_mb'] / 1024:.1f} GB). The model may stall and a conversation can run past the 3-minute "
            "limit. Quit heavy apps (browsers, simulators) and try again.")
