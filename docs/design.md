# 精简性与可靠性审查

审查日期：2026-11-03。目标仍为 Shadowrocket 2.2.93；电脑测试不是手机运行证明。本次保留规则源、分流顺序、快照和回滚，只简化 DNS、修复校验与文档错误。

## 规则规模：保留覆盖，不新增裁剪机制

当前固定 [Loyalsoldier/surge-rules 提交](https://github.com/Loyalsoldier/surge-rules/tree/c68677db8fb27a5fcf466218b53c347a09e39c70)：

| 集合 | 条数 | 决策 |
| --- | ---: | --- |
| Apple | 165 | 保留国内可直连例外，优先于代理集合 |
| Proxy | 27,335 | 保留与 Direct 重叠时的代理优先级 |
| Direct | 110,189 | 保留长尾国内覆盖，不以宽泛关键词替代 |
| China IP | 9,662 | 保留 6,183 条 IPv4、3,479 条 IPv6；全部 no-resolve |
| 合计 | 147,351 | 本次没有减少运行规则数 |

不能证明每一条都必要，也不能仅凭条数断言手机会慢。实际发现：

- Direct 集合中被父后缀覆盖的规则只有 158 条（约 0.14%）；Proxy 为 675 条，Apple 为 3 条。自建裁剪器收益有限，且会让手机远程规则与本地派生数据的分发更复杂。
- Proxy 与 Direct 有 115 条完全相同的规则；父后缀与子域重叠更多。不能因为 FINAL 已经代理，就认为整个 Proxy 集合冗余。
- 对当前 Apple、Proxy、Direct 及同提交 GFW 集合中的 **137,452 个不同域名值**执行相同的域名/后缀意图匹配：删除 Proxy 会改变 552 个结果；换为 4,451 条 GFW 规则会改变 433 个结果。例如删除 Proxy 会让 `adservice.google.com` 直连。这个样本比较没有覆盖所有可能子域，更不是手机流量回放。
- [blackmatrix7 China](https://github.com/blackmatrix7/ios_rule_script/tree/master/rule/Shadowrocket/China) 更小，但使用 `.cn`、`.ms` 以及 `microsoft` 等关键词；[ACL4SSR ChinaDomain](https://github.com/ACL4SSR/ACL4SSR/blob/master/Clash/ChinaDomain.list) 也包含顶级后缀和关键词。采用它们会改变匹配边界，不是无损压缩。

因此暂时保留四个集合。若手机实际出现编译慢/内存问题，应以真实连接日志选择更小集合并验收；本次没有这些证据，不引入第二套规则配置或裁剪框架。

顺序不变：自定义 → LAN → Apple 例外 → Proxy → Direct → China IP → FINAL,PROXY。IP 规则使用 `no-resolve`，避免为未知域名的归属判断触发本地解析。未知国内域名仍可能代理；修正具体误判用自定义规则。此前“cncidr 仅覆盖 IPv4”的描述错误，已纠正并补入国内公网 IPv6 样例测试。

## DNS：独立于节点的两级加密解析

旧方案的默认 Cloudflare 和备用 Google 都带 `#proxy`，依赖同一节点。它们可处理解析器自身故障，却不能处理节点故障；DIRECT 解析超时后也会落到这个依赖。另设两组国内 DNS 又增加了引导和故障路径。

现改为：

```ini
dns-server = https://223.5.5.5/dns-query#no-h3
fallback-dns-server = https://doh.pub/dns-query#no-h3
```

删除 `direct-dns-server`、`proxy-dns-server`，让普通直连解析和节点域名解析使用 DNS 覆写。根据 [LOWERTOP 手册](https://github.com/LOWERTOP/Shadowrocket/blob/9ff0cc1564d528b9e77a863b39fc443b08cf98ae/README.md)，普通代理目标仍由节点解析；这不等于所有查询类型都由节点处理。保留 Fake-IP、`always-ip-address=false`、IP 规则的 `no-resolve`，不主动要求代理域名先在国内解析。

| 场景 | 配置意图及限制 |
| --- | --- |
| 正常国内访问 | 国内加密 DNS；保持国内 CDN 解析视角 |
| 节点失效 | 国内 DNS 不依赖节点，应继续直连；国外业务失败，不能自动直连 |
| 主 DNS 失败/超时 | 切换 DNSPod DoH，不改变 DIRECT 策略，不留空回退 system |
| 冷启动 | 主 DNS 的 IP URL 不需要先解析端点域名；节点名称经该 DNS 解析 |
| 备用 DNS 引导 | `doh.pub` 仍需要解析，实际缓存/系统引导行为待手机抓包；不固定其历史 IP |
| 两家 DNS 都不可达 | 接受解析失败，不通过配置主动增加明文 DNS 或代理依赖 |

主端点已在电脑上以默认 TLS 证书验证完成实际 RFC 8484 查询；这只能证明当次端点可用，不能证明 iOS 的故障切换时序。IP URL 在 IPv6-only/NAT64 环境的可用性也不能从双栈测试推断。

**隐私取舍：**客户端额外产生的 TXT/SRV 等查询、无法交节点解析的协议路径，可能经国内 DoH 查询。DoH 加密传输并不向解析器隐藏域名。此方案选择减少节点耦合、稳定国内访问，不再把“所有默认查询经代理”作为保证；也不设 `allow-dns-all=false`，以免损害服务发现。`allow-dns-svcb=false` 保留 Fake-IP 兼容意图，HTTPS/SVCB 的具体处理需实测。

保留 `dns-direct-system=false`、`dns-direct-fallback-proxy=false`、UDP 不支持时 REJECT。它们不能构成 VPN kill switch。仅劫持配置列出的公共 DNS 的 53 端口；LAN、未列出的硬编码 DNS、应用自带 DoH 和 VPN 关闭期间仍有独立路径。

## 参数兼容性：有依据的保留，运行行为另验收

| 参数 | 核实结果 | 本次处理 |
| --- | --- | --- |
| `IP-CIDR6` | [开发者频道 2.2.33 日志](https://t.me/ShadowrocketNews/424) 明确记载 IPv6 规则保存修复；[dler-io 配置](https://github.com/dler-io/Rules/blob/main/Shadowrocket/Complete.conf) 也使用它 | 目标 2.2.93 保留；未声称手机编译已通过 |
| `IP-CIDR` 搭配 IPv6 | LOWERTOP 手册明确表示此类型可匹配 IPv4 或 IPv6；blackmatrix7 的 Shadowrocket 输出也如此 | 修复校验器仅接受 IPv4 的错误；仍拒绝 IP-CIDR6 搭配 IPv4 |
| `always-real-ip` | [开发者频道 2.1.62 日志](https://t.me/ShadowrocketNews/320) 记录加入支持，[2.1.78 日志](https://t.me/ShadowrocketNews/343) 记录修复 | 保留 LAN 范围，不替换成布尔值或全局通配符 |

版本记录证明功能早于目标版本存在，不证明当前版本没有回归，也不保证每个通配符与 mDNS 路径都正常。`always-real-ip` 只要求返回真实地址，**不会自动发现内网 DNS**。`.home.arpa` 仍需实际 Host/内网解析服务；`.local` 的 Bonjour 与普通单播 DNS 也不是同一路径。

开发者入口为 [shadowlaunch.com](https://shadowlaunch.com/) 和 [App Store](https://apps.apple.com/us/app/shadowrocket/id932747118)。LOWERTOP 是非官方参数手册。本次直接读取了上述开发者 Telegram 消息；没有把第三方下载站当作官方依据。

## 工程机制：保留与可靠性直接相关的部分

仍只有 Python 标准库脚本：固定提交下载、保存原始字节和 SHA256、校验后选择锁文件、构建两种输出、离线回滚。快照有实际作用：上游 release 可能重建历史，旧 SHA 的远程文件不保证永久存在；Git 历史不能替代手机首次下载的可达性。

不增加自动更新服务、规则转换框架或配置模式。只删去 CI 构建后重复的 `check`：构建前检查追踪文件是否陈旧，构建本身验证内容，构建后用 Git diff 检查可重复性；故障注入和回滚测试保留。

快照不自动清理；多次更新会增长磁盘和 Git 体积。更新/构建不得并发，多个输出不是跨文件事务，异常中断后重建即可。哈希不等于上游签名；手机远程下载也不会核验本项目 manifest，需确切字节时使用离线版。

验收只保留 [三组手机检查](iphone-test.md)。电脑结果见 [验证记录](verification.md)。
