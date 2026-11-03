# 设计依据与边界

研究日期：2026-11-03。仓库原先为空，因此没有沿用既有配置。

## 资料可信度

- [Shadowrocket 开发者网站](https://shadowlaunch.com/) 与 [App Store 页面及更新日志](https://apps.apple.com/us/app/shadowrocket/id932747118) 用于核对开发者、功能和版本。开发者网站没有完整的公开参数手册。2.2.92 更新说明出现直连域名独立 DNS，2.2.93 涉及隧道路由与本地排除，本项目采用 2.2.93 为验收基线。
- 详细字段依据 [LOWERTOP/Shadowrocket 使用手册](https://github.com/LOWERTOP/Shadowrocket/blob/9ff0cc1564d528b9e77a863b39fc443b08cf98ae/README.md) 和 [配套配置](https://github.com/LOWERTOP/Shadowrocket/blob/main/lazy.conf)。这是明确声明为**非官方**、依据官方群组关键词与社区反馈维护的手册，不能替代设备行为验证。未把搜索结果中自称“官方”的第三方下载站当作依据。
- [Loyalsoldier/surge-rules](https://github.com/Loyalsoldier/surge-rules) 提供清楚的域名/IP 分类和生成流程；检查到 release 提交 `c68677db8fb27a5fcf466218b53c347a09e39c70`，提交时间为 2026-11-02 22:32:13 UTC（北京时间 11 月 3 日 06:32）。
- 也检查了 [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script/tree/master/rule/Shadowrocket)：服务级细分丰富，但本项目不需要大量分类。查询的 `China.list` 最近文件提交是 2026-06-21，不能据此推断整个项目停止维护；本次选择更新更近、统一来源的 Loyalsoldier 四个集合，不混合多个大集合。
- DoH 地址参考 [阿里云 DoH 文档](https://static-aliyun-doc.oss-cn-hangzhou.aliyuncs.com/download%2Fpdf%2F171662%2FAPI_Reference_intl_en-US.pdf)、[DNSPod 公告](https://docs.dnspod.cn/notices/mian-fei-ban-dot-dohbu-zai-gong-kai-ipjie-ru-de-gong-gao/)、[Cloudflare 文档](https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/)、[Google 文档](https://developers.google.com/speed/public-dns/docs/doh/)。四个配置端点另外做了实际 RFC 8484 查询，TLS 校验保持开启。

## 分流逻辑

顺序为：自定义 → 局域网 → Apple 国内可直连例外 → 代理域名 → 国内可直连域名 → 国内 IPv4 字面地址 → 最终代理。规则数据使用上游 `ruleset/*.txt`，不把纯域名的 DOMAIN-SET 文件误用为 RULE-SET。

主配置引用不可变提交，离线配置展开同样的列表。Apple 例外先于代理集合，是因为后者包含 `apple.com` 等宽泛后缀；不对全部 Apple、iCloud、Microsoft 服务做宽泛直连。国内直连指维护者分类的可直连服务，绝非按公司国籍或 `.cn` 后缀粗分。

IP 规则统一 `no-resolve`，不为了判断“是否中国 IP”先在本地解析未知国外域名。不采用会触发解析的 `GEOIP,CN,DIRECT`，也不依赖手机内置 GeoIP 数据库版本。结果是：未被域名集覆盖的国内域名会代理，即便它实际上部署在国内；可通过自定义 DIRECT 修正。国内 IPv6 字面 IP 未由上游 cncidr 集合覆盖，也默认代理。这是可重复、少泄漏优先的有意取舍。

Shadowrocket 手册说明模块可优先于配置，编译过程还会处理显式规则、域名与 IP 规则的优先关系。离线测试只检查本项目明确支持的子集；自定义跨类型冲突、同一域名多种规则类型、CNAME 及编译器重排必须在手机检查，不声称通用线性模拟等价。

不添加广告集合、HTTPS 解密、重写脚本、测速分组或地区节点筛选。首页选择可用节点即可，避免为了节点切换引入配置耦合；需要自动故障切换时，先验证节点与 App 的回退机制，再自行启用。配置本身不提供可用节点，也不是 VPN kill switch。

## DNS 与 Fake-IP

Fake-IP 是客户端把虚拟 IP 映射回域名的机制，并不代表 DNS 查询天然加密。保持 Shadowrocket 默认 Fake-IP 行为，不写入 Clash 的 `fake-ip-range`、`enhanced-mode` 或 TUN 字段。`always-ip-address=false` 避免强制所有域名本地解析；`always-real-ip` 只保留 localhost、`.local`、`.home.arpa` 兼容例外。

| 路径 | 设计意图 | 取舍 |
| --- | --- | --- |
| 命中 DIRECT 的域名 | `direct-dns-server` 使用阿里/DNSPod DoH 直连，并行取先返回者 | 保留中国网络视角，帮助国内 CDN；不是运营商权威调度保证 |
| 代理目标域名 | 通常把域名交给代理节点解析 | 节点解析器由服务端控制，未必是 Cloudflare/Google |
| 需由客户端执行的默认 DNS | `dns-server` 为 Cloudflare DoH，`#proxy` 经首页选中节点 | 避免默认查询直接送本地公共 DNS；仍需实测所有查询类型 |
| 覆写/直连 DNS 失败 | 显式 Google DoH `#proxy` 备用 | 不留空、不填 system；国内 DNS 故障时 CDN 可能变为海外结果 |
| 代理节点的域名 | `proxy-dns-server` 使用国内 DoH | 避免“连接节点需要先通过节点解析”的启动循环 |

`dns-direct-system=false` 不主动把 DIRECT 域名交系统 DNS；`dns-direct-fallback-proxy=false` 不在解析失败后改变业务流量的 DIRECT 策略，这与备用 DNS 自身走代理是两回事。节点失效时普通代理业务应失败，不能悄悄直连；不支持 UDP 的代理策略设为 REJECT，代价是部分实时通信可能失败。

不把 DNSPod 免费 DoH 固定到历史 IP，其公告已提示不再提供公开 IP 接入。国内 DoH 使用主机名，首次引导解析仍可能由系统进行；预期允许暴露的范围是解析器主机名，而非国外业务域名。不能仅凭配置证明这个范围：需要冷启动抓包，尤其是节点域名的引导顺序。海外 DoH 使用经 TLS 实测有效的 IP URL，减少这一路的引导依赖。国内端点禁用 H3 自动升级，降低受限 UDP 网络的变量。

保留非 A/AAAA 查询支持，避免全局 `allow-dns-all=false` 破坏 TXT/SRV 服务发现。设置 `allow-dns-svcb=false` 维持 Fake-IP 兼容行为，可能失去 HTTPS/SVCB 的服务提示及部分 ECH 自动发现收益；不同版本两参数的交互需实测。不能把 TXT/SRV 或应用自带 DoH 的行为推断成 A/AAAA 的行为。

仅接管列出的常见公共 DNS IP 的 53 端口，不使用全局 `hijack-dns=*:53`，避免对局域网 DNS 强行改写。未列出的硬编码 DNS、应用内 DoH/DoT、系统服务、VPN 未启用期间和旁路网络仍可能产生额外查询。全机“零 DNS 泄漏”不在当前可证明范围。

## TUN 与局域网

`skip-proxy` 的含义不是绕过 VPN：它主要让兼容性流量交给 TUN 处理；真正的 IP 旁路来自 `tun-excluded-routes`。本配置只排除私网、回环、链路本地及组播/广播，保留 Bonjour/mDNS 和 LAN 设备发现路径；不照搬大量公网/测试地址排除，也不排除 Fake-IP 的 `198.18.0.0/15`。

IPv6 保持开启，优先 IPv4；关闭 IPv6 DNS 不等于物理接口不发 IPv6，不能靠 `ipv6=false` 声称防泄漏。包含 IPv6 LAN 地址及组播旁路，公网 IPv6 交给隧道和分流。IPv6-only/NAT64 网络、不同协议的 UDP 域名转发、APNs、锁屏恢复需专门验收。

`private-ip-answer=true` 允许私网解析结果，以支持 split DNS/NAS。它同时放宽了对私有应答的防劫持判断；公共域名解析到私网的情况应审查。保留 LAN 旁路意味着局域网 IP 和路由器 DNS 可在隧道外通信，这是可用性取舍，不是全设备封闭隧道。

未默认排除 `100.64.0.0/10`，避免干扰 Tailscale 等覆盖网络；没有启用 Tailscale 模组。企业 VPN、CGNAT 管理入口、自定义内网域名或其他本地路由需结合实际网络单独配置。手机“包含所有网络/强制路由/排除本地网络”等开关可能改变结果，验收时要记录实际设置，不能只看本配置。

## 更新与供应链

固定同一上游提交下载所有文件，保存原始字节、SHA256、规则数，校验后才切换锁文件。已存在的快照再次验证，不静默覆盖；网络失败、HTML 错误页、格式变化、嵌入策略、空文件或明显条数异常会阻止激活。上游新增规则语法时应先评估兼容性再扩展校验器，而不是静默忽略。

哈希提供快照完整性与可重复性，不是上游真实性签名，也无法阻止合法 HTTPS 源被攻陷后发布合理格式的恶意分类。精简版由手机自行下载规则，手机不会校验本项目 manifest 的 SHA256；要使用已核验的确切字节，导入离线版。两种模式都依赖 Shadowrocket 自己正确编译规则。

快照独立于配置逻辑，回滚不依赖上游保留历史。Git 管理源文件和快照；不增加自动定时更新、不自动发布服务，不为了几份配置引入框架或依赖管理器。
