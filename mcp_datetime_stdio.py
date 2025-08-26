#!/usr/bin/env python3
"""
日期时间查询 MCP Server (stdio版本)
提供当前日期、时间、日期时间等功能
使用 FastMCP 和 stdio 协议
"""

from fastmcp import FastMCP
from datetime import datetime, date, time, timedelta
import pytz

# 创建 FastMCP 应用
mcp = FastMCP("日期时间查询")

@mcp.tool()
def get_current_date() -> dict:
    """
    获取当前日期
    
    Returns:
        当前日期信息
    """
    try:
        today = date.today()
        return {
            "success": True,
            "date": today.isoformat(),
            "year": today.year,
            "month": today.month,
            "day": today.day,
            "weekday": today.weekday(),  # 0=Monday, 6=Sunday
            "weekday_name": today.strftime("%A"),
            "message": f"当前日期: {today.strftime('%Y年%m月%d日')}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"获取当前日期时发生错误: {str(e)}"
        }

@mcp.tool()
def get_current_time() -> dict:
    """
    获取当前时间
    
    Returns:
        当前时间信息
    """
    try:
        now = datetime.now()
        return {
            "success": True,
            "time": now.time().isoformat(),
            "hour": now.hour,
            "minute": now.minute,
            "second": now.second,
            "microsecond": now.microsecond,
            "message": f"当前时间: {now.strftime('%H时%M分%S秒')}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"获取当前时间时发生错误: {str(e)}"
        }

@mcp.tool()
def get_current_datetime() -> dict:
    """
    获取当前日期时间
    
    Returns:
        当前日期时间信息
    """
    try:
        now = datetime.now()
        return {
            "success": True,
            "datetime": now.isoformat(),
            "date": now.date().isoformat(),
            "time": now.time().isoformat(),
            "year": now.year,
            "month": now.month,
            "day": now.day,
            "hour": now.hour,
            "minute": now.minute,
            "second": now.second,
            "weekday": now.weekday(),
            "weekday_name": now.strftime("%A"),
            "formatted": now.strftime('%Y年%m月%d日 %H时%M分%S秒'),
            "message": f"当前日期时间: {now.strftime('%Y年%m月%d日 %H时%M分%S秒')}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"获取当前日期时间时发生错误: {str(e)}"
        }

@mcp.tool()
def get_datetime_by_timezone(timezone: str) -> dict:
    """
    获取指定时区的当前日期时间
    
    Args:
        timezone: 时区名称 (如: 'Asia/Shanghai', 'UTC', 'America/New_York')
    
    Returns:
        指定时区的日期时间信息
    """
    try:
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        return {
            "success": True,
            "timezone": timezone,
            "datetime": now.isoformat(),
            "date": now.date().isoformat(),
            "time": now.time().isoformat(),
            "year": now.year,
            "month": now.month,
            "day": now.day,
            "hour": now.hour,
            "minute": now.minute,
            "second": now.second,
            "weekday": now.weekday(),
            "weekday_name": now.strftime("%A"),
            "formatted": now.strftime('%Y年%m月%d日 %H时%M分%S秒'),
            "message": f"{timezone} 时区的当前日期时间: {now.strftime('%Y年%m月%d日 %H时%M分%S秒')}"
        }
    except Exception as e:
        return {
            "success": False,
            "timezone": timezone,
            "message": f"获取时区 {timezone} 的日期时间时发生错误: {str(e)}"
        }

@mcp.tool()
def format_datetime(datetime_str: str, format_str: str) -> dict:
    """
    格式化日期时间字符串
    
    Args:
        datetime_str: 日期时间字符串
        format_str: 格式化字符串 (如: '%Y年%m月%d日 %H时%M分%S秒')
    
    Returns:
        格式化后的日期时间
    """
    try:
        # 尝试解析日期时间字符串
        dt = datetime.fromisoformat(datetime_str)
        formatted = dt.strftime(format_str)
        return {
            "success": True,
            "original": datetime_str,
            "formatted": formatted,
            "format": format_str,
            "message": f"格式化结果: {formatted}"
        }
    except Exception as e:
        return {
            "success": False,
            "original": datetime_str,
            "format": format_str,
            "message": f"格式化日期时间时发生错误: {str(e)}"
        }

@mcp.tool()
def calculate_date_difference(date1: str, date2: str) -> dict:
    """
    计算两个日期之间的差值
    
    Args:
        date1: 第一个日期 (YYYY-MM-DD)
        date2: 第二个日期 (YYYY-MM-DD)
    
    Returns:
        日期差值信息
    """
    try:
        d1 = date.fromisoformat(date1)
        d2 = date.fromisoformat(date2)
        delta = abs(d2 - d1)
        
        return {
            "success": True,
            "date1": date1,
            "date2": date2,
            "days_difference": delta.days,
            "weeks_difference": delta.days // 7,
            "years_difference": delta.days // 365,
            "message": f"{date1} 和 {date2} 相差 {delta.days} 天"
        }
    except Exception as e:
        return {
            "success": False,
            "date1": date1,
            "date2": date2,
            "message": f"计算日期差值时发生错误: {str(e)}"
        }

@mcp.tool()
def add_days_to_date(date_str: str, days: int) -> dict:
    """
    在指定日期上增加天数
    
    Args:
        date_str: 基础日期 (YYYY-MM-DD)
        days: 要增加的天数 (可为负数)
    
    Returns:
        计算后的日期
    """
    try:
        base_date = date.fromisoformat(date_str)
        result_date = base_date + timedelta(days=days)
        
        return {
            "success": True,
            "base_date": date_str,
            "days_added": days,
            "result_date": result_date.isoformat(),
            "formatted_result": result_date.strftime('%Y年%m月%d日'),
            "message": f"{date_str} 加上 {days} 天后的日期是: {result_date.strftime('%Y年%m月%d日')}"
        }
    except Exception as e:
        return {
            "success": False,
            "base_date": date_str,
            "days_added": days,
            "message": f"计算日期时发生错误: {str(e)}"
        }

@mcp.tool()
def get_timezones() -> dict:
    """
    获取常用时区列表
    
    Returns:
        常用时区列表
    """
    try:
        common_timezones = [
            "UTC",
            "Asia/Shanghai",
            "Asia/Tokyo",
            "Asia/Seoul",
            "Asia/Singapore",
            "Europe/London",
            "Europe/Paris",
            "Europe/Berlin",
            "America/New_York",
            "America/Los_Angeles",
            "America/Chicago",
            "Australia/Sydney",
            "Pacific/Auckland"
        ]
        
        return {
            "success": True,
            "timezones": common_timezones,
            "count": len(common_timezones),
            "message": f"共提供 {len(common_timezones)} 个常用时区"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"获取时区列表时发生错误: {str(e)}"
        }

if __name__ == "__main__":
    mcp.run(
        transport="stdio"  # 使用 stdio 传输协议
    )