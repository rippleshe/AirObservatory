from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CityReference:
    location_id: int
    name: str
    province: str
    latitude: float
    longitude: float
    region: str


# Keep the first ten entries in their original order so existing location_id values stay stable.
CITY_CATALOG: tuple[CityReference, ...] = (
    CityReference(1, "北京", "北京", 39.9042, 116.4074, "华北"),
    CityReference(2, "上海", "上海", 31.2304, 121.4737, "华东"),
    CityReference(3, "广州", "广东", 23.1291, 113.2644, "华南"),
    CityReference(4, "深圳", "广东", 22.5431, 114.0579, "华南"),
    CityReference(5, "成都", "四川", 30.5728, 104.0668, "西南"),
    CityReference(6, "重庆", "重庆", 29.5630, 106.5516, "西南"),
    CityReference(7, "武汉", "湖北", 30.5928, 114.3055, "华中"),
    CityReference(8, "西安", "陕西", 34.3416, 108.9398, "西北"),
    CityReference(9, "杭州", "浙江", 30.2741, 120.1551, "华东"),
    CityReference(10, "南京", "江苏", 32.0603, 118.7969, "华东"),
    CityReference(11, "天津", "天津", 39.0842, 117.2009, "华北"),
    CityReference(12, "石家庄", "河北", 38.0428, 114.5149, "华北"),
    CityReference(13, "太原", "山西", 37.8706, 112.5489, "华北"),
    CityReference(14, "呼和浩特", "内蒙古", 40.8426, 111.7492, "华北"),
    CityReference(15, "沈阳", "辽宁", 41.8057, 123.4315, "东北"),
    CityReference(16, "大连", "辽宁", 38.9140, 121.6147, "东北"),
    CityReference(17, "长春", "吉林", 43.8171, 125.3235, "东北"),
    CityReference(18, "哈尔滨", "黑龙江", 45.8038, 126.5349, "东北"),
    CityReference(19, "济南", "山东", 36.6512, 117.1201, "华东"),
    CityReference(20, "青岛", "山东", 36.0671, 120.3826, "华东"),
    CityReference(21, "合肥", "安徽", 31.8206, 117.2272, "华东"),
    CityReference(22, "福州", "福建", 26.0745, 119.2965, "华东"),
    CityReference(23, "厦门", "福建", 24.4798, 118.0894, "华东"),
    CityReference(24, "南昌", "江西", 28.6829, 115.8579, "华东"),
    CityReference(25, "郑州", "河南", 34.7466, 113.6254, "华中"),
    CityReference(26, "长沙", "湖南", 28.2282, 112.9388, "华中"),
    CityReference(27, "南宁", "广西", 22.8170, 108.3665, "华南"),
    CityReference(28, "海口", "海南", 20.0440, 110.1999, "华南"),
    CityReference(29, "贵阳", "贵州", 26.6470, 106.6302, "西南"),
    CityReference(30, "昆明", "云南", 25.0389, 102.7183, "西南"),
    CityReference(31, "拉萨", "西藏", 29.6520, 91.1721, "西南"),
    CityReference(32, "兰州", "甘肃", 36.0611, 103.8343, "西北"),
    CityReference(33, "西宁", "青海", 36.6171, 101.7782, "西北"),
    CityReference(34, "银川", "宁夏", 38.4872, 106.2309, "西北"),
    CityReference(35, "乌鲁木齐", "新疆", 43.8256, 87.6168, "西北"),
    CityReference(36, "苏州", "江苏", 31.2989, 120.5853, "华东"),
    CityReference(37, "无锡", "江苏", 31.4912, 120.3119, "华东"),
    CityReference(38, "宁波", "浙江", 29.8683, 121.5440, "华东"),
    CityReference(39, "温州", "浙江", 27.9939, 120.6994, "华东"),
    CityReference(40, "佛山", "广东", 23.0215, 113.1214, "华南"),
    CityReference(41, "东莞", "广东", 23.0207, 113.7518, "华南"),
    CityReference(42, "珠海", "广东", 22.2710, 113.5767, "华南"),
    CityReference(43, "唐山", "河北", 39.6309, 118.1802, "华北"),
    CityReference(44, "保定", "河北", 38.8739, 115.4646, "华北"),
    CityReference(45, "徐州", "江苏", 34.2058, 117.2841, "华东"),
    CityReference(46, "南通", "江苏", 31.9802, 120.8943, "华东"),
    CityReference(47, "绍兴", "浙江", 30.0303, 120.5802, "华东"),
    CityReference(48, "嘉兴", "浙江", 30.7522, 120.7500, "华东"),
    CityReference(49, "洛阳", "河南", 34.6197, 112.4540, "华中"),
    CityReference(50, "宜昌", "湖北", 30.6919, 111.2865, "华中"),
    CityReference(51, "襄阳", "湖北", 32.0424, 112.1441, "华中"),
    CityReference(52, "株洲", "湖南", 27.8274, 113.1340, "华中"),
    CityReference(53, "惠州", "广东", 23.1115, 114.4152, "华南"),
    CityReference(54, "湛江", "广东", 21.2707, 110.3594, "华南"),
    CityReference(55, "桂林", "广西", 25.2736, 110.2900, "华南"),
    CityReference(56, "绵阳", "四川", 31.4675, 104.6796, "西南"),
    CityReference(57, "遵义", "贵州", 27.7257, 106.9274, "西南"),
    CityReference(58, "宝鸡", "陕西", 34.3619, 107.2373, "西北"),
    CityReference(59, "咸阳", "陕西", 34.3296, 108.7089, "西北"),
    CityReference(60, "克拉玛依", "新疆", 45.5799, 84.8892, "西北"),
)


def city_seed_rows() -> list[tuple[int, str, str, str, float, float]]:
    return [
        (
            city.location_id,
            city.name,
            city.name,
            city.province,
            city.latitude,
            city.longitude,
        )
        for city in CITY_CATALOG
    ]


def region_for(city_name: str) -> str | None:
    for city in CITY_CATALOG:
        if city.name == city_name:
            return city.region
    return None
