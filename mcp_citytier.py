#!/usr/bin/env python3
"""
城市分级查询 MCP Server
根据城市名称返回城市属于哪一线城市
使用 FastMCP 和 SSE 协议
"""

from fastmcp import FastMCP

# 城市分级数据 (基于2025新一线城市魅力排行榜)
CITY_TIERS = {
    # 一线城市（4个）
    "一线城市": ["上海", "北京", "深圳", "广州"],
    
    # 新一线城市（15个）
    "新一线城市": ["成都", "杭州", "重庆", "武汉", "苏州", "西安", "南京", "长沙", 
                "郑州", "天津", "合肥", "青岛", "东莞", "宁波", "佛山"],
    
    # 二线城市（30个）
    "二线城市": ["济南", "无锡", "沈阳", "昆明", "福州", "厦门", "温州", "石家庄", 
              "大连", "哈尔滨", "金华", "泉州", "南宁", "长春", "常州", "南昌", 
              "南通", "贵阳", "嘉兴", "徐州", "惠州", "太原", "烟台", "临沂", 
              "保定", "台州", "绍兴", "珠海", "洛阳", "潍坊"],
    
    # 三线城市（70个）
    "三线城市": ["乌鲁木齐", "兰州", "中山", "盐城", "海口", "扬州", "济宁", "湖州", 
              "赣州", "邯郸", "南阳", "唐山", "芜湖", "阜阳", "廊坊", "汕头", 
              "泰州", "呼和浩特", "镇江", "江门", "菏泽", "连云港", "沧州", "淄博", 
              "新乡", "周口", "襄阳", "淮安", "商丘", "桂林", "咸阳", "上饶", 
              "银川", "宿迁", "漳州", "遵义", "滁州", "绵阳", "宜昌", "威海", 
              "湛江", "九江", "邢台", "揭阳", "三亚", "衡阳", "信阳", "泰安", 
              "荆州", "肇庆", "蚌埠", "安阳", "安庆", "德州", "株洲", "莆田", 
              "聊城", "驻马店", "岳阳", "亳州", "柳州", "宜春", "宿州", "黄冈", 
              "六安", "常德", "宁德", "茂名", "马鞍山", "衢州"], 
   
    # 四线城市（90个）
    "四线城市": ["枣庄", "宜宾", "榆林", "开封", "邵阳", "运城", "清远", "吉安", 
              "日照", "许昌", "包头", "郴州", "滨州", "丽水", "宣城", "淮南", 
              "平顶山", "东营", "南充", "秦皇岛", "黄石", "鞍山", "晋中", "曲靖", 
              "孝感", "抚州", "宝鸡", "渭南", "舟山", "德阳", "衡水", "吉林", 
              "西宁", "龙岩", "焦作", "十堰", "濮阳", "潮州", "大庆", "湘潭", 
              "鄂尔多斯", "泸州", "长治", "怀化", "玉林", "大同", "梅州", "南平", 
              "黄山", "临汾", "赤峰", "恩施", "齐齐哈尔", "张家口", "阳江", "达州", 
              "乐山", "益阳", "汕尾", "大理", "永州", "红河", "北海", "河源", 
              "锦州", "毕节", "景德镇", "晋城", "凉山", "韶关", "三明", "黔东南", 
              "眉山", "承德", "铜陵", "荆门", "黔南", "淮北", "铜仁", "咸宁", 
              "营口", "娄底", "汉中", "玉溪", "喀什", "遂宁", "拉萨", "百色", 
              "天水", "吕梁"],
    
    # 五线城市（128个）
    "五线城市": ["忻州", "盘锦", "伊犁", "丹东", "延边", "酒泉", "阿克苏", "梧州", 
              "牡丹江", "池州", "葫芦岛", "佳木斯", "通化", "朝阳", "六盘水", "延安", 
              "内江", "自贡", "漯河", "新余", "西双版纳", "湘西", "黔西南", "张家界", 
              "昭通", "丽江", "贵港", "嘉峪关", "云浮", "钦州", "庆阳", "昌吉", 
              "随州", "安顺", "河池", "萍乡", "文山", "通辽", "辽阳", "鹰潭", 
              "鹤壁", "白银", "呼伦贝尔", "鄂州", "陇南", "抚顺", "普洱", "广安", 
              "广元", "三门峡", "楚雄", "贺州", "绥化", "阜新", "本溪", "铁岭", 
              "张掖", "雅安", "定西", "巴音郭楞", "保山", "德宏", "松原", "克拉玛依", 
              "巴中", "朔州", "攀枝花", "安康", "资阳", "四平", "金昌", "阳泉", 
              "商洛", "平凉", "防城港", "甘南", "白山", "乌兰察布", "临夏", "吴忠", 
              "辽源", "来宾", "武威", "海西", "锡林郭勒", "哈密", "崇左", "儋州", 
              "临沧", "白城", "甘孜", "鸡西", "中卫", "乌海", "巴彦淖尔", "和田", 
              "铜川", "阿坝", "兴安", "七台河", "石嘴山", "伊春", "博尔塔拉", "阿勒泰", 
              "双鸭山", "黑河", "林芝", "鹤岗", "固原", "塔城", "吐鲁番", "海东", 
              "大兴安岭", "阿拉善", "迪庆", "昌都", "怒江", "山南", "日喀则", "克孜勒苏", 
              "阿里", "那曲", "海南", "黄南", "果洛", "玉树", "海北", "三沙"]
}

