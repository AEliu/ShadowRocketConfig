# 自动验证记录

日期：2026-11-03（Asia/Shanghai）。运行环境：Windows PowerShell、Python 3.13。没有连接 iPhone，也没有在 Shadowrocket 内导入/编译配置。GitHub Actions 已配置，远端尚未运行。

## 已执行

| 验证 | 结果 |
| --- | --- |
| 下载固定提交的实际规则 | 4 份均成功；保存原始字节与 SHA256 |
| `python scripts/manage.py update` | 成功查询 release 分支；与已锁定提交一致，使用核验后的本地快照 |
| `python scripts/manage.py build` | 生成精简版和离线版 |
| `python scripts/manage.py check` | 通过：规则语法、数据完整性、关键 DNS/路由约束、输出与源文件一致性 |
| `python -m unittest discover -s tests -v` | **15/15 通过**，无需网络 |
| 再次渲染与输出逐字节对照 | 两份输出完全一致 |
| `python scripts/probe_dns.py` | 4/4 端点返回有效 RFC 8484 A 记录响应；保持默认 TLS 证书验证 |

规则提交：`c68677db8fb27a5fcf466218b53c347a09e39c70`。

| 集合 | 有效条数 |
| --- | ---: |
| Apple 国内直连例外 | 165 |
| Proxy | 27,335 |
| Direct | 110,189 |
| China IPv4 | 9,662 |
| 合计 | 147,351 |

主配置：46 行、2,186 字节。离线配置：147,397 行、5,071,756 字节（约 4.84 MiB）。这些数字只对应本记录中的配置和快照。

输出 SHA256：

```text
shadowrocket.conf
3211d99e64effc3e111cd4c7101018a56a6244ce2db43adb793c43eaa6c2be05

dist/shadowrocket-offline.conf
a6a679cf0c2a7b7a5d7106c67b38edff353e02cd1c64fd737e4bdc3888e17b01
```

## 自动测试覆盖

- 更新 → 构建 → 回滚全过程；回滚不联网并保留自定义规则。
- 中途下载失败不切换活动锁文件、不改变已生成主配置。
- HTML 错误页、嵌入策略、FINAL 注入、未知规则类型被拒绝。
- 规则数量变化超过 30% 时停止切换，显式覆盖后可继续。
- 规则哈希损坏阻止构建和回滚。
- 生成文件陈旧、路径穿越或非完整 SHA 被识别。
- 分支只解析一次，后续文件均使用同一不可变提交 URL；重复更新验证已有快照。
- 禁止意外系统 DNS、IP 规则触发解析、Fake-IP 网段旁路、最终直连等关键回归。
- 实际快照的国内域名、Apple CDN、国外域名、未知域名、后缀边界、LAN/IPv6 LAN、字面 IP 与精简/离线顺序。

测试中的小型规则匹配器是项目意图模型，不能替代 Shadowrocket 的规则编译、DNS 缓存、CNAME、IPv6、UDP 或 TUN 实现；故障注入使用临时目录与受控假下载响应，没有故意破坏真实快照。

## DoH 网络探测

| 端点 | 结果 | 单次耗时 |
| --- | --- | ---: |
| `dns.alidns.com` | 有效应答，2 条 answer | 256 ms |
| `doh.pub` | 有效应答，2 条 answer | 3,287 ms |
| `1.1.1.1` | 有效应答，2 条 answer | 1,008 ms |
| `8.8.8.8` | 有效应答，2 条 answer | 2,014 ms |

查询域名为 `example.com`。结果代表运行电脑及其系统/环境代理路径，不代表 iPhone 国内直连延迟，不能据此给解析器做速度排名，也不能证明 `#proxy` 在手机生效。DNSPod 此次超过 2 秒，说明备用路径必须纳入手机测试，不能只验证正常情况。

## 尚未验证

手机导入与规则编译、约 15 万条离线规则的内存/启动开销、各 DNS 参数在实际版本的交互、UDP/TCP DNS 劫持、冷启动引导、外层抓包、国内 CDN 调度、节点远端解析、IPv6-only/NAT64、Bonjour/AirPlay、锁屏与 Wi-Fi/蜂窝切换，以及实机更新/回滚行为均未验证。执行方法见 [iPhone 验收步骤](iphone-test.md)。
