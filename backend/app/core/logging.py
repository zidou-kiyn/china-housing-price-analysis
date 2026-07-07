"""统一日志配置：时间/级别/模块名格式，级别由 settings.log_level 控制。"""

import logging

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_CONFIGURED_FLAG = "_housing_price_configured"


def setup_logging(level: str = "INFO") -> None:
    """初始化根 logger；幂等，重复调用不叠加 handler。"""
    root = logging.getLogger()
    root.setLevel(level.upper())
    if getattr(root, _CONFIGURED_FLAG, False):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(handler)
    setattr(root, _CONFIGURED_FLAG, True)
