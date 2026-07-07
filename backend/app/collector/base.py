"""数据采集抽象层：数据源基类、原始记录容器与注册表。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class CityInfo:
    """城市列表项。"""

    name: str
    code: str
    province: str | None = None


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


class DataType:
    """采集数据类型 / 源能力标识。源通过 capabilities 声明自己支持哪些。"""

    CITIES = "cities"
    DISTRICTS = "districts"
    PRICE_TIMELINE = "price_timeline"
    PRICE_DISTRIBUTION = "price_distribution"


class BaseSource(ABC):
    """数据源适配器基类。每个数据源实现城市列表与均价时序的抓取。

    异构源通过类级 ``capabilities`` 声明支持的数据类型；编排层（PipelineRunner）
    按 ``supports()`` 跳过不支持的阶段，而非假设每个源都有区县 / 价格分布。
    """

    # 类级：默认最小能力（城市列表 + 城市级时序）。声明为类属性以便免实例化读取。
    capabilities: frozenset[str] = frozenset(
        {DataType.CITIES, DataType.PRICE_TIMELINE}
    )
    # 均价语义：¥/㎡（默认）vs 指数（政府源）。供前端/清洗区分，不做跨语义混算。
    price_unit: str = "cny_per_sqm"
    # 源站基址，取代 runner 里对具体源属性的硬取。
    base_url: str = ""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """数据源标识，如 "creprice"。"""

    @classmethod
    def supports(cls, data_type: str) -> bool:
        """该源是否支持某数据类型（能力）。"""
        return data_type in cls.capabilities

    @abstractmethod
    def fetch_cities(self) -> list[CityInfo]:
        """抓取并返回去重后的城市列表。"""

    @abstractmethod
    def fetch_price_timeline(self, city_code: str, district_code: str = "allsq1") -> RawRecord:
        """抓取某城市（或区县）的均价时序。"""

    # -- 可选能力：仅声明了对应 capability 的源才需覆盖 --------------------------------

    def fetch_districts(self, city_code: str | None = None) -> list[DistrictInfo]:
        """抓取区县列表。声明 DataType.DISTRICTS 的源必须覆盖。"""
        raise NotImplementedError(f"{self.source_name} 不支持区县采集")

    def fetch_price_distribution(
        self, city_code: str, district_code: str = "allsq1"
    ) -> RawRecord:
        """抓取价格区间分布。声明 DataType.PRICE_DISTRIBUTION 的源必须覆盖。"""
        raise NotImplementedError(f"{self.source_name} 不支持价格分布采集")


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
    def get_class(cls, name: str) -> type[BaseSource]:
        """返回源类（不实例化），供读取 capabilities/price_unit 而不新建 http 客户端。"""
        if name not in cls._registry:
            raise KeyError(f"未注册的数据源: {name}")
        return cls._registry[name]

    @classmethod
    def names(cls) -> list[str]:
        return list(cls._registry)
