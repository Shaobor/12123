# 12123 Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

Home Assistant 自定义集成，用于集成12123服务。

## 安装

### 使用 HACS（推荐）

1. 确保已安装 [HACS](https://hacs.xyz/)
2. 在 HACS 中，进入"集成"页面
3. 点击右上角的三个点，选择"自定义仓库"
4. 添加此仓库 URL：`https://github.com/Shaobor/12123`
5. 选择类别为"集成"
6. 点击"添加"
7. 在集成页面搜索"12123"并安装

### 手动安装

1. 下载此仓库
2. 将 `custom_components/12123` 文件夹复制到你的 Home Assistant `custom_components` 目录
3. 重启 Home Assistant

## 配置

在 Home Assistant 中通过 UI 配置此集成：
1. 进入"设置" > "设备与服务"
2. 点击"添加集成"
3. 搜索"12123"
4. 按照提示完成配置

## 功能

- 交通违法查询
- 驾驶证信息查询
- 机动车信息查询

## Lovelace 卡片

如果需要在仪表盘中以卡片方式展示 12123 数据，可以使用我维护的自定义卡片：[Shaobor 12123 Card](https://github.com/Shaobor/12123-card)。该卡片支持驾驶证、车辆、违章等信息的精美展示，并可通过 HACS 自定义仓库或手动方式安装。

## 调试

如果遇到问题需要调试，可以开启详细的日志记录。

### 开启 Debug 日志

在 Home Assistant 的 `configuration.yaml` 文件中添加以下配置：

```yaml
logger:
  default: info
  logs:
    custom_components.12123: debug
```

或者只针对特定模块开启：

```yaml
logger:
  default: info
  logs:
    custom_components.12123: debug
    custom_components.12123.config_flow: debug
    custom_components.12123.sensor: debug
```

保存后重启 Home Assistant，日志会输出到 Home Assistant 的日志文件中。

### 查看日志

- **通过 UI**: 设置 → 系统 → 日志
- **通过文件**: 查看 `<config>/home-assistant.log` 文件
- **通过终端**: 如果使用 Docker，可以使用 `docker logs homeassistant` 查看

### 反馈问题

反馈问题时，请提供：
1. 详细的错误日志（开启 debug 后）
2. Home Assistant 版本
3. 集成版本
4. 问题复现步骤

## 支持

如有问题或建议，请在 [GitHub Issues](https://github.com/Shaobor/12123/issues) 中提出。

## 捐赠

如果这个项目对你有帮助，欢迎捐赠支持开发！

<div align="center">

| 支付宝 | 微信 |
|:------:|:----:|
| <img src="donate_alipay.jpg" width="200" /> | <img src="donate_wechat.jpg" width="200" /> |

</div>

感谢你的支持！🙏

## 许可证

本项目采用 Apache License 2.0 许可证。

## 免责声明

本集成是第三方开发，与12123官方无关。使用本集成需要遵守相关法律法规和12123的服务条款。
