__all__ = ["DesktopManager"]


def __getattr__(name):
    if name == "DesktopManager":
        from dctl.platform.manager import DesktopManager
        return DesktopManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

