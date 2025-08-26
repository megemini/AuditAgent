#!/usr/bin/env python3
"""
城市分级查询 MCP Server (stdio版本)
根据城市名称返回城市属于哪一线城市
使用 FastMCP 和 stdio 协议
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
    "五线城市": ["阿坝", "阿克苏", "阿拉善", "阿勒泰", "安康", "安顺", "巴彦淖尔", "白城", 
              "白山", "白银", "百色", "蚌埠", "保山", "北海", "本溪", "毕节", 
              "滨州", "博尔塔拉", "沧州", "昌吉", "朝阳", "池州", "崇左", "楚雄", 
              "达州", "大理", "大庆", "大同", "大兴安岭", "丹东", "德宏", "德阳", 
              "定西", "东营", "鄂尔多斯", "鄂州", "恩施", "防城港", "佛山", "抚顺", 
              "抚州", "阜新", "甘南", "甘孜", "赣州", "固原", "广安", "广元", 
              "贵港", "桂林", "哈密", "海北", "海东", "海南", "海西", "邯郸", 
              "汉中", "鹤壁", "鹤岗", "河池", "河源", "贺州", "黑河", "衡水", 
              "红河", "呼伦贝尔", "湖州", "怀化", "淮北", "淮南", "淮安", "黄冈", 
              "黄南", "黄山", "黄石", "惠州", "鸡西", "吉安", "吉林", "济宁", 
              "佳木斯", "嘉峪关", "江门", "焦作", "揭阳", "金昌", "金华", "锦州", 
              "晋城", "晋中", "荆门", "荆州", "景德镇", "九江", "酒泉", "喀什", 
              "开封", "克拉玛依", "克孜勒苏", "昆明", "来宾", "莱芜", "廊坊", "乐山", 
              "丽江", "丽水", "连云港", "凉山", "辽阳", "辽源", "临沧", "临汾", 
              "临夏", "临沂", "柳州", "六安", "六盘水", "龙岩", "陇南", "娄底", 
              "泸州", "吕梁", "马鞍山", "茂名", "眉山", "梅州", "绵阳", "牡丹江"]
}

# 创建 FastMCP 应用
mcp = FastMCP("城市分级查询")

def find_city_tier(city_name: str) -> dict:
    """
    查找城市所属的分级
    
    Args:
        city_name: 城市名称
    
    Returns:
        包含城市分级信息的字典
    """
    # 去除可能的"市"字后缀
    clean_city_name = city_name.replace("市", "")
    
    for tier, cities in CITY_TIERS.items():
        if clean_city_name in cities:
            return {
                "success": True,
                "city": city_name,
                "tier": tier,
                "message": f"{city_name} 属于 {tier}"
            }
    
    # 对于不在 CITY_TIERS 中的城市，返回默认分级
    default_tier = "六线城市、地级市、县级市或其他"
    return {
        "success": True,
        "city": city_name,
        "tier": default_tier,
        "message": f"{city_name} 属于 {default_tier}"
    }

@mcp.tool()
def query_city_tier(city_name: str) -> dict:
    """
    查询城市分级
    
    Args:
        city_name: 要查询的城市名称
    
    Returns:
        城市分级查询结果
    """
    try:
        result = find_city_tier(city_name)
        return result
    except Exception as e:
        return {
            "success": False,
            "city": city_name,
            "tier": "错误",
            "message": f"查询城市分级时发生错误: {str(e)}"
        }

@mcp.tool()
def query_multiple_cities(city_list: list) -> dict:
    """
    批量查询多个城市的分级
    
    Args:
        city_list: 城市名称列表
    
    Returns:
        批量查询结果
    """
    try:
        results = []
        for city in city_list:
            result = find_city_tier(city)
            results.append(result)
        
        return {
            "success": True,
            "results": results,
            "message": f"成功查询了 {len(city_list)} 个城市的分级信息"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"批量查询城市分级时发生错误: {str(e)}"
        }

@mcp.tool()
def get_tier_cities(tier: str) -> dict:
    """
    获取指定分级的所有城市
    
    Args:
        tier: 城市分级（一线城市、新一线城市、二线城市、三线城市、四线城市、五线城市）
    
    Returns:
        指定分级的城市列表
    """
    try:
        if tier in CITY_TIERS:
            cities = CITY_TIERS[tier]
            return {
                "success": True,
                "tier": tier,
                "cities": cities,
                "count": len(cities),
                "message": f"{tier} 共有 {len(cities)} 个城市"
            }
        else:
            available_tiers = list(CITY_TIERS.keys())
            return {
                "success": False,
                "tier": tier,
                "message": f"未知的城市分级: {tier}。可用的分级有: {', '.join(available_tiers)}"
            }
    except Exception as e:
        return {
            "success": False,
            "tier": tier,
            "message": f"获取城市分级列表时发生错误: {str(e)}"
        }

if __name__ == "__main__":
    mcp.run(
        transport="stdio"  # 使用 stdio 传输协议
    )
