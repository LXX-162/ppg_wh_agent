from pydantic import BaseModel, Field
from typing import Optional

class OrderData(BaseModel):
    """
    定义的订单数据 Schema，仅包含需要同步至飞书多维表的必填字段和含有默认值的字段。
    """
    客户名: str = Field(..., description="客户名 (如 芜湖PPG / PPG修补漆)")
    单号: str = Field(..., description="唯一标识 (如 11226109)")
    订单状态: str = Field(default="正常", description="单选（正常/已取消）")
    下单日期: str = Field(..., description="下单日期 (如 2024-12-01 00:00:00)")
    收货单位: str = Field(..., description="收货单位 (如 柳州库)")
    收货地址: str = Field(..., description="收货地址")
    收货人: str = Field(..., description="收货人 (如 陈芸 -13807726654)")
    数量: int = Field(..., description="数量")
    重量: float = Field(..., description="重量")
    发运方式: str = Field(default="零担", description="单选: 零担/包车/保温车/自提")
    始发城市: str = Field(..., description="始发城市")
    到货城市: str = Field(..., description="到货城市")
    到货省份: str = Field(..., description="到货省份")
    产品特性: str = Field(default="DG", description="单选: DG / NDG")
    承运商: str = Field(..., description="承运商")