# 创建城市到分级的映射
CITY_TO_TIER = {}
for tier, cities in CITY_TIERS.items():
    for city in cities:
        CITY_TO_TIER[city] = tier

# 创建 FastMCP 应用
mcp = FastMCP("城市分级查询")

@mcp.tool()
def get_city_tier(city_name: str) -> dict:
    """
    根据城市名称查询城市属于哪一线城市
    
    Args:
        city_name: 要查询的城市名称
    
    Returns:
        城市分级信息
    """
    city_name = city_name.strip()
    if not city_name:
        return {"success": False, "message": "请提供城市名称"}
    
    # 标准化城市名称（去掉"市"、"区"等后缀）
    normalized_name = city_name
    if city_name.endswith("市") or city_name.endswith("区"):
        normalized_name = city_name[:-1]
    
    # 查找城市分级（先尝试原始名称，再尝试标准化名称）
    tier = CITY_TO_TIER.get(city_name)
    if not tier and normalized_name != city_name:
        tier = CITY_TO_TIER.get(normalized_name)
    
    if tier:
        return {
            "success": True,
            "city": city_name,
            "tier": tier,
            "message": f"{city_name} 属于 {tier}"
        }
    else:
        # 尝试模糊匹配
        possible_matches = []
        for city in CITY_TO_TIER.keys():
            # 更宽松的匹配条件
            if (city_name in city or city in city_name or
                (normalized_name != city_name and (normalized_name in city or city in normalized_name))):
                possible_matches.append(city)
        
        if possible_matches:
            suggestions = "、".join(possible_matches[:5])
            return {
                "success": False,
                "city": city_name,
                "suggestions": possible_matches,
                "message": f"未找到城市 '{city_name}'，您是否想查询：{suggestions}？"
            }
        else:
            return {
                "success": False,
                "city": city_name,
                "message": f"未找到城市 '{city_name}'，请检查城市名称是否正确"
            }

@mcp.tool()
def list_cities_by_tier(tier: str) -> dict:
    """
    列出指定分级的所有城市
    
    Args:
        tier: 城市分级（一线城市、新一线城市、二线城市、三线城市、四线城市、五线城市）
    
    Returns:
        该分级的所有城市列表
    """
    tier = tier.strip()
    if tier not in CITY_TIERS:
        return {
            "success": False,
            "tier": tier,
            "message": f"无效的城市分级：{tier}。可选分级：一线城市、新一线城市、二线城市、三线城市、四线城市、五线城市"
        }
    
    cities = CITY_TIERS[tier]
    return {
        "success": True,
        "tier": tier,
        "count": len(cities),
        "cities": cities,
        "message": f"{tier}（{len(cities)}个）：{'、'.join(cities)}"
    }

@mcp.tool()
def get_all_tiers() -> dict:
    """
    获取所有城市分级的统计信息
    
    Returns:
        所有分级的统计信息
    """
    tiers_data = {}
    for tier, cities in CITY_TIERS.items():
        tiers_data[tier] = {
            "count": len(cities),
            "cities": cities
        }
    
    total_cities = sum(len(cities) for cities in CITY_TIERS.values())
    
    return {
        "success": True,
        "tiers": tiers_data,
        "total_cities": total_cities,
        "message": f"\n".join([f"{tier}：{len(cities)}个城市" for tier, cities in CITY_TIERS.items()]) + f"\n\n总计：{total_cities}个城市"
    }

@mcp.tool()
def search_cities(keyword: str) -> dict:
    """
    根据关键词搜索城市
    
    Args:
        keyword: 搜索关键词
    
    Returns:
        匹配的城市列表及其分级
    """
    keyword = keyword.strip()
    if not keyword:
        return {
            "success": False,
            "keyword": keyword,
            "message": "请提供搜索关键词"
        }
    
    matches = []
    for city, tier in CITY_TO_TIER.items():
        if keyword in city:
            matches.append({"city": city, "tier": tier})
    
    if matches:
        if len(matches) > 20:
            return {
                "success": True,
                "keyword": keyword,
                "count": len(matches),
                "matches": matches[:20],
                "truncated": True,
                "message": f"找到 {len(matches)} 个匹配城市，前20个：" + "、".join([f"{m['city']}({m['tier']})" for m in matches[:20]]) + "..."
            }
        else:
            return {
                "success": True,
                "keyword": keyword,
                "count": len(matches),
                "matches": matches,
                "truncated": False,
                "message": f"找到 {len(matches)} 个匹配城市：" + "、".join([f"{m['city']}({m['tier']})" for m in matches])
            }
    else:
        return {
            "success": False,
            "keyword": keyword,
            "message": f"未找到包含 '{keyword}' 的城市"
        }

if __name__ == "__main__":
    mcp.run(
        transport="sse",  # 使用 SSE 传输协议
        host="0.0.0.0",   # 监听所有 IP（默认可能是 127.0.0.1）
        port=8080,        # 修改端口（默认可能是 5000 或其他）
    )
    # mcp.run("stdio")