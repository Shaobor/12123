"""12123 integration sensors."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.event import async_track_time_interval
import logging
import asyncio
import aiohttp
from datetime import timedelta, datetime
from typing import Any, Dict, Optional

from .const import (
    DOMAIN, VIOLATION_INFO_INTERVAL, SURVEILLANCE_INFO_INTERVAL,
    GET_KEEPALIVE_INTERVAL, REQUEST_TIMEOUT, DEFAULT_ICON, PROVINCE_CODE_MAPPING,
    VIOLATION_POINTS_MAP
)

_LOGGER = logging.getLogger(__name__)

# 需要脱敏的敏感字段
TO_REDACT = ["accessToken", "JSESSIONID-L", "acw_tc", "url"]


# 单独的数据获取函数
async def fetch_vehicle_info(
    session: aiohttp.ClientSession,
    access_token: str,
    jsessionid: str,
    province_code: str
) -> Optional[Dict[str, Any]]:
    """获取车辆信息"""
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Cookie": f"JSESSIONID-L={jsessionid}",
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Connection": "keep-alive"
    }

    url = f"https://{province_code}.122.gov.cn/user/m/userinfo/allvehs"
    payload = "page=1&size=999&status=null"

    try:
        async with session.post(url, headers=headers, data=payload) as resp:
            if resp.status == 200:
                try:
                    data = await resp.json()
                    if isinstance(data, dict) and "code" in data:
                        code = str(data.get("code"))
                        if code and code != "200":
                            message = data.get("message") or data.get("msg") or "服务异常"
                            error_text = f"服务异常 (代码: {code}): {message}"
                            return {
                                "success": False,
                                "error": error_text,
                                "code": code,
                                "raw": data,
                            }
                    return {"success": True, "data": data}
                except aiohttp.ContentTypeError as json_err:
                    response_text = await resp.text()
                    if "/m/login" in response_text:
                        return {"success": False, "error": "需要重新登录"}
                    return {"success": False, "error": f"JSON解析错误: {json_err}"}
            else:
                return {"success": False, "error": f"HTTP {resp.status}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def fetch_violation_info(
    session: aiohttp.ClientSession,
    access_token: str,
    jsessionid: str,
    province_code: str
) -> Optional[Dict[str, Any]]:
    """获取驾驶证违章信息"""
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Cookie": f"JSESSIONID-L={jsessionid}",
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Connection": "keep-alive"
    }

    url = f"https://{province_code}.122.gov.cn/user/m/userinfo/drvvio"
    payload = "drvSize=10&vioSize=5&forcSize=5"

    try:
        async with session.post(url, headers=headers, data=payload) as resp:
            if resp.status == 200:
                try:
                    data = await resp.json()
                    _LOGGER.debug(f"驾驶证违章API原始响应: {data}")
                    if isinstance(data, dict):
                        _LOGGER.debug(f"驾驶证违章API响应键值: {list(data.keys())}")
                    return {"success": True, "data": data}
                except aiohttp.ContentTypeError as json_err:
                    response_text = await resp.text()
                    if "/m/login" in response_text:
                        return {"success": False, "error": "需要重新登录"}
                    return {"success": False, "error": f"JSON解析错误: {json_err}"}
            else:
                return {"success": False, "error": f"HTTP {resp.status}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def fetch_surveillance_info(
    session: aiohttp.ClientSession,
    access_token: str,
    jsessionid: str,
    province_code: str
) -> Optional[Dict[str, Any]]:
    """获取车辆监控信息"""
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Cookie": f"JSESSIONID-L={jsessionid}",
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Connection": "keep-alive"
    }

    url = f"https://{province_code}.122.gov.cn/user/m/userinfo/vehundosurveils"
    payload = "page=1&size=10"

    try:
        async with session.post(url, headers=headers, data=payload) as resp:
            if resp.status == 200:
                try:
                    data = await resp.json()
                    return {"success": True, "data": data}
                except aiohttp.ContentTypeError as json_err:
                    response_text = await resp.text()
                    if "/m/login" in response_text:
                        return {"success": False, "error": "需要重新登录"}
                    return {"success": False, "error": f"JSON解析错误: {json_err}"}
            else:
                return {"success": False, "error": f"HTTP {resp.status}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """为12123集成设置传感器平台。"""
    _LOGGER.debug("设置12123传感器")

    access_token = entry.data.get("accessToken")
    jsessionid = entry.data.get("JSESSIONID-L")
    acw_tc = entry.data.get("acw_tc")
    province_code = entry.data.get("sf")
    url = entry.data.get("url")
    account_name = entry.data.get("account_name", "未知账户")

    if not all([access_token, jsessionid, province_code]):
        _LOGGER.error("缺少必要的认证信息，无法设置传感器")
        return

    # 创建设备信息
    device_info = DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{province_code}")},
        name=f"12123 ({account_name})",
        manufacturer="Shaobor丶",
        model=f"12123 ({province_code.upper()}省)",
        sw_version="1.1.0"
    )

    # 创建共享的session和SSL上下文
    def create_ssl_context():
        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        return ssl_context

    ssl_context = await hass.async_add_executor_job(create_ssl_context)

    session = aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        connector=aiohttp.TCPConnector(
            ssl=ssl_context,
            force_close=True,
            enable_cleanup_closed=True
        )
    )

    # 注册清理函数
    async def cleanup_session():
        await session.close()
    entry.async_on_unload(cleanup_session)

    # 1. 创建车辆信息Coordinator（由保活驱动）
    async def _update_vehicle_data():
        return await fetch_vehicle_info(session, access_token, jsessionid, province_code)

    vehicle_coordinator = DataUpdateCoordinator(
        hass,
        logger=_LOGGER,
        name=f"{DOMAIN}_vehicle",
        update_interval=None,  # 车辆信息由保活请求触发
        update_method=_update_vehicle_data,
    )

    # 2. 创建驾驶证违章信息Coordinator（10分钟）
    async def _update_violation_data():
        return await fetch_violation_info(session, access_token, jsessionid, province_code)

    violation_coordinator = DataUpdateCoordinator(
        hass,
        logger=_LOGGER,
        name=f"{DOMAIN}_violation",
        update_interval=VIOLATION_INFO_INTERVAL,
        update_method=_update_violation_data,
    )

    # 3. 创建车辆监控信息Coordinator（30分钟）
    async def _update_surveillance_data():
        return await fetch_surveillance_info(session, access_token, jsessionid, province_code)

    surveillance_coordinator = DataUpdateCoordinator(
        hass,
        logger=_LOGGER,
        name=f"{DOMAIN}_surveillance",
        update_interval=SURVEILLANCE_INFO_INTERVAL,
        update_method=_update_surveillance_data,
    )

    # 4. 登录状态：由保活任务驱动
    login_status: Dict[str, Any] = {
        "success": True,
        "logged_in": True,
        "message": "等待保活首次执行",
        "status_code": None,
        "final_url": "",
        "checked_at": None,
        "error": None,
    }

    async def _get_login_status():
        return login_status

    login_coordinator = DataUpdateCoordinator(
        hass,
        logger=_LOGGER,
        name=f"{DOMAIN}_login",
        update_interval=None,
        update_method=_get_login_status,
    )
    login_coordinator.async_set_updated_data(login_status.copy())

    # 5. GET保活请求（5分钟）- 使用登录接口返回的URL进行保活
    async def get_keepalive_task(_: datetime) -> None:
        """定时执行GET保活请求以维持会话（使用登录成功后的URL，自动重定向）"""
        if not url:
            _LOGGER.debug("保活请求：URL为空，跳过请求")
            return

        if not jsessionid or not access_token:
            _LOGGER.debug("保活请求：缺少必要的认证信息，跳过请求")
            return

        cookie_parts = []
        if access_token:
            cookie_parts.append(f"accessToken={access_token}")
        if acw_tc:
            cookie_parts.append(f"acw_tc={acw_tc}")
        if jsessionid:
            cookie_parts.append(f"JSESSIONID-L={jsessionid}")

        cookie = "; ".join(cookie_parts)

        headers = {
            "Cookie": cookie,
            "User-Agent": "Mozilla/5.0",
            "Accept": "*/*",
            "Connection": "keep-alive",
            "Referer": f"https://{province_code}.122.gov.cn/",
        }

        try:
            _LOGGER.debug(f"执行GET保活请求，URL: {url}")
            async with session.get(url, headers=headers, allow_redirects=True) as resp:
                final_url = str(resp.url)
                if resp.url != url:
                    _LOGGER.debug(
                        f"GET保活请求发生重定向：原始URL: {url} -> 最终URL: {final_url}"
                    )

                checked_at = datetime.utcnow().isoformat()
                redirected_to_login = any(
                    marker in final_url.lower()
                    for marker in ["/m/login", "/login", "loginsuccess?fail", "logon"]
                )
                # 一些省份（如黑龙江）会在重定向链末端返回404，但会话仍然有效。
                redirect_chain = [str(history_step.url) for history_step in resp.history]
                redirect_status_chain = [history_step.status for history_step in resp.history]
                if redirect_chain:
                    _LOGGER.debug(
                        "GET保活请求重定向链: %s",
                        " -> ".join(redirect_chain + [final_url]),
                    )
                effective_success = resp.status == 200
                if not effective_success:
                    # 如果最终返回404，但重定向链存在且未指向登录页，视为成功
                    if (
                        resp.status == 404
                        and redirect_chain
                        and not redirected_to_login
                    ):
                        effective_success = True
                    # 如果中间存在成功或非登录跳转的302，也认为成功
                    elif any(
                        status in (200, 302, 303, 307, 308)
                        for status in redirect_status_chain
                    ) and not redirected_to_login:
                        effective_success = True

                if effective_success and not redirected_to_login:
                    login_status.update(
                        {
                            "success": True,
                            "logged_in": True,
                            "message": "会话有效",
                            "status_code": resp.status,
                            "final_url": final_url,
                            "checked_at": checked_at,
                            "error": None,
                        }
                    )
                    _LOGGER.info(
                        f"GET保活请求成功，会话有效，最终URL: {final_url} (状态码: {resp.status})"
                    )

                    # 保活成功后刷新车辆信息，避免额外的周期性请求
                    try:
                        _LOGGER.debug("保活成功，触发车辆信息刷新")
                        await vehicle_coordinator.async_request_refresh()
                    except Exception as refresh_err:
                        _LOGGER.warning(f"保活触发车辆信息刷新失败: {refresh_err}")
                else:
                    fail_reason = (
                        "重定向至登录页" if redirected_to_login else "状态码异常"
                    )
                    login_status.update(
                        {
                            "success": True,
                            "logged_in": False,
                            "message": f"需要重新登录（{fail_reason}）",
                            "status_code": resp.status,
                            "final_url": final_url,
                            "checked_at": checked_at,
                            "error": None,
                        }
                    )
                    _LOGGER.warning(
                        f"GET保活请求：会话失效或异常，需要重新登录。原因：{fail_reason}，状态码: {resp.status}，最终URL: {final_url}"
                    )
                login_coordinator.async_set_updated_data(login_status.copy())
        except aiohttp.ClientError as e:
            login_status.update(
                {
                    "success": False,
                    "logged_in": False,
                    "message": "保活请求网络错误",
                    "status_code": None,
                    "final_url": "",
                    "checked_at": datetime.utcnow().isoformat(),
                    "error": str(e),
                }
            )
            login_coordinator.async_set_updated_data(login_status.copy())
            _LOGGER.warning(f"GET保活请求网络错误: {e}")
        except Exception as e:
            login_status.update(
                {
                    "success": False,
                    "logged_in": False,
                    "message": "保活请求未知错误",
                    "status_code": None,
                    "final_url": "",
                    "checked_at": datetime.utcnow().isoformat(),
                    "error": str(e),
                }
            )
            login_coordinator.async_set_updated_data(login_status.copy())
            _LOGGER.error(f"GET保活请求未知错误: {e}")

    # 注册GET保活定时任务
    cancel_callback = async_track_time_interval(hass, get_keepalive_task, GET_KEEPALIVE_INTERVAL)
    entry.async_on_unload(cancel_callback)

    # 启动时立即执行一次保活请求，避免等待下一个调度周期
    hass.async_create_task(get_keepalive_task(datetime.utcnow()))

    # 创建传感器
    sensors = [
        # 使用各自的coordinator
        VehicleSensor(vehicle_coordinator, entry.entry_id, device_info, DEFAULT_ICON),
        DriverLicenseSensor(violation_coordinator, entry.entry_id, device_info, DEFAULT_ICON),
        ThirdRequestSensor(surveillance_coordinator, entry.entry_id, device_info, DEFAULT_ICON),
        # 登录状态传感器使用login_coordinator
        SessionStatusSensor(login_coordinator, entry.entry_id, device_info, DEFAULT_ICON),
    ]

    async_add_entities(sensors)

    # 立即触发第一次更新，确保传感器有初始数据
    _LOGGER.debug("触发coordinator的首次更新")
    await vehicle_coordinator.async_request_refresh()
    await violation_coordinator.async_request_refresh()
    await surveillance_coordinator.async_request_refresh()
    await login_coordinator.async_request_refresh()

    _LOGGER.info(
        "传感器设置完成 - 车辆信息:保活驱动, "
        f"驾驶证违章:{VIOLATION_INFO_INTERVAL}, "
        f"车辆监控:{SURVEILLANCE_INFO_INTERVAL}, "
        "登录状态:保活驱动, "
        f"GET保活:{GET_KEEPALIVE_INTERVAL}"
    )


class Base12123Sensor(CoordinatorEntity, SensorEntity):
    """12123传感器基类"""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry_id: str,
        device_info: DeviceInfo,
        icon: str,
        name: str,
        unique_id_suffix: str
    ) -> None:
        """初始化基础传感器"""
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_icon = icon
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{unique_id_suffix}"
        # 移除 DIAGNOSTIC 类别，让传感器显示为普通传感器而不是诊断
        # self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._entry_id = entry_id

    def _format_update_time(self) -> str:
        """格式化更新时间"""
        from datetime import datetime
        
        # 尝试多种可能的属性名
        time_attrs = [
            'last_update_success_time',
            'last_update_time', 
            'last_update',
        ]
        
        for attr_name in time_attrs:
            if hasattr(self.coordinator, attr_name):
                attr_value = getattr(self.coordinator, attr_name)
                if attr_value:
                    # 如果是 datetime 对象
                    if isinstance(attr_value, datetime):
                        return attr_value.strftime("%Y-%m-%d %H:%M:%S")
                    # 如果是其他类型，尝试转换
                    try:
                        if hasattr(attr_value, 'strftime'):
                            return attr_value.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception as e:
                        _LOGGER.debug(f"{self._attr_name}: 格式化时间属性时出错: {e}")
        
        # 如果 coordinator 有数据且更新成功，使用当前时间作为备用
        if (hasattr(self.coordinator, 'data') and self.coordinator.data and 
            hasattr(self.coordinator, 'last_update_success') and self.coordinator.last_update_success):
            # 记录调试信息
            _LOGGER.debug(f"{self._attr_name}: 使用当前时间作为更新时间，coordinator属性: {[a for a in dir(self.coordinator) if not a.startswith('_')]}")
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 调试：记录为什么返回"从未更新"
        _LOGGER.debug(f"{self._attr_name}: 无法获取更新时间 - data存在: {hasattr(self.coordinator, 'data') and bool(self.coordinator.data)}, "
                     f"last_update_success: {getattr(self.coordinator, 'last_update_success', None)}")
        return "从未更新"

    @property
    def available(self) -> bool:
        """传感器可用性 - 基础传感器总是可用的，除非有网络错误"""
        return True


class VehicleSensor(Base12123Sensor):
    """车辆信息传感器，处理车辆信息接口"""

    def __init__(self, coordinator: DataUpdateCoordinator, entry_id: str, device_info: DeviceInfo, icon: str):
        super().__init__(coordinator, entry_id, device_info, icon, "12123_车辆信息", "vehicle_info")

    @property
    def native_value(self) -> StateType:
        """传感器主状态：车辆总数"""
        data = self.coordinator.data
        if not data:
            return "未知"

        if not data.get("success"):
            code = data.get("code")
            if code:
                return f"服务异常({code})"
            return "服务异常"

        if "data" in data:
            vehicle_data = data["data"]
            if isinstance(vehicle_data, dict) and "data" in vehicle_data:
                return vehicle_data["data"].get("totalCount", 0)
            if isinstance(vehicle_data, dict) and "content" in vehicle_data:
                return len(vehicle_data.get("content", []))
        return 0

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """额外属性：展示车辆详细信息及更新时间"""
        attributes = {}

        data = self.coordinator.data
        if not data:
            attributes["数据更新时间"] = self._format_update_time()
            return attributes

        if not data.get("success"):
            attributes["错误信息"] = data.get("error", "未知错误")
            if "code" in data:
                attributes["错误代码"] = data.get("code")
            attributes["数据更新时间"] = self._format_update_time()
            return attributes

        if "data" in data:
            vehicle_data = data["data"]
            if isinstance(vehicle_data, dict) and "data" in vehicle_data:
                vehicles = vehicle_data["data"].get("content", [])
                attributes["车辆总数"] = len(vehicles)

                for i, vehicle in enumerate(vehicles, 1):
                    attributes[f"车辆{i}_车牌号"] = vehicle.get("hphm", "未知")
                    attributes[f"车辆{i}_类型"] = vehicle.get("cllxStr", "未知")
                    attributes[f"车辆{i}_状态"] = vehicle.get("ztStr", "未知")
                    attributes[f"车辆{i}_检验有效期至"] = vehicle.get("yxqz", "未知")
                    attributes[f"车辆{i}_电子监控"] = vehicle.get("dzjk", "未知")

        attributes["数据更新时间"] = self._format_update_time()
        return attributes

    @property
    def available(self) -> bool:
        """传感器可用性：基于数据获取状态"""
        data = self.coordinator.data
        return (
            self.coordinator.last_update_success
            and data is not None
            and data.get("success", False)
        )


class DriverLicenseSensor(Base12123Sensor):
    """驾驶证信息传感器，处理驾驶证违章接口"""

    def __init__(self, coordinator: DataUpdateCoordinator, entry_id: str, device_info: DeviceInfo, icon: str):
        super().__init__(coordinator, entry_id, device_info, icon, "12123_驾驶证信息", "driver_license_info")
        self._attr_icon = "mdi:card-account-details"

    @property
    def native_value(self) -> StateType:
        """传感器主状态：12-累积记分"""
        data = self.coordinator.data
        if not data:
            _LOGGER.debug("驾驶证传感器：没有数据")
            return "未知"

        if not data.get("success"):
            _LOGGER.debug(f"驾驶证传感器：API调用失败，错误: {data.get('error', '未知错误')}")
            return "未知"

        if "data" not in data:
            _LOGGER.debug("驾驶证传感器：响应中没有data字段")
            return "未知"

        license_data = data["data"]
        if not isinstance(license_data, dict):
            _LOGGER.debug(f"驾驶证传感器：data不是字典格式: {type(license_data)}")
            return "未知"

        # 检查是否是错误响应（包含code字段且不是200）
        if "code" in license_data:
            code = license_data.get("code")
            if code != 200 and code != "200":
                error_message = license_data.get("message", "未知错误")
                _LOGGER.warning(f"驾驶证传感器：API返回错误，代码: {code}, 消息: {error_message}")
                return "服务异常"

        # 从drvs数组中提取累积记分
        drvs_array = None
        
        # 尝试路径1: license_data["drvs"]
        if "drvs" in license_data and isinstance(license_data["drvs"], list) and len(license_data["drvs"]) > 0:
            drvs_array = license_data["drvs"]
        # 尝试路径2: license_data["data"]["drvs"]
        elif "data" in license_data and isinstance(license_data["data"], dict):
            if "drvs" in license_data["data"] and isinstance(license_data["data"]["drvs"], list) and len(license_data["data"]["drvs"]) > 0:
                drvs_array = license_data["data"]["drvs"]
            # 尝试路径3: license_data["data"]["data"]["drvs"] (更深层嵌套)
            elif "data" in license_data["data"] and isinstance(license_data["data"]["data"], dict):
                if "drvs" in license_data["data"]["data"] and isinstance(license_data["data"]["data"]["drvs"], list) and len(license_data["data"]["data"]["drvs"]) > 0:
                    drvs_array = license_data["data"]["data"]["drvs"]
        
        if drvs_array and len(drvs_array) > 0:
            drv_info = drvs_array[0]
            if isinstance(drv_info, dict) and "ljjf" in drv_info:
                try:
                    ljjf = int(drv_info["ljjf"]) if drv_info["ljjf"] else 0
                    result = 12 - ljjf
                    _LOGGER.debug(f"驾驶证传感器：累积记分={ljjf}, 计算结果=12-{ljjf}={result}")
                    return result
                except (ValueError, TypeError):
                    _LOGGER.warning(f"驾驶证传感器：无法解析累积记分值: {drv_info.get('ljjf')}")
                    return "未知"

        _LOGGER.debug(f"驾驶证传感器：无法找到drvs数组或累积记分字段")
        return "未知"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """额外属性：展示驾驶证详细信息及更新时间"""
        attributes = {}

        data = self.coordinator.data
        if not data:
            _LOGGER.debug("驾驶证传感器：没有数据")
            attributes["数据更新时间"] = self._format_update_time()
            return attributes

        if not data.get("success"):
            error_msg = data.get('error', '未知错误')
            _LOGGER.warning(f"驾驶证传感器：API调用失败: {error_msg}")
            attributes["数据更新时间"] = self._format_update_time()
            return attributes

        # 根据用户提供的字段映射直接创建字段
        if "data" in data:
            license_data = data["data"]
            if isinstance(license_data, dict):
                # 调试：打印完整的API响应数据结构
                _LOGGER.debug(f"驾驶证传感器：完整API响应数据结构: {license_data}")
                _LOGGER.debug(f"驾驶证传感器：数据类型: {type(license_data)}")
                _LOGGER.debug(f"驾驶证传感器：数据键值: {list(license_data.keys()) if isinstance(license_data, dict) else '非字典类型'}")

                # 检查是否是错误响应（包含code字段且不是200）
                if "code" in license_data:
                    code = license_data.get("code")
                    if code != 200 and code != "200":
                        error_message = license_data.get("message", "未知错误")
                        attributes["错误信息"] = f"服务异常 (代码: {code}): {error_message}"
                        attributes["错误代码"] = code
                        attributes["错误消息"] = error_message
                        _LOGGER.warning(f"驾驶证传感器：API返回错误，代码: {code}, 消息: {error_message}")
                        _LOGGER.warning(f"驾驶证传感器：license_data完整内容: {license_data}")
                        # 即使有错误，也尝试检查是否有部分数据可用
                        # 检查嵌套的data结构
                        has_drvs = False
                        if "drvs" in license_data and isinstance(license_data["drvs"], list) and len(license_data["drvs"]) > 0:
                            has_drvs = True
                        elif "data" in license_data and isinstance(license_data["data"], dict):
                            if "drvs" in license_data["data"] and isinstance(license_data["data"]["drvs"], list) and len(license_data["data"]["drvs"]) > 0:
                                has_drvs = True
                            # 检查更深层嵌套
                            elif "data" in license_data["data"] and isinstance(license_data["data"]["data"], dict):
                                if "drvs" in license_data["data"]["data"] and isinstance(license_data["data"]["data"]["drvs"], list) and len(license_data["data"]["data"]["drvs"]) > 0:
                                    has_drvs = True
                        
                        if has_drvs:
                            _LOGGER.info(f"驾驶证传感器：虽然API返回错误，但发现drvs数组，尝试提取字段")
                            # 继续执行下面的字段提取逻辑，不提前返回
                        else:
                            attributes["数据更新时间"] = self._format_update_time()
                            return attributes

                # 优先从drvs数组中提取驾驶证信息
                # 数据结构可能是 data.data.drvs 或 data.data.data.drvs
                drvs_array = None
                
                # 尝试路径1: license_data["drvs"]
                if "drvs" in license_data and isinstance(license_data["drvs"], list) and len(license_data["drvs"]) > 0:
                    drvs_array = license_data["drvs"]
                    _LOGGER.info(f"驾驶证传感器：在license_data中找到drvs数组")
                # 尝试路径2: license_data["data"]["drvs"]
                elif "data" in license_data and isinstance(license_data["data"], dict):
                    _LOGGER.info(f"驾驶证传感器：检查license_data.data，键值: {list(license_data['data'].keys())}")
                    if "drvs" in license_data["data"] and isinstance(license_data["data"]["drvs"], list) and len(license_data["data"]["drvs"]) > 0:
                        drvs_array = license_data["data"]["drvs"]
                        _LOGGER.info(f"驾驶证传感器：在license_data.data中找到drvs数组，长度: {len(drvs_array)}")
                    # 尝试路径3: license_data["data"]["data"]["drvs"] (更深层嵌套)
                    elif "data" in license_data["data"] and isinstance(license_data["data"]["data"], dict):
                        _LOGGER.info(f"驾驶证传感器：检查license_data.data.data，键值: {list(license_data['data']['data'].keys())}")
                        if "drvs" in license_data["data"]["data"] and isinstance(license_data["data"]["data"]["drvs"], list) and len(license_data["data"]["data"]["drvs"]) > 0:
                            drvs_array = license_data["data"]["data"]["drvs"]
                            _LOGGER.info(f"驾驶证传感器：在license_data.data.data中找到drvs数组，长度: {len(drvs_array)}")
                
                if drvs_array and len(drvs_array) > 0:
                    drv_info = drvs_array[0]  # 取第一个驾驶证信息
                    if isinstance(drv_info, dict):
                        _LOGGER.info(f"驾驶证传感器：从drvs数组提取数据，字段: {list(drv_info.keys())}")
                        
                        # 直接提取用户要求的字段（即使值为None也添加，让用户知道字段存在）
                        if "zjcx" in drv_info:
                            value = drv_info["zjcx"]
                            attributes["证件车型"] = value if value is not None else "未知"
                            _LOGGER.info(f"驾驶证传感器：证件车型 = {value}")
                        
                        if "syyxqz" in drv_info:
                            value = drv_info["syyxqz"]
                            attributes["使用有效期至"] = value if value is not None else "未知"
                            _LOGGER.info(f"驾驶证传感器：使用有效期至 = {value}")
                        
                        # 优先使用ztStr（状态文字描述），如果没有再使用zt（状态代码）
                        if "ztStr" in drv_info:
                            value = drv_info["ztStr"]
                            attributes["驾驶证状态"] = value if value is not None else "未知"
                            _LOGGER.info(f"驾驶证传感器：驾驶证状态 = {value}")
                        elif "ztstr" in drv_info:
                            value = drv_info["ztstr"]
                            attributes["驾驶证状态"] = value if value is not None else "未知"
                            _LOGGER.info(f"驾驶证传感器：驾驶证状态 = {value}")
                        elif "zt" in drv_info:
                            value = drv_info["zt"]
                            attributes["驾驶证状态"] = value if value is not None else "未知"
                            _LOGGER.info(f"驾驶证传感器：驾驶证状态 = {value}（使用状态代码）")
                        
                        if "ljjf" in drv_info:
                            value = drv_info["ljjf"]
                            attributes["累积记分"] = value if value is not None else "0"
                            _LOGGER.info(f"驾驶证传感器：累积记分 = {value}")
                        
                        if "qfrq" in drv_info:
                            value = drv_info["qfrq"]
                            attributes["清分日期"] = value if value is not None else "未知"
                            _LOGGER.info(f"驾驶证传感器：清分日期 = {value}")
                else:
                    _LOGGER.warning(f"驾驶证传感器：未找到drvs数组或数组为空。license_data键值: {list(license_data.keys())}")
                    if "data" in license_data:
                        _LOGGER.warning(f"驾驶证传感器：license_data.data键值: {list(license_data['data'].keys()) if isinstance(license_data['data'], dict) else '非字典类型'}")

                # 支持多种可能的字段名变体（作为备用方案）
                field_variations = {
                    "证件车型": ["zjcx", "zjcxStr"],
                    "使用有效期至": ["syyxqz", "syyxqzStr"],
                    "驾驶证状态": ["zt", "ztStr"],
                    "累积记分": ["ljjf", "ljjfStr"],
                    "清分日期": ["qfrq", "qfrqStr"],
                    "身份证号码": ["sfzmhm", "sfzmhmStr"]
                }

                # 如果上述字段还未设置，尝试从扁平数据创建字段
                for display_name, api_fields in field_variations.items():
                    if display_name not in attributes:  # 只在未设置时尝试
                        value_found = False
                        for api_field in api_fields:
                            if api_field in license_data:
                                attributes[display_name] = license_data[api_field]
                                _LOGGER.debug(f"驾驶证传感器：创建字段 {api_field} -> {display_name}: {license_data[api_field]}")
                                value_found = True
                                break
                        if not value_found:
                            _LOGGER.debug(f"驾驶证传感器：未找到字段 {display_name}，尝试的字段: {api_fields}")

                # 如果数据在嵌套结构中
                if "data" in license_data and isinstance(license_data["data"], dict):
                    nested_data = license_data["data"]
                    _LOGGER.debug(f"驾驶证传感器：找到嵌套数据结构，键值: {list(nested_data.keys())}")
                    for display_name, api_fields in field_variations.items():
                        if display_name not in attributes:  # 只在未设置时尝试
                            value_found = False
                            for api_field in api_fields:
                                if api_field in nested_data:
                                    attributes[display_name] = nested_data[api_field]
                                    _LOGGER.debug(f"驾驶证传感器：从嵌套数据创建字段 {api_field} -> {display_name}: {nested_data[api_field]}")
                                    value_found = True
                                    break
                            if not value_found:
                                _LOGGER.debug(f"驾驶证传感器：嵌套数据中未找到字段 {display_name}，尝试的字段: {api_fields}")

        # 记录最终提取到的字段
        extracted_fields = [k for k in attributes.keys() if k in ["证件车型", "使用有效期至", "驾驶证状态", "累积记分", "清分日期"]]
        if extracted_fields:
            _LOGGER.info(f"驾驶证传感器：成功提取的字段: {extracted_fields}")
        else:
            _LOGGER.warning(f"驾驶证传感器：未能提取任何自定义字段。当前属性键: {list(attributes.keys())}")

        attributes["数据更新时间"] = self._format_update_time()
        return attributes

    @property
    def available(self) -> bool:
        """传感器可用性：基于数据获取状态"""
        data = self.coordinator.data
        return (
            self.coordinator.last_update_success
            and data is not None
            and data.get("success", False)
        )


class ThirdRequestSensor(Base12123Sensor):
    """车辆监控传感器，处理监控接口"""

    def __init__(self, coordinator: DataUpdateCoordinator, entry_id: str, device_info: DeviceInfo, icon: str):
        super().__init__(coordinator, entry_id, device_info, icon, "12123_违章监控记录", "surveillance_info")

    @property
    def native_value(self) -> StateType:
        """传感器主状态：监控记录数"""
        data = self.coordinator.data
        if data and data.get("success") and "data" in data:
            surveillance_data = data["data"]
            if isinstance(surveillance_data, dict):
                if "data" in surveillance_data:
                    content = surveillance_data["data"].get("content", [])
                    return len(content)
                elif "content" in surveillance_data:
                    return len(surveillance_data["content"])
        return 0

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """额外属性：展示监控记录详细信息及更新时间"""
        attributes = {}

        data = self.coordinator.data
        if not data:
            _LOGGER.debug("监控记录传感器：没有数据")
            attributes["数据更新时间"] = self._format_update_time()
            return attributes

        if not data.get("success"):
            error_msg = data.get('error', '未知错误')
            _LOGGER.warning(f"监控记录传感器：API调用失败: {error_msg}")
            attributes["数据更新时间"] = self._format_update_time()
            return attributes

        if "data" not in data:
            _LOGGER.debug("监控记录传感器：响应中没有data字段")
            attributes["数据更新时间"] = self._format_update_time()
            return attributes

        surveillance_data = data["data"]
        if not isinstance(surveillance_data, dict):
            _LOGGER.debug(f"监控记录传感器：data不是字典格式: {type(surveillance_data)}")
            attributes["数据更新时间"] = self._format_update_time()
            return attributes

        # 尝试多种路径提取监控信息
        content = None

        # 路径1: data.data.content
        if "data" in surveillance_data and isinstance(surveillance_data["data"], dict):
            data_section = surveillance_data["data"]
            content = data_section.get("content", [])

        # 路径2: data.content
        elif "content" in surveillance_data:
            content = surveillance_data["content"]

        # 路径3: data中其他可能的字段
        else:
            # 检查其他可能的字段名
            possible_content_fields = ["records", "list", "监控记录", "surveillances", "items"]
            for field in possible_content_fields:
                if field in surveillance_data:
                    content = surveillance_data[field]
                    break

        if content is not None:
            if isinstance(content, list):
                attributes["监控记录总数"] = len(content)

                # 提取监控记录详细信息
                for i, record in enumerate(content, 1):
                    if isinstance(record, dict):
                        behavior_text = None
                        matched_points = None

                        # 车牌号字段
                        for plate_field in ["hphm", "plate", "车牌", "license_plate", "car_number"]:
                            if plate_field in record and record[plate_field]:
                                attributes[f"记录{i}_车牌号"] = record[plate_field]
                                break

                        # 时间字段
                        for time_field in ["wfsj", "time", "时间", "createTime", "date"]:
                            if time_field in record and record[time_field]:
                                attributes[f"记录{i}_时间"] = record[time_field]
                                break

                        # 地点字段
                        for location_field in ["wfdz", "location", "地点", "address", "position"]:
                            if location_field in record and record[location_field]:
                                attributes[f"记录{i}_地点"] = record[location_field]
                                break

                        # 行为字段
                        for behavior_field in ["wfms", "wfxw", "behavior", "行为", "violation", "illegal_act"]:
                            if behavior_field in record and record[behavior_field]:
                                behavior_text = record[behavior_field]
                                attributes[f"记录{i}_行为"] = behavior_text
                                break

                        # 罚款金额
                        for fine_field in ["fkje", "fine", "罚款", "amount", "money"]:
                            if fine_field in record and record[fine_field]:
                                attributes[f"记录{i}_罚款"] = record[fine_field]
                                break

                        # 记分
                        for point_field in ["wfjf", "points", "记分", "score", "deduct"]:
                            if point_field in record and record[point_field]:
                                matched_points = record[point_field]
                                attributes[f"记录{i}_记分"] = matched_points
                                break

                        if not matched_points:
                            lookup_key = behavior_text or record.get("wfms")
                            if lookup_key and lookup_key in VIOLATION_POINTS_MAP:
                                attributes[f"记录{i}_记分"] = VIOLATION_POINTS_MAP[lookup_key]

            elif isinstance(content, dict):
                attributes["监控记录总数"] = len(content)
            else:
                attributes["监控记录总数"] = 1 if content else 0
        else:
            attributes["监控记录总数"] = 0

        attributes["数据更新时间"] = self._format_update_time()
        return attributes

    @property
    def available(self) -> bool:
        """传感器可用性：基于数据获取状态"""
        data = self.coordinator.data
        return (
            self.coordinator.last_update_success
            and data is not None
            and data.get("success", False)
        )


class SessionStatusSensor(Base12123Sensor):
    """会话状态传感器，监控登录状态"""

    def __init__(self, coordinator: DataUpdateCoordinator, entry_id: str, device_info: DeviceInfo, icon: str):
        super().__init__(coordinator, entry_id, device_info, icon, "12123_会话状态", "session_status")

    @property
    def native_value(self) -> StateType:
        """传感器主状态：会话健康度"""
        if self.is_healthy:
            return "已登录"
        elif self.needs_relogin:
            return "需要重新登录"
        else:
            return "会话异常"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """额外属性：展示会话详细状态"""
        attributes = {}

        data = self.coordinator.data
        if data:
            if data.get("success"):
                if data.get("logged_in"):
                    attributes["登录状态"] = "已登录"
                    attributes["最后检查时间"] = self._format_update_time()
                else:
                    attributes["登录状态"] = "需要重新登录"
                    attributes["失败原因"] = data.get("error", "未知错误")
            else:
                attributes["登录状态"] = "检查失败"
                attributes["失败原因"] = data.get("error", "未知错误")

        return attributes

    @property
    def is_healthy(self) -> bool:
        """会话健康状态"""
        data = self.coordinator.data
        if data and data.get("success"):
            return data.get("logged_in", False)
        return False

    @property
    def needs_relogin(self) -> bool:
        """是否需要重新登录"""
        data = self.coordinator.data
        if data and data.get("success"):
            # 如果success为True但logged_in为False，需要重新登录
            return not data.get("logged_in", False)
        # 如果success为False，可能是网络错误或其他问题，不一定是需要重新登录
        # 但为了安全起见，如果数据获取失败，也认为可能需要重新登录
        if data and not data.get("success"):
            error = data.get("error", "")
            if "需要重新登录" in error or "登录" in error:
                return True
        return False

    @property
    def available(self) -> bool:
        """传感器总是可用的"""
        return True