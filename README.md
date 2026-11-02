# Xiaomi-Watch-Time-Sync
After a Xiaomi/REDMI Watch/Band freezes and the date rolls back to 1970, you can restore the system time in one click with AstroBox.小米/红米 手表/手环 卡死后回滚 1970 时，可以通过AstroBox一键把系统时间写回去
# Xiaomi-Watch-Time-Sync

给小米 / REDMI 手表用的 AstroBox 插件：固件异常卡死导致 RTC 归零、表盘停在 **1970-01-01 08:00** 之后，一键把系统时间写回去。

## 为什么需要它

部分 REDMI 手表（例如 Watch 5 eSIM）自研底层 + 通信芯片占用，异常卡死后 RTC 会清零，表盘跳到 1970。官方固件没有修，手动路径只有「重连手机上的小米运动健康等它同步」，很别扭。

这个插件走 AstroBox 已经握好的 SPP 通道，直接下发一条 `system.system_time` 命令，把 PC 的当前时间写进去。

## 用法

1. AstroBox 连上手表（能列出 REDMI Watch 5/6 之类的设备即可）
2. 打开「Xiaomi-Watch-Time-Sync」
3. 点「立即同步时间」

手表没连上时点「检查设备」可以确认连接状态。

## 原理

等价于 Gadgetbridge 的 `XiaomiSystemService`：向手表发一条 Command 信封。

```
WearPacket { payload: Command }
Command {
  type = 2            // SYSTEM
  id   = 3            // CLOCK
  system {
    system_time {
      date      { year, month, day }
      time      { hour, minuter, second }
      time_zone { offset, dst_saving, id, idSpec }
      is_12_hours = false
    }
  }
}
```

AstroBox 的 `transport` 接口只透传 Xiaomi SARv2 的 protobuf 信封，不能塞原始 `BA DC FE` 字节，所以直接构造 JSON 信封交给 `transport.from_json` 编码，再由 `transport.send` 下发。

## 踩坑清单（改代码前必看）

| # | 坑 | 真相 |
|---|---|---|
| 1 | `Command.clock` | 那是闹钟 / 世界时钟，**不是**系统时间。系统时间在 `system.system_time` 下，且是扁平结构 |
| 2 | `time.minute` | 官方拼写是 **`minuter`**（多一个 r），写 `minute` 会报 `unknown field` |
| 3 | `time_zone.zoneOffset` | 实际字段是 `offset` / `dst_saving` / `id` / `idSpec`，后三个必填 |
| 4 | `offset` 语义 | 手表按 `显示 = 发送时间 + (8h - offset/8h)` 叠加。发本地时间时 `offset` 必须等于 **时区小时数 × 8**（UTC+8 → 64） |
| 5 | `transport.from_json` | WIT 里声明为 `async func`，但 componentize-py 实际同步返回 `bytes`。直接 `await` 会报 `'bytes' object can't be awaited` |
| 6 | `transport.send` 参数 | `list<u8>` 必须传 `bytes`，传 `list` 触发 `CastError` |
| 7 | manifest 权限 | 要写 `request` 和 `register_transport_recv`（WIT 函数名的下划线形式），写 `transport` 无效 |
| 8 | WASI 沙箱没有 `json` | `import json` 直接报 `No module named 'json'`，JSON 得手写字符串 |
| 9 | WASI 沙箱没有 TZ | `time.localtime()` 返回 UTC，要本地时间得 `time.gmtime(ts + offset)` |
| 10 | 日志乱码 | AstroBox 按 GBK 解码插件 stdout，**日志一律用英文**，只有 UI 文案用中文 |
| 11 | 枚举参数 | 宿主在 `from_json` 阶段就本地校验字段名，非法包不会发出去，所以试错很便宜 |
| 12 | 频繁校时 | 手表有保护，一天超过约 30 次会弹窗提示 |

## 构建

需要 `componentize-py` 0.25+：

```bash
componentize-py -d wit -w psys-world-v4 componentize app -p src -o plugin.wasm
```

产物约 19.6 MB（内嵌 CPython）。

本地安装：把 `manifest.json` / `plugin.wasm` / `icon.png` 放进 AstroBox 的插件目录（Windows 下是 `%APPDATA%\moe.astralsight.astrobox\plugins\<插件名>\`），然后完全重启 AstroBox。改过 wasm 记得删掉同目录的 `plugin.cwasm4` 缓存。

## 接口

- `api_level: 4`
- `wasi_version: 3`
- 权限：`device`、`request`、`register_transport_recv`

## 许可

MIT
