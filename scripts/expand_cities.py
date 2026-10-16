"""One-off catalog expansion with prefecture verification.

The Open-Meteo geocoder matches Chinese city names fuzzily (「鞍山」resolves to a
village in 重庆), so a candidate is accepted only when ``admin2`` — the prefecture —
is the city itself. Checking the province alone is not enough, and was actively
wrong: it let thirteen cities through in October 2026 with coordinates 115-686 km
away, every one of them in the right province and the wrong prefecture
(``backend/city_geocoding.csv`` carries the repairs, ``scripts/build_city_geography.py``
is what made them).

Hong Kong, Macao and Taiwan have no usable ``admin1``: they are queried *without*
``countryCode=CN`` and accepted by ``country_code`` (HK/MO/TW) instead, and their
Chinese names are not what the geocoder indexes — the pinyin form is.

Usage: uv run python -m scripts.expand_cities   # 打印复核表 + 写 data/_cities_new.csv
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request

REGION = {
    "北京": "华北", "天津": "华北", "河北": "华北", "山西": "华北", "内蒙古": "华北",
    "辽宁": "东北", "吉林": "东北", "黑龙江": "东北",
    "上海": "华东", "江苏": "华东", "浙江": "华东", "安徽": "华东",
    "福建": "华东", "江西": "华东", "山东": "华东", "台湾": "华东",
    "河南": "华中", "湖北": "华中", "湖南": "华中",
    "广东": "华南", "广西": "华南", "海南": "华南", "香港": "华南", "澳门": "华南",
    "重庆": "西南", "四川": "西南", "贵州": "西南", "云南": "西南", "西藏": "西南",
    "陕西": "西北", "甘肃": "西北", "青海": "西北", "宁夏": "西北", "新疆": "西北",
}

# Province-level units that cannot be checked by admin1: their country_code is what
# identifies them, and countryCode=CN has to come off the query or they are filtered
# out before the check runs.
SPECIAL_PROVINCES = {"香港": "HK", "澳门": "MO", "台湾": "TW"}

WANTED = [
    ("吉林", "吉林"), ("四平", "吉林"), ("佳木斯", "黑龙江"), ("绥化", "黑龙江"),
    ("鞍山", "辽宁"), ("抚顺", "辽宁"), ("锦州", "辽宁"), ("丹东", "辽宁"), ("营口", "辽宁"),
    ("大同", "山西"), ("长治", "山西"), ("运城", "山西"),
    ("鄂尔多斯", "内蒙古"), ("通辽", "内蒙古"), ("呼伦贝尔", "内蒙古"), ("乌兰察布", "内蒙古"),
    ("邢台", "河北"), ("沧州", "河北"), ("廊坊", "河北"), ("承德", "河北"),
    ("开封", "河南"), ("新乡", "河南"), ("许昌", "河南"), ("南阳", "河南"),
    ("商丘", "河南"), ("信阳", "河南"),
    ("泰安", "山东"), ("德州", "山东"), ("菏泽", "山东"),
    ("常州", "江苏"), ("扬州", "江苏"), ("泰州", "江苏"), ("淮安", "江苏"), ("连云港", "江苏"),
    ("湖州", "浙江"), ("衢州", "浙江"),
    ("马鞍山", "安徽"), ("安庆", "安徽"), ("阜阳", "安徽"),
    ("泉州", "福建"), ("漳州", "福建"), ("莆田", "福建"),
    ("宜春", "江西"), ("景德镇", "江西"), ("抚州", "江西"),
    ("荆州", "湖北"), ("荆门", "湖北"), ("咸宁", "湖北"),
    ("衡阳", "湖南"), ("湘潭", "湖南"), ("怀化", "湖南"),
    ("汕头", "广东"), ("江门", "广东"), ("肇庆", "广东"), ("揭阳", "广东"), ("清远", "广东"),
    ("梧州", "广西"), ("北海", "广西"), ("玉林", "广西"), ("百色", "广西"),
    ("泸州", "四川"), ("乐山", "四川"), ("达州", "四川"), ("雅安", "四川"),
    ("六盘水", "贵州"), ("安顺", "贵州"), ("铜仁", "贵州"),
    ("曲靖", "云南"), ("玉溪", "云南"), ("大理", "云南"), ("丽江", "云南"),
    ("日喀则", "西藏"), ("昌都", "西藏"), ("林芝", "西藏"),
    ("汉中", "陕西"), ("安康", "陕西"), ("铜川", "陕西"),
    ("酒泉", "甘肃"), ("武威", "甘肃"), ("平凉", "甘肃"), ("陇南", "甘肃"),
    ("海东", "青海"), ("格尔木", "青海"),
    ("石嘴山", "宁夏"), ("固原", "宁夏"),
    ("吐鲁番", "新疆"), ("哈密", "新疆"), ("阿克苏", "新疆"), ("库尔勒", "新疆"),
    ("伊宁", "新疆"), ("阿勒泰", "新疆"),
    # 港澳台：admin1 不可用，按 country_code 接收（见 SPECIAL_PROVINCES）
    ("香港", "香港"), ("澳门", "澳门"), ("台北", "台湾"), ("高雄", "台湾"),
]

SUFFIXES = ("市", "地区", "自治州", "盟", "省", "自治区", "壮族自治区", "回族自治区",
            "维吾尔自治区", "特别行政区")
CITY_FEATURES = ("PPLA", "PPLA2", "PPLA3", "PPLA4", "PPLC")

# The Chinese-name query misses these; OSM usually carries the pinyin form with
# a complete admin1, which is what the province check needs.
PINYIN = {
    "四平": "Siping", "鞍山": "Anshan", "锦州": "Jinzhou", "丹东": "Dandong",
    "营口": "Yingkou", "大同": "Datong", "长治": "Changzhi", "运城": "Yuncheng",
    "鄂尔多斯": "Ordos", "通辽": "Tongliao", "承德": "Chengde", "开封": "Kaifeng",
    "新乡": "Xinxiang", "许昌": "Xuchang", "商丘": "Shangqiu", "信阳": "Xinyang",
    "泰安": "Tai'an", "扬州": "Yangzhou", "淮安": "Huai'an", "连云港": "Lianyungang",
    "湖州": "Huzhou", "衢州": "Quzhou", "马鞍山": "Ma'anshan", "宜春": "Yichun",
    "景德镇": "Jingdezhen", "咸宁": "Xianning", "衡阳": "Hengyang", "百色": "Baise",
    "乐山": "Leshan", "六盘水": "Liupanshui", "铜仁": "Tongren", "曲靖": "Qujing",
    "日喀则": "Shigatse", "林芝": "Nyingchi", "汉中": "Hanzhong", "陇南": "Longnan",
    "海东": "Haidong", "格尔木": "Golmud", "石嘴山": "Shizuishan", "固原": "Guyuan",
    "吐鲁番": "Turpan", "哈密": "Hami", "伊宁": "Yining",
    "香港": "Hong Kong", "澳门": "Macau", "台北": "Taipei", "高雄": "Kaohsiung",
}


def strip_suffix(value: str) -> str:
    for suffix in SUFFIXES:
        if value.endswith(suffix) and len(value) > len(suffix):
            return value[: -len(suffix)]
    return value


def normalize_province(value: str) -> str:
    return (
        strip_suffix(value)
        .replace("壮族", "")
        .replace("回族", "")
        .replace("维吾尔", "")
        .replace("自治", "")
    )


def search(term: str, country: str | None = "CN") -> list[dict]:
    params = {"name": term, "count": 10, "language": "zh"}
    if country:
        params["countryCode"] = country
    query = urllib.parse.urlencode(params)
    url = f"https://geocoding-api.open-meteo.com/v1/search?{query}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                return json.loads(response.read().decode("utf-8")).get("results") or []
        except Exception:  # noqa: BLE001
            time.sleep(0.5 + attempt)
    return []


def verified(name: str, province: str) -> dict | None:
    """The city's own record, or None — refusing is the point of the recipe.

    A record has to name the city (in either script, so 吐鲁番县 counts and the
    pinyin-only "Siping" counts for 四平) *and* sit in the city's own prefecture. A
    seat-of-government record (``PPLA*``/``PPLC``) is preferred; several prefectures
    only have a plain ``PPL`` record for their urban core (四平市 is one), and those
    are the fallback once every other check has passed. 日喀则 has neither — only an
    airport record — so it is dropped rather than guessed.
    """
    country = SPECIAL_PROVINCES.get(province)
    pinyin = PINYIN.get(name)
    forms = [form for form in (name, pinyin) if form]
    terms = [pinyin, name, name + "市"] if country else [name, name + "市", pinyin]
    fallback = None
    for term in terms:
        if not term:
            continue
        for item in search(term, country=None if country else "CN"):
            if not any(form in item.get("name", "") for form in forms):
                continue
            if country:
                if item.get("country_code") != country:
                    continue
            else:
                if normalize_province(item.get("admin1", "")) != province:
                    continue
                # The prefecture has to be the city's own. A record named 德阳 whose
                # admin2 is 攀枝花市 is a village 557 km away, and the province check
                # waves it through; autonomous prefectures are why this is a
                # containment test rather than an equality one (大理 is 大理白族自治州).
                admin2 = item.get("admin2")
                if admin2 and not any(form in admin2 for form in forms):
                    continue
            if item.get("population", 0) < 50_000:
                continue
            if str(item.get("feature_code", "")).startswith(CITY_FEATURES):
                return item
            fallback = fallback or item
        time.sleep(0.12)
    return fallback


def main() -> None:
    accepted, rejected = [], []
    for name, province in WANTED:
        item = verified(name, province)
        if item is None:
            rejected.append(f"{name}({province})")
            continue
        accepted.append(
            (name, province, REGION[province], round(item["latitude"], 5),
             round(item["longitude"], 5), item["id"], int(item.get("population") or 0))
        )
        print(
            f"OK   {name:6} {province:5} {item['latitude']:8.4f} {item['longitude']:9.4f} "
            f"{item.get('feature_code'):6} {item.get('admin2') or item.get('country_code'):12} "
            f"人口 {(item.get('population') or 0):>9,}"
        )
    print(f"\n接受 {len(accepted)}，丢弃 {len(rejected)}：{' '.join(rejected)}", file=sys.stderr)
    with open("data/_cities_new.csv", "w", encoding="utf-8") as handle:
        for name, province, region, lat, lon, geoid, population in accepted:
            handle.write(f"{name},{province},{region},{lat},{lon},{geoid},{population}\n")


if __name__ == "__main__":
    main()
