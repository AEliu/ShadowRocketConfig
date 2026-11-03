# 本次审查验证记录

日期：2026-11-03（Asia/Shanghai）。环境：Windows PowerShell、Python 3.13。基线提交：`17deec2`。本次没有连接 iPhone，没有运行远端 CI。

## 自动验证结果

| 命令/检查 | 结果 |
| --- | --- |
| `python scripts/manage.py build` | 两份配置生成成功 |
| `python scripts/manage.py check` | 快照哈希、规则格式、DNS/路由约束及输出一致性通过 |
| `python -m unittest discover -s tests -v` | **16/16 通过**，无需在线下载 |
| `python scripts/probe_dns.py` | 两个现用端点均返回有效 RFC 8484 应答，默认 TLS 证书校验开启 |
| 与 HEAD 的规则段逐字节比较 | 规则段和 Host 段不变 |
| `git diff -- rules/` | 无变化；原始快照及锁文件未改动 |
| `git diff --check`、文档链接检查 | 通过 |

新增/扩展的测试检查：IP-CIDR 接受 IPv4/IPv6、IP-CIDR6 拒绝 IPv4；DNS 主备不能意外依赖节点或退回 system；国内公网 IPv6 直连；代理/直连集合重叠时保持代理优先。下载失败、异常数据、校验失败、陈旧输出、不可变 URL、离线回滚及自定义规则保留等原有测试继续通过。

测试名称中涉及 Shadowrocket 的行为，只表示依照公开资料检查本项目允许的语法及分流意图；不代表运行了其解析器或内核。

## 规模与输出

上游提交仍为 `c68677db8fb27a5fcf466218b53c347a09e39c70`。Apple 165、Proxy 27,335、Direct 110,189、China IP 9,662，共 **147,351 条**。China IP 中 IPv4 为 6,183 条，IPv6 为 3,479 条；前一版文档的“仅 IPv4”描述已纠正。

| 输出 | 字节 | 行数 |
| --- | ---: | ---: |
| shadowrocket.conf | 2,007 | 44 |
| dist/shadowrocket-offline.conf | 5,071,577 | 147,395 |

```text
shadowrocket.conf SHA256
f8cba82a6e8590ae4d2e87473a8c8a059e25a6273e7c0e33d5790b2ccf47998c

dist/shadowrocket-offline.conf SHA256
40812c48f9c94d834bd4eee86a2162ae330890dccc2bec0ed8e8e3d14004d30e
```

本次实际比较了删 Proxy、换成同上游 GFW、域名后缀冗余，以及更小的 blackmatrix7/ACL4SSR 国内列表；结果和保留原因见 [审查记录](design.md)。没有声称当前规则数量最优，也没有把主配置行数的减少当作运行规则数减少。

## 电脑侧 DoH 探测

| 端点 | 结果 | 本次单次耗时 |
| --- | --- | ---: |
| https://223.5.5.5/dns-query | 有效应答，2 条 answer | 113 ms |
| https://doh.pub/dns-query | 有效应答，2 条 answer | 169 ms |

查询为 `example.com` 的 A 记录。结果包含运行电脑可能使用的系统/环境代理路径，不是 iPhone 直连延迟，也不是备用 DNS 时序测试。没有为测故障而修改电脑或路由器的网络设置。

## 尚待手机验证

三组检查见 [iPhone 验收](iphone-test.md)：导入与 IPv6/LAN；节点失效、主备 DNS 和冷启动；网络切换与恢复。约 15 万条规则的手机编译/内存开销、端点引导、DNS 隐私边界、IPv6-only/NAT64 仍未验证。不保证“零泄漏”或“已解决手机稳定性问题”。
