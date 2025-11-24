"""Constants for the 12123 integration."""
from datetime import timedelta

DOMAIN = "12123"

# 省份-缩写映射表
PROVINCE_CODE_MAPPING = {
    "北京": "bj",
    "天津": "tj",
    "河北": "he",
    "山西": "sx",
    "内蒙古": "nm",
    "辽宁": "ln",
    "吉林": "jl",
    "黑龙江": "hl",
    "上海": "sh",
    "江苏": "js",
    "浙江": "zj",
    "安徽": "ah",
    "福建": "fj",
    "江西": "jx",
    "山东": "sd",
    "河南": "ha",
    "湖北": "hb",
    "湖南": "hn",
    "广东": "gd",
    "广西": "gx",
    "海南": "hi",
    "重庆": "cq",
    "四川": "sc",
    "贵州": "gz",
    "云南": "yn",
    "西藏": "xz",
    "陕西": "sn",
    "甘肃": "gs",
    "青海": "qh",
    "宁夏": "nx",
    "新疆": "xj"
}

# 提取省份列表
PROVINCES = list(PROVINCE_CODE_MAPPING.keys())

# 更新间隔配置
VEHICLE_INFO_INTERVAL = timedelta(minutes=10)  # 车辆信息接口：10分钟一次
VIOLATION_INFO_INTERVAL = timedelta(minutes=10)  # 驾驶证违章接口：10分钟一次
SURVEILLANCE_INFO_INTERVAL = timedelta(minutes=30)  # 车辆监控接口：30分钟一次
GET_KEEPALIVE_INTERVAL = timedelta(minutes=5)  # GET保活请求：5分钟一次
REQUEST_TIMEOUT = 30  # 秒

# 违章扣分映射
VIOLATION_POINTS_MAP = {
    '不按规定停车': 0,
    '驾驶机动车不按交通信号灯指示通行的': 6,
    '人行道不停车让行的': 3,
    '违反禁止标线指示': 3,
    '驾驶校车、中型以上载客载货汽车、危险物品运输车辆以外的机动车在高速公路上行驶超过规定时速百分之二十以上未达到百分之五十的': 6,
    '驾驶校车、中型以上载客载货汽车、危险物品运输车辆以外的机动车在城市快速路上行驶超过规定时速百分之二十以上未达到百分之五十的': 6,
    '驾驶校车、中型以上载客载货汽车、危险物品运输车辆以外的机动车在高速公路以外的道路上行驶超过规定时速百分之十以上未达到百分之二十的': 0,
    '不按导向车道行驶': 0,
    '驾驶校车、中型以上载客载货汽车、危险物品运输车辆以外的机动车在高速公路、城市快速路以外的道路上行驶超过规定时速百分之二十以上未达到百分之五十的': 3
}

# API端点
QR_CODE_API_URL = "https://gab.122.gov.cn/eapp/qrCode/loginQrCodeImg"
QR_CODE_QUERY_URL = "https://gab.122.gov.cn/eapp/qrCode/queryQRCode"

# 传感器配置
SENSOR_TYPES = {
    "vehicle": {
        "name": "12123_车辆信息",
        "unique_id": "vehicle_info",
        "icon": "mdi:car"
    },
    "driver_license": {
        "name": "12123_驾驶证信息",
        "unique_id": "driver_license_info",
        "icon": "mdi:card-account-details"
    },
    "violation": {
        "name": "12123_违章监控记录",
        "unique_id": "third_request_info",
        "icon": "mdi:camera"
    }
}

# 错误消息
ERROR_MESSAGES = {
    "connection_error": "网络连接错误，请检查网络",
    "server_error": "服务器错误，请稍后重试",
    "invalid_response": "服务器响应格式错误",
    "unknown_error": "未知错误",
    "no_image_data": "未获取到二维码图片",
    "session_lost": "会话丢失，请重新配置",
    "session_closed": "会话已关闭，请重新配置",
    "session_recreate_failed": "重新创建会话失败，请重试",
    "incomplete_auth": "认证信息不完整，请重试",
    "please_scan": "请扫描二维码",
    "second_request_failed": "第二次请求失败，请重试",
    "second_request_error": "第二次请求异常，请重试",
    "no_redirect_url": "操作失败: 未获取到重定向URL",
    "auth_failed": "认证过程中获取用户信息失败",
    "missing_cookies": "登录认证失败，未获取到必需的认证信息"
}

# 默认图标
DEFAULT_ICON = "mdi:car"