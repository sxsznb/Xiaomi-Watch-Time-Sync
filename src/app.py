"""1970 同步器 - AstroBox Level 4 插件

通过 AstroBox 的 transport 通道给小米 / REDMI 手表写系统时间。
适用于固件异常卡死后 RTC 归零、表盘停在 1970-01-01 08:00 的场景。

协议（等价于 Gadgetbridge 的 XiaomiSystemService）：
    Command {
      type = 2,          // SYSTEM
      id   = 3,          // CLOCK
      system {
        system_time {
          date       { year, month, day }
          time       { hour, minuter, second }
          time_zone  { offset, dst_saving, id, idSpec }
          is_12_hours = false
        }
      }
    }

日志一律用英文：AstroBox 按 GBK 解码插件 stdout，中文会变成乱码。
UI 文案才用中文。
"""
import time

import wit_world
from wit_world import exports
from wit_world import imports

LOG = []
MAX_LOG = 20


def log(msg):
    s = str(msg)
    if len(s) > 140:
        s = s[:140] + "..."
    LOG.append(s)
    if len(LOG) > MAX_LOG:
        LOG.pop(0)
    print(s, flush=True)


# ---------- 时间计算 ----------

def wall_clock(ts=None, tz_min=480):
    """本地墙上时间 (year, month, day, hour, minute, second)。

    沙箱里没有 TZ，time.localtime() 返回 UTC，所以显式平移 tz_min 分钟。
    """
    if ts is None:
        ts = time.time()
    lt = time.gmtime(ts + tz_min * 60)
    return (lt.tm_year, lt.tm_mon, lt.tm_mday, lt.tm_hour, lt.tm_min, lt.tm_sec)


def clock_json(tz_name="Asia/Shanghai", tz_min=480, ts=None):
    """生成 system.system_time 的 JSON —— 手写，沙箱没有 json 模块。"""
    y, mo, d, h, mi, s = wall_clock(ts, tz_min)
    # 实测规律：手表显示 = 发出去的 date/time + (8h - offset/8h)
    #   offset=0  -> +8h    offset=32 -> +4h    offset=64 -> +-0h
    # 既然发的已经是本地时间，要让附加量为 0，offset 得等于「时区小时数 x 8」
    z = (tz_min // 60) * 8
    return (
        '{"type":2,"id":3,"system":{"system_time":{'
        '"date":{"year":%d,"month":%d,"day":%d},'
        '"time":{"hour":%d,"minuter":%d,"second":%d},'
        '"time_zone":{"offset":%d,"dst_saving":0,"id":"%s","idSpec":""},'
        '"is_12_hours":false}}}'
    ) % (y, mo, d, h, mi, s, z, tz_name)


# ---------- 设备与发送 ----------

async def connected_addr():
    """返回第一台已连接设备的地址，没有则返回 None。"""
    try:
        devs = await imports.device.get_connected_device_list()
        if devs:
            return devs[0].addr
        all_devs = await imports.device.get_device_list()
        log("no connected device, known=%d" % len(all_devs))
    except Exception as e:
        log("get device failed: %s" % e)
    return None


async def push_time(addr):
    """把当前时间编码后推给手表。"""
    P = imports.transport.Protocol.XIAOMI_VELA_V5_PROTOBUF
    raw = imports.transport.from_json(P, clock_json())
    if hasattr(raw, "__await__"):
        raw = await raw
    log("encoded %d bytes" % len(raw))
    n = len(raw)
    await imports.transport.send(addr, bytes(raw))
    return n


# ---------- UI ----------

STATUS = "就绪"
RENDER_TARGET = "main"


def make_ui():
    ui = exports.ui

    root = ui.Element(ui.ElementType.DIV, None)
    root.flex()
    root.flex_direction(ui.FlexDirection.COLUMN)
    root.padding(10)
    root.bg("#1b1b1f")
    root.radius(8)

    title = ui.Element(ui.ElementType.SPAN, "1970 同步器")
    title.text_color("#ffffff")
    title.prop("font-size", "13px")
    title.margin(4)
    root.child(title)

    def button(label, eid):
        b = ui.Element(ui.ElementType.BUTTON, label)
        b.margin(3)
        b.child(ui.Element(ui.ElementType.SPAN, label))
        b.on(ui.Event.CLICK, eid)
        root.child(b)

    button("立即同步时间", "btn_sync")
    button("检查设备", "btn_check")

    line = ui.Element(ui.ElementType.SPAN, STATUS)
    line.text_color("#9be7a0")
    line.prop("font-size", "10px")
    line.margin(4)
    root.child(line)

    for entry in LOG[-6:]:
        t = ui.Element(ui.ElementType.SPAN, entry)
        t.text_color("#9aa4b2")
        t.prop("font-size", "10px")
        root.child(t)

    return root


def render():
    exports.ui.render(RENDER_TARGET, make_ui())


# ---------- 回调 ----------

class Lifecycle(wit_world.exports.Lifecycle):
    async def on_load(self):
        log("plugin loaded")


class Event(wit_world.exports.Event):
    async def on_event(self, event_type, event_payload):
        # 手表上报数据时顺手校一次时（重连、醒来都会触发）
        if "TRANSPORT_PACKET" in str(event_type):
            try:
                addr = await connected_addr()
                if addr:
                    await push_time(addr)
                    log("auto sync done")
            except Exception as e:
                log("auto sync failed: %s" % e)
        return ""

    async def on_card_render(self, card_id):
        pass

    async def on_ui_render(self, element_id):
        global RENDER_TARGET
        RENDER_TARGET = element_id
        render()

    async def on_ui_event(self, event_id, event, event_payload):
        global STATUS
        try:
            if event_id == "btn_sync":
                addr = await connected_addr()
                if not addr:
                    STATUS = "没有已连接的设备"
                else:
                    n = await push_time(addr)
                    y, mo, d, h, mi, s = wall_clock()
                    STATUS = "已同步 %04d-%02d-%02d %02d:%02d:%02d（%d 字节）" % (
                        y, mo, d, h, mi, s, n)
            elif event_id == "btn_check":
                addr = await connected_addr()
                STATUS = ("已连接 " + addr) if addr else "没有已连接的设备"
            log(STATUS)
        except Exception as e:
            STATUS = "出错 %s" % e
            log("error: %s" % e)
        render()
        return ""
