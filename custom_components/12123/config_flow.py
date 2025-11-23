import voluptuous as vol
from homeassistant import config_entries
import logging
import aiohttp
import asyncio
import json
from typing import Any, Dict, Optional

from .const import (
    DOMAIN,
    PROVINCE_CODE_MAPPING,
    PROVINCES,
    QR_CODE_API_URL,
    QR_CODE_QUERY_URL,
    REQUEST_TIMEOUT,
    ERROR_MESSAGES,
    DEFAULT_ICON
)

_LOGGER = logging.getLogger(__name__)


class MySensorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    MINOR_VERSION = 1
    _selected_province: Optional[str] = None
    _selected_province_code: Optional[str] = None
    _session: Optional[aiohttp.ClientSession] = None

    # 存储认证信息供图标选择步骤使用
    _access_token: Optional[str] = None
    _jsessionid: Optional[str] = None
    _acw_tc: Optional[str] = None
    _url: Optional[str] = None
    _auth_cookies: Optional[Dict[str, str]] = None
    _qrcode_digest: Optional[str] = None
    token: Optional[str] = None
    url: Optional[str] = None
    _img_base64: Optional[str] = None

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """第一步：省份选择，并在选择后发送POST请求"""
        errors = {}

        if user_input is not None:
            self._selected_province = user_input["province"]
            self._selected_province_code = PROVINCE_CODE_MAPPING[self._selected_province]
            _LOGGER.info(f"用户选择了省份：{self._selected_province}，变量：{self._selected_province_code}")

            # 发送POST请求
            try:
                # 创建可复用的session
                if self._session is None:
                    # 为政府API创建SSL上下文，允许自签名证书
                    ssl_context = await self.hass.async_add_executor_job(self._create_ssl_context)
                    connector = aiohttp.TCPConnector(
                        ssl=ssl_context,
                        force_close=True,
                        enable_cleanup_closed=True
                    )
                    self._session = aiohttp.ClientSession(
                        timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                        connector=connector
                    )

                url = QR_CODE_API_URL
                async with self._session.get(url) as response:
                    if response.status == 200:
                        _LOGGER.info("省份选择已成功提交到服务器")
                        try:
                            response_data = await response.json()
                        except aiohttp.ContentTypeError:
                            errors["base"] = ERROR_MESSAGES.get("invalid_response", "服务器响应格式错误")
                            _LOGGER.error("响应不是有效的JSON格式")
                            return self._show_user_form(errors)

                        for cookie in response.cookies.values():
                            if cookie.key == "_qrcode_digest":
                                self._qrcode_digest = cookie.value
                                # 只记录部分敏感信息，避免完整泄露
                                _LOGGER.info(f"成功获取_qrcode_digest: {cookie.value[:8]}...")
                                break
                        else:
                            _LOGGER.warning("响应中未包含_qrcode_digest Cookie")

                        token = response_data.get('token')
                        if token:
                            self.token = token
                            # 只记录部分token信息
                            _LOGGER.info(f"成功获取并保存token: {token[:8]}...")
                        else:
                            _LOGGER.warning("响应中未包含token")

                        self._img_base64 = response_data.get('img')
                        if not self._img_base64:
                            _LOGGER.warning("响应中未包含图片数据")
                            errors["base"] = ERROR_MESSAGES.get("no_image_data", "未获取到二维码图片")
                            return self._show_user_form(errors)

                    else:
                        errors["base"] = ERROR_MESSAGES.get("server_error", "服务器错误，请稍后重试")
                        _LOGGER.error(f"GET请求失败，状态码: {response.status}")
                        # 清理session资源
                        await self._cleanup_session()
                        return self._show_user_form(errors)

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                errors["base"] = ERROR_MESSAGES.get("connection_error", "网络连接错误，请检查网络")
                _LOGGER.error(f"发送GET请求时出错: {str(e)}")
                await self._cleanup_session()
                return self._show_user_form(errors)
            except Exception as e:
                errors["base"] = ERROR_MESSAGES.get("unknown_error", "未知错误")
                _LOGGER.error(f"未知错误: {str(e)}")
                await self._cleanup_session()
                return self._show_user_form(errors)

            # POST请求成功后进入下一步
            return await self.async_step_next()

        return self._show_user_form(errors)

    def _show_user_form(self, errors: Dict[str, str]) -> Dict[str, Any]:
        """显示省份选择表单"""
        return self.async_show_form(
            step_id="user",
            description_placeholders={"msg": "请选择您所在的省份"},
            data_schema=vol.Schema({
                vol.Required("province"): vol.In(PROVINCES)
            }),
            errors=errors
        )

    async def async_step_next(self, user_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """第二步：显示二维码，点击提交时发送POST请求"""
        errors = {}

        if user_input is not None:
            # 用户点击提交，发送POST请求
            # 检查必要的认证信息
            if not self._qrcode_digest:
                errors["base"] = ERROR_MESSAGES.get("incomplete_auth", "认证信息不完整，请重试")
                _LOGGER.error("缺少_qrcode_digest，请重新配置")
                return self._show_next_form(errors)

            if not self.token:
                errors["base"] = ERROR_MESSAGES.get("incomplete_auth", "认证信息不完整，请重试")
                _LOGGER.error("缺少token，请重新配置")
                return self._show_next_form(errors)

            # 如果session丢失或已关闭，尝试重新创建
            if not self._session or self._session.closed:
                _LOGGER.warning("Session丢失或已关闭，尝试重新创建session")
                try:
                    # 重新创建session
                    ssl_context = await self.hass.async_add_executor_job(self._create_ssl_context)
                    connector = aiohttp.TCPConnector(
                        ssl=ssl_context,
                        force_close=True,
                        enable_cleanup_closed=True
                    )
                    self._session = aiohttp.ClientSession(
                        timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                        connector=connector
                    )
                    _LOGGER.info("成功重新创建session")
                except Exception as e:
                    errors["base"] = ERROR_MESSAGES.get("session_recreate_failed", "重新创建会话失败，请重试")
                    _LOGGER.error(f"重新创建session失败: {str(e)}")
                return self._show_next_form(errors)

            try:
                headers = {
                    "Content-Type": "application/json",
                    "Cookie": f"_qrcode_digest={self._qrcode_digest}"
                }

                url = f"{QR_CODE_QUERY_URL}?token={self.token}"
                _LOGGER.debug(f"准备发送QR查询请求，URL: {url}")
                async with self._session.post(url, headers=headers) as response:
                    if response.status == 200:
                        try:
                            result = await response.json()
                        except aiohttp.ContentTypeError:
                            errors["base"] = ERROR_MESSAGES.get("invalid_response", "服务器响应格式错误")
                            _LOGGER.error("QR查询响应不是有效的JSON格式")
                            return self._show_next_form(errors)

                        code = result.get("code")
                        _LOGGER.debug(f"QR查询响应代码: {code}")

                        if code == "201":
                            errors["base"] = ERROR_MESSAGES.get("please_scan", "请使用12123手机App扫描二维码，然后点击提交按钮")
                            return self._show_next_form(errors)
                        elif code == "200":
                            self.url = result.get('url')

                            if self.url:
                                try:
                                    new_headers = {
                                        "Cookie": "_122_gt_tag=1"
                                    }

                                    async with self._session.get(
                                            self.url,
                                            headers=new_headers,
                                            allow_redirects=True
                                    ) as second_response:
                                        # 验证重定向响应是否成功
                                        if second_response.status != 200:
                                            _LOGGER.error(f"重定向请求失败，状态码: {second_response.status}")
                                            errors["base"] = ERROR_MESSAGES.get("auth_failed", "认证过程中获取用户信息失败")
                                            return self._show_next_form(errors)

                                        # 记录重定向信息（用于调试）
                                        final_url = str(second_response.url)
                                        _LOGGER.info(f"登录URL重定向：原始URL: {self.url[:50]}... -> 最终URL: {final_url[:50]}...")
                                        
                                        # 保存原始的带ticket的URL（用于保活），因为Node-RED测试表明原始URL可以成功保活
                                        # 保活时会自动重定向到最终的登录页面
                                        keepalive_url = self.url
                                        _LOGGER.info(f"保存保活URL（原始URL）: {keepalive_url[:50]}...")

                                        # 提取认证cookies
                                        cookies = self._extract_auth_cookies(second_response)

                                        # 验证认证信息完整性
                                        # jsessionid 和 access_token 是必需的，acw_tc 是可选的
                                        required_cookies = ["jsessionid", "access_token"]
                                        missing_required = [k for k in required_cookies if not cookies.get(k)]
                                        
                                        if missing_required:
                                            _LOGGER.error(f"必需Cookie缺失: {missing_required}")
                                            errors["base"] = ERROR_MESSAGES.get("missing_cookies", "登录认证失败，未获取到必需的认证信息")
                                            return self._show_next_form(errors)
                                        
                                        # acw_tc 是可选的，如果缺失只记录警告
                                        if not cookies.get("acw_tc"):
                                            _LOGGER.warning("acw_tc Cookie未获取到，某些功能可能受限，但可以继续配置")

                                        # 验证登录状态 - 尝试获取用户信息来确认登录成功
                                        try:
                                            user_info = await self._get_user_info(cookies)
                                            if not user_info:
                                                _LOGGER.warning("无法获取用户信息，但可能仍然登录成功，继续创建配置")
                                                account_name = f"{self._selected_province}账号"
                                            else:
                                                # 使用API返回的用户信息生成标识符
                                                if "身份证号后4位" in user_info:
                                                    account_name = user_info["身份证号后4位"]
                                                    _LOGGER.info(f"成功获取用户身份证号后4位: {account_name}")
                                                elif "姓名" in user_info:
                                                    account_name = user_info["姓名"]
                                                    _LOGGER.info(f"成功获取用户姓名: {account_name}")
                                                else:
                                                    account_name = f"{self._selected_province}账号"
                                                    _LOGGER.warning("获取到用户信息但无法提取标识符，使用默认标识符")

                                        except Exception as e:
                                            _LOGGER.warning(f"用户信息验证失败，但二维码登录可能已成功: {e}")
                                            _LOGGER.info("继续创建配置，用户信息获取失败不影响基本功能")
                                            account_name = f"{self._selected_province}账号"

                                        # 保存认证信息
                                        self._auth_cookies = cookies
                                        await self._cleanup_session()

                                        # 创建配置条目
                                        title = f"12123 ({self._selected_province} - {account_name})"
                                        return self.async_create_entry(
                                            title=title,
                                            data={
                                                "accessToken": cookies["access_token"],
                                                "JSESSIONID-L": cookies["jsessionid"],
                                                "acw_tc": cookies.get("acw_tc") or "",  # acw_tc是可选的，如果为None则使用空字符串
                                                "sf": self._selected_province_code,
                                                "url": keepalive_url,  # 使用原始的带ticket的URL，保活时会自动重定向
                                                "account_name": account_name,
                                                "province_name": self._selected_province
                                            },
                                            options={
                                                "icon": DEFAULT_ICON
                                            }
                                        )

                                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                                    errors["base"] = ERROR_MESSAGES.get("second_request_failed", "第二次请求失败，请重试")
                                    _LOGGER.error(f"第二次请求出错: {str(e)}")
                                    # 确保清理session资源
                                    await self._cleanup_session()
                                    return self._show_next_form(errors)
                                except Exception as e:
                                    errors["base"] = ERROR_MESSAGES.get("second_request_error", "第二次请求异常，请重试")
                                    _LOGGER.error(f"第二次请求未知错误: {str(e)}")
                                    # 确保清理session资源
                                    await self._cleanup_session()
                                    return self._show_next_form(errors)
                            else:
                                errors["base"] = ERROR_MESSAGES.get("no_redirect_url", "操作失败: 未获取到重定向URL")
                        else:
                            errors["base"] = f"操作失败: {result.get('message', '未知错误')}"
                    else:
                        errors["base"] = ERROR_MESSAGES.get("server_error", "服务器错误，请稍后重试")
                        _LOGGER.error(f"QR查询请求失败，状态码: {response.status}")
                        await self._cleanup_session()

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                errors["base"] = ERROR_MESSAGES.get("connection_error", "网络连接错误，请检查网络")
                error_type = type(e).__name__
                error_msg = str(e) if str(e) else repr(e)
                _LOGGER.error(f"发送QR查询请求时出错 [类型: {error_type}]: {error_msg}")
                _LOGGER.debug(f"完整异常信息: {repr(e)}", exc_info=True)
                # 确保清理session资源
                await self._cleanup_session()
            except Exception as e:
                errors["base"] = ERROR_MESSAGES.get("unknown_error", "未知错误")
                _LOGGER.error(f"QR查询未知错误: {str(e)}")
                # 确保清理session资源
                await self._cleanup_session()

        return self._show_next_form(errors)

    def _extract_auth_cookies(self, response: aiohttp.ClientResponse) -> Dict[str, str]:
        """从响应中提取认证cookies"""
        cookies = {
            "jsessionid": None,
            "access_token": None,
            "acw_tc": None
        }

        # 从重定向历史中提取 Cookie
        for redirect in response.history:
            for cookie in redirect.cookies.values():
                if cookie.key == "JSESSIONID-L":
                    cookies["jsessionid"] = cookie.value
                    _LOGGER.info("成功获取JSESSIONID-L")
                elif cookie.key == "accessToken":
                    cookies["access_token"] = cookie.value
                    _LOGGER.info("成功获取accessToken")
                elif cookie.key == "acw_tc":
                    cookies["acw_tc"] = cookie.value
                    _LOGGER.info("成功获取acw_tc")

        # 也从最终响应中提取 Cookie（某些 Cookie 可能只在最终响应中）
        for cookie in response.cookies.values():
            if cookie.key == "JSESSIONID-L" and not cookies["jsessionid"]:
                cookies["jsessionid"] = cookie.value
                _LOGGER.info("从最终响应中成功获取JSESSIONID-L")
            elif cookie.key == "accessToken" and not cookies["access_token"]:
                cookies["access_token"] = cookie.value
                _LOGGER.info("从最终响应中成功获取accessToken")
            elif cookie.key == "acw_tc" and not cookies["acw_tc"]:
                cookies["acw_tc"] = cookie.value
                _LOGGER.info("从最终响应中成功获取acw_tc")

        return cookies

    def _create_ssl_context(self):
        """在后台线程中创建SSL上下文以避免阻塞事件循环"""
        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        return ssl_context

    def _show_next_form(self, errors: Dict[str, str]) -> Dict[str, Any]:
        """显示二维码表单"""
        if self._img_base64:
            img_html = (
                f"![12123登录二维码](data:image/png;base64,{self._img_base64})\n\n"
                "**请使用12123手机App扫描上方二维码完成登录。**\n\n"
                "扫描完成后点击下方“提交”按钮。"
            )
        else:
            img_html = (
                "⚠️ **二维码未加载**\n\n"
                "请返回上一步重新选择省份以重新获取二维码。"
            )
        
        return self.async_show_form(
            step_id="next",
            description_placeholders={
                "msg": img_html
            },
            data_schema=vol.Schema({}),
            errors=errors
        )

    async def _cleanup_session(self) -> None:
        """清理session资源"""
        if self._session:
            await self._session.close()
            self._session = None

        # 清理认证cookie
        if self._auth_cookies:
            self._auth_cookies = None

    async def async_step_reauth(self, user_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """处理重新认证"""
        return await self.async_step_user()

    async def _get_user_info(self, cookies: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """获取用户信息，返回包含姓名等标识信息的字典"""
        if not self._selected_province_code:
            return None

        try:
            # 为政府API创建SSL上下文，允许自签名证书
            ssl_context = await self.hass.async_add_executor_job(self._create_ssl_context)

            connector = aiohttp.TCPConnector(
                ssl=ssl_context,
                force_close=True,
                enable_cleanup_closed=True
            )
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                connector=connector
            ) as session:
                # 确保jsessionid存在（防御性编程）
                jsessionid = cookies.get('jsessionid')
                if not jsessionid:
                    _LOGGER.error("jsessionid缺失，无法获取用户信息")
                    return None
                
                headers = {
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Cookie": f"JSESSIONID-L={jsessionid}",
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "*/*",
                    "Connection": "keep-alive"
                }

                # 调用驾驶证信息接口获取用户信息
                url = f"https://{self._selected_province_code}.122.gov.cn/user/m/userinfo/drvvio"
                payload = "drvSize=10&vioSize=5&forcSize=5"

                # 安全地记录JSESSIONID（避免切片错误）
                jsessionid_preview = cookies['jsessionid'][:20] if cookies.get('jsessionid') and len(cookies['jsessionid']) >= 20 else (cookies.get('jsessionid') or 'None')
                _LOGGER.info(f"获取用户信息参数 - 省份代码: {self._selected_province_code}, JSESSIONID: {jsessionid_preview}...")

                _LOGGER.info(f"开始获取用户信息，URL: {url}")
                async with session.post(url, headers=headers, data=payload) as response:
                    _LOGGER.info(f"用户信息接口响应状态码: {response.status}")
                    if response.status == 200:
                        try:
                            response_text = await response.text()
                            _LOGGER.debug(f"用户信息接口原始响应: {response_text[:500]}...")
                            # 从text解析JSON，避免重复读取响应体
                            data = json.loads(response_text)
                            _LOGGER.info(f"用户信息接口JSON解析成功: {type(data)}")
                            _LOGGER.debug(f"用户信息接口响应结构: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")

                            # 先检查API响应是否成功
                            if isinstance(data, dict) and "code" in data:
                                code = data.get("code")
                                if code != 200 and code != "200":
                                    error_message = data.get("message", "未知错误")
                                    _LOGGER.warning(f"用户信息接口返回错误，代码: {code}, 消息: {error_message}")
                                    _LOGGER.debug(f"用户信息接口完整响应: {data}")
                                    # 如果返回错误，直接返回None，不尝试提取数据
                                    return None
                                else:
                                    _LOGGER.info(f"用户信息接口返回成功，代码: {code}")
                                    # 检查是否有data字段
                                    if "data" not in data:
                                        _LOGGER.warning(f"用户信息接口返回成功但缺少data字段，响应键: {list(data.keys())}")
                                        # 即使没有data字段，也尝试从顶层查找信息
                                        # 某些API可能直接在顶层返回数据

                            # 尝试从返回数据中提取身份证号等信息
                            user_info = {}

                            # 从驾驶证信息中获取身份证号和姓名
                            if data and isinstance(data, dict):
                                _LOGGER.info(f"API返回的顶级数据结构: {list(data.keys())}")

                                # 优先检查 drvs 数组（这是最常见的结构）
                                if "data" in data and isinstance(data["data"], dict):
                                    data_section = data["data"]
                                    
                                    # 检查 drvs 数组
                                    if "drvs" in data_section and isinstance(data_section["drvs"], list) and len(data_section["drvs"]) > 0:
                                        drv_info = data_section["drvs"][0]  # 取第一个驾驶证信息
                                        _LOGGER.info(f"从drvs数组提取用户信息，字段: {list(drv_info.keys())}")
                                        
                                        # 优先获取身份证号
                                        for id_field in ["sfzmhm", "idCard", "identityCard", "身份证号", "sfzm", "idcard"]:
                                            if id_field in drv_info and drv_info[id_field]:
                                                id_card = str(drv_info[id_field])
                                                _LOGGER.info(f"在drvs中找到身份证号字段 {id_field}: {id_card[:6]}...{id_card[-4:]}")
                                                # 使用后4位作为标识符
                                                if len(id_card) >= 4:
                                                    user_info["身份证号后4位"] = id_card[-4:]
                                                    user_info["完整身份证号"] = id_card
                                                else:
                                                    user_info["身份证号后4位"] = id_card
                                                    user_info["完整身份证号"] = id_card
                                                break
                                        
                                        # 如果没找到身份证号，获取姓名作为备用
                                        if "完整身份证号" not in user_info:
                                            _LOGGER.info("drvs中未找到身份证号，尝试获取姓名")
                                            for name_field in ["姓名", "name", "xm", "driverName", "xmxx"]:
                                                if name_field in drv_info and drv_info[name_field]:
                                                    user_info["姓名"] = str(drv_info[name_field])
                                                    _LOGGER.info(f"在drvs中找到姓名字段 {name_field}: {user_info['姓名']}")
                                                    break
                                    
                                    # 如果drvs中没有找到，尝试从data_section直接查找
                                    if "完整身份证号" not in user_info and "姓名" not in user_info:
                                        _LOGGER.info(f"开始从data_section提取用户信息，数据结构: {list(data_section.keys())}")

                                        # 打印所有可能的字段名用于调试
                                        for key, value in data_section.items():
                                            if 'sf' in key.lower() or 'id' in key.lower() or 'card' in key.lower() or '证' in key or '号' in key:
                                                _LOGGER.info(f"发现可能的身份字段: {key} = {str(value)[:10]}...")

                                        for id_field in ["sfzmhm", "idCard", "identityCard", "身份证号", "sfzm", "idcard"]:
                                            if id_field in data_section and data_section[id_field]:
                                                id_card = str(data_section[id_field])
                                                _LOGGER.info(f"找到身份证号字段 {id_field}: {id_card[:6]}...{id_card[-4:]}")
                                                # 使用后4位作为标识符
                                                if len(id_card) >= 4:
                                                    user_info["身份证号后4位"] = id_card[-4:]
                                                    user_info["完整身份证号"] = id_card  # 用于生成唯一标识符
                                                else:
                                                    user_info["身份证号后4位"] = id_card
                                                    user_info["完整身份证号"] = id_card
                                                break

                                        # 如果没找到身份证号，获取姓名作为备用
                                        if "完整身份证号" not in user_info:
                                            _LOGGER.info("未找到身份证号，尝试获取姓名")
                                            for name_field in ["姓名", "name", "xm", "driverName", "xmxx"]:
                                                if name_field in data_section and data_section[name_field]:
                                                    user_info["姓名"] = str(data_section[name_field])
                                                    _LOGGER.info(f"找到姓名字段 {name_field}: {user_info['姓名']}")
                                                    break

                                # 如果没找到信息，尝试其他可能的路径
                                if "完整身份证号" not in user_info and "姓名" not in user_info:
                                    # 有些API可能返回驾驶证信息数组（直接在顶层）
                                    if "drvlicinfo" in data and isinstance(data["drvlicinfo"], list) and len(data["drvlicinfo"]) > 0:
                                        _LOGGER.info(f"尝试从drvlicinfo数组获取用户信息，数组长度: {len(data['drvlicinfo'])}")
                                        first_license = data["drvlicinfo"][0]
                                        _LOGGER.info(f"第一个驾驶证信息结构: {list(first_license.keys())}")

                                        # 打印所有可能的字段名用于调试
                                        for key, value in first_license.items():
                                            if 'sf' in key.lower() or 'id' in key.lower() or 'card' in key.lower() or '证' in key or '号' in key:
                                                _LOGGER.info(f"drvlicinfo中发现可能的身份字段: {key} = {str(value)[:10]}...")

                                        # 优先获取身份证号
                                        for id_field in ["sfzmhm", "idCard", "identityCard", "身份证号", "sfzm", "idcard"]:
                                            if id_field in first_license and first_license[id_field]:
                                                id_card = str(first_license[id_field])
                                                _LOGGER.info(f"在drvlicinfo中找到身份证号字段 {id_field}: {id_card[:6]}...{id_card[-4:]}")
                                                # 使用后4位作为标识符
                                                if len(id_card) >= 4:
                                                    user_info["身份证号后4位"] = id_card[-4:]
                                                    user_info["完整身份证号"] = id_card
                                                else:
                                                    user_info["身份证号后4位"] = id_card
                                                    user_info["完整身份证号"] = id_card
                                                break

                                        # 备用：获取姓名
                                        if "完整身份证号" not in user_info:
                                            _LOGGER.info("drvlicinfo中未找到身份证号，尝试获取姓名")
                                            for name_field in ["姓名", "name", "xm", "driverName", "xmxx"]:
                                                if name_field in first_license and first_license[name_field]:
                                                    user_info["姓名"] = str(first_license[name_field])
                                                    _LOGGER.info(f"在drvlicinfo中找到姓名字段 {name_field}: {user_info['姓名']}")
                                                    break

                                # 如果data字段不存在，尝试从顶层直接查找（某些API可能直接在顶层返回数据）
                                if "完整身份证号" not in user_info and "姓名" not in user_info and "data" not in data:
                                    _LOGGER.info("data字段不存在，尝试从顶层直接查找用户信息")
                                    # 尝试从顶层直接查找身份证号
                                    for id_field in ["sfzmhm", "idCard", "identityCard", "身份证号", "sfzm", "idcard"]:
                                        if id_field in data and data[id_field]:
                                            id_card = str(data[id_field])
                                            _LOGGER.info(f"在顶层找到身份证号字段 {id_field}: {id_card[:6]}...{id_card[-4:]}")
                                            if len(id_card) >= 4:
                                                user_info["身份证号后4位"] = id_card[-4:]
                                                user_info["完整身份证号"] = id_card
                                            else:
                                                user_info["身份证号后4位"] = id_card
                                                user_info["完整身份证号"] = id_card
                                            break
                                    
                                    # 如果还是没找到，进行全数据搜索
                                    if "完整身份证号" not in user_info and "姓名" not in user_info:
                                        _LOGGER.info("前述路径未找到用户信息，开始全数据搜索")
                                        user_info = self._search_user_info_recursively(data)
                                elif "完整身份证号" not in user_info and "姓名" not in user_info:
                                    _LOGGER.info("前述路径未找到用户信息，开始全数据搜索")
                                    user_info = self._search_user_info_recursively(data)

                            if user_info:
                                _LOGGER.info(f"成功提取用户信息: {list(user_info.keys())}")
                                # 提取身份证号后4位用于显示
                                if "身份证号后4位" in user_info:
                                    _LOGGER.info(f"最终身份证号后4位: {user_info['身份证号后4位']}")
                            else:
                                _LOGGER.warning("未能从用户信息接口中提取到有效数据")
                            return user_info if user_info else None

                        except aiohttp.ContentTypeError as json_err:
                            _LOGGER.error(f"用户信息接口响应不是有效的JSON格式: {json_err}")
                            _LOGGER.error(f"响应内容: {response_text[:200] if 'response_text' in locals() else 'Unable to capture response'}")
                            return None
                        except Exception as parse_err:
                            _LOGGER.error(f"解析用户信息响应时出错: {parse_err}")
                            return None
                    else:
                        # 尝试获取错误响应内容
                        try:
                            error_text = await response.text()
                            _LOGGER.error(f"获取用户信息失败，状态码: {response.status}, 响应内容: {error_text[:200]}")
                        except Exception:
                            _LOGGER.error(f"获取用户信息失败，状态码: {response.status}")
                        return None

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            _LOGGER.error(f"获取用户信息时网络错误: {e}")
            return None
        except Exception as e:
            _LOGGER.error(f"获取用户信息时未知错误: {e}")
            return None

    def _search_user_info_recursively(self, data: Any, path: str = "root") -> Optional[Dict[str, Any]]:
        """递归搜索数据中的用户信息"""
        user_info = {}

        def search_recursive(obj, current_path):
            if isinstance(obj, dict):
                # 检查当前层级的字段
                for key, value in obj.items():
                    new_path = f"{current_path}.{key}"

                    # 检查身份证号字段
                    if any(id_field in key.lower() for id_field in ['sfz', 'idcard', 'identity', 'sfzm', '身份证', '证件号']):
                        if value and str(value).strip():
                            _LOGGER.info(f"递归搜索找到身份证字段: {new_path} = {str(value)[:6]}...{str(value)[-4:]}")
                            id_card = str(value)
                            if len(id_card) >= 4:
                                user_info["身份证号后4位"] = id_card[-4:]
                                user_info["完整身份证号"] = id_card
                            else:
                                user_info["身份证号后4位"] = id_card
                                user_info["完整身份证号"] = id_card
                            return True  # 找到了，停止搜索

                    # 检查姓名字段
                    if any(name_field in key.lower() for name_field in ['name', 'xm', '姓名', 'xmxx']):
                        if value and str(value).strip():
                            _LOGGER.info(f"递归搜索找到姓名字段: {new_path} = {value}")
                            user_info["姓名"] = str(value)
                            # 如果还没找到身份证号，继续搜索
                            if "完整身份证号" not in user_info:
                                search_recursive(value, new_path)
                    else:
                        # 继续递归搜索
                        if search_recursive(value, new_path):
                            return True

            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    if search_recursive(item, f"{current_path}[{i}]"):
                        return True

            return False

        _LOGGER.info(f"开始递归搜索用户信息，数据类型: {type(data)}")
        search_recursive(data, path)

        return user_info if user_info else None

    async def async_on_unload(self) -> None:
        """卸载时清理资源"""
        await self._cleanup_session()

  