# 第三方规则

`snapshots/<commit>/{apple,proxy,direct,cncidr}.txt` 是从
[Loyalsoldier/surge-rules](https://github.com/Loyalsoldier/surge-rules)
对应提交的 `ruleset/` 目录下载的原始文件，未改写、未合并。
每个目录的 `manifest.json` 记录提交、SHA256 和有效规则条数。

上游采用 GNU GPL v3，许可证原文保存在 `LICENSE-Loyalsoldier`；
源仓库、生成脚本、致谢和底层数据来源可在上游查阅。
本项目记录的初始快照为 `c68677db8fb27a5fcf466218b53c347a09e39c70`。
许可文本下载自上游 master/LICENSE（2026-11-03）。

上游说明其数据来自 v2ray-rules-dat、v2fly/domain-list-community、
felixonmars/dnsmasq-china-list、17mon/china_ip_list 等项目。
本项目不声称拥有第三方规则；再次分发时保留相应声明与许可证。

离线生成配置会为原始规则补充 DIRECT/PROXY 策略，并为 IP 规则补充
no-resolve。分发这个派生文件时，请同时提供本说明、许可证和对应规则快照，
不要只分发一个去掉来源的规则文件。规则分类最终以上游维护者判断为准。
