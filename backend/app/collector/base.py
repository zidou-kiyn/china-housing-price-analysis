"""数据采集抽象层：数据源基类、原始记录容器与注册表。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class CityInfo:
    """城市列表项。"""

    name: str
    code: str


@dataclass
class DistrictInfo:
    """区县列表项，code 跨城市复用，需配合 city_code 使用。"""

    name: str
    code: str
    city_code: str


@dataclass
class RawRecord:
    """一次采集的解析结果容器。records 为已归一化的行，raw_url 保留溯源地址。"""

    source: str
    city_code: str
    data_type: str
    records: list[dict] = field(default_factory=list)
    fetched_at: str = ""
    raw_url: str = ""


class BaseSource(ABC):
    """数据源适配器基类。每个数据源实现城市列表与均价时序的抓取。"""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """数据源标识，如 "creprice"。"""

    @abstractmethod
    def fetch_cities(self) -> list[CityInfo]:
        """抓取并返回去重后的城市列表。"""

    @abstractmethod
    def fetch_price_timeline(self, city_code: str, district_code: str = "allsq1") -> RawRecord:
        """抓取某城市（或区县）的均价时序。"""


class SourceRegistry:
    """数据源注册表：按名称登记数据源类，get() 返回实例。"""

    _registry: dict[str, type[BaseSource]] = {}

    @classmethod
    def register(cls, name: str, source: type[BaseSource]) -> None:
        cls._registry[name] = source

    @classmethod
    def get(cls, name: str) -> BaseSource:
        if name not in cls._registry:
            raise KeyError(f"未注册的数据源: {name}")
        return cls._registry[name]()

    @classmethod
    def names(cls) -> list[str]:
        return list(cls._registry)
