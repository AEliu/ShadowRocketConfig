# Shadowrocket 精简分流配置

国内常用服务直连，国外及未匹配流量代理。主配置只有约 50 行；节点、订阅和密码由 Shadowrocket App 管理，不放入仓库。开发与维护只需要 Python 3.10+，无第三方 Python 包、数据库或后台服务。

基于 2026-11-03 查阅的文档，目标版本为 **Shadowrocket 2.2.93 或更新版本**。这是项目选定的验证基线，并非所有参数的最低支持版本。当前只完成电脑侧验证，**尚未在 iPhone 导入或实测**。

## 使用

1. 在 App 内添加自己的节点，选中一个可用节点；配置中的内置 `PROXY` 使用首页选中的节点。
2. 首次使用推荐从“文件”/iCloud 导入生成的 `dist/shadowrocket-offline.conf`，它已经包含规则，无需手机下载 GitHub 数据。重新生成：

   ```powershell
   python scripts/manage.py build
   python scripts/manage.py check
   ```

3. 如果手机能访问 GitHub Raw，也可导入根目录的 `shadowrocket.conf`。进入配置详情确认 **4 个规则集** 均下载并编译成功；首次下载失败时不要继续依赖这个配置，改用离线版。需要代理才能下载时，临时切换“全局路由 → 代理”，下载完成后恢复“配置”。
4. 选中导入的配置，首页“全局路由”设为 **配置**，连接 VPN。不要同时启用改变 DNS/规则的模块；模块可能优先于本配置。
5. 按 [iPhone 验收步骤](docs/iphone-test.md) 检查分流、DNS、局域网与网络切换。

两种输出使用同一组规则、相同顺序。离线版体积较大，手机编译耗时和内存仍需实测。导入后不要依赖自动更新跟进上游：精简版 URL 已锁定提交，离线版本身就是快照。

## 文件分工

| 文件 | 用途 |
| --- | --- |
| `config/base.conf` | DNS、TUN 与规则顺序模板，日常不必修改 |
| `rules/custom.list` | 自定义规则，优先于上游规则 |
| `config/hosts.conf` | 局域网固定地址或指定内网 DNS |
| `rules/lan.list` | 少量局域网基础规则 |
| `rules/lock.json` | 当前使用的上游提交 |
| `rules/snapshots/<SHA>/` | 未改写的上游数据、SHA256 与条数，纳入 Git |
| `shadowrocket.conf` | 可导入的精简配置，生成文件，纳入 Git |
| `dist/shadowrocket-offline.conf` | 可重新生成的离线配置，不纳入 Git |
| `scripts/manage.py` | 更新、构建、校验、离线回滚 |

## 自定义

修改 `rules/custom.list`，例如：

```ini
DOMAIN,downloads.example.com,DIRECT
DOMAIN-SUFFIX,example.org,PROXY
DOMAIN,ads.example.net,REJECT
IP-CIDR,203.0.113.8/32,PROXY,no-resolve
```

支持 `DOMAIN`、`DOMAIN-SUFFIX`、`DOMAIN-KEYWORD`、`IP-CIDR`、`IP-CIDR6`，策略限 `DIRECT / PROXY / REJECT`。IP 规则必须带 `no-resolve`。不支持向这里插入 `FINAL`、远程配置、脚本或任意策略组。

NAS 等优先使用 IP 或 Bonjour 的 `.local` 名称。`home.arpa` 并不自带 DNS 服务：如路由器没有提供适用的本地解析，给 `config/hosts.conf` 添加 `nas.home.arpa = 192.168.1.10`。其他内网域名同时添加 DIRECT 规则及 `office.example.com = server:192.168.1.1`，仅在该内网下使用；不要把所有域名交给路由器。单标签主机名、企业搜索域与 Tailscale MagicDNS 不在默认支持范围。

修改后执行 `build`、`check`，重新导入手机并切换到新配置。不要直接编辑生成文件，否则下次构建会覆盖。TUN 旁路的局域网流量不会进入规则引擎，因此自定义 PROXY 规则不能覆盖这些旁路路由。

## 独立更新规则

```powershell
python scripts/manage.py update
python scripts/manage.py build
python scripts/manage.py check
python -m unittest discover -s tests -v
git diff -- rules/lock.json shadowrocket.conf
git status --short
```

每个命令成功后再执行下一步。`update` 只选择新的规则快照，不修改配置逻辑、自定义规则或手机当前配置；`build` 才生成输出。下载使用 HTTPS、超时及大小限制，所有规则验证成功后才原子替换锁文件。每类规则数量变化超过 30% 时拒绝切换：检查新快照和上游变更后，可用 `update --revision <完整SHA> --allow-large-change` 接受。这个阈值只能发现明显异常，无法保证上游分类正确。

不要同时运行多个更新/构建进程。输出文件分别原子替换，不提供跨文件事务；若中途断电，重新 `build`、`check` 即可恢复一致性。审阅新增快照后将配置与数据一起纳入自己的 Git 提交；本项目不会代你自动提交、推送、发布或删除旧版本。

## 回滚

查看 `rules/snapshots/` 中已有版本。初始版本：`c68677db8fb27a5fcf466218b53c347a09e39c70`。

```powershell
python scripts/manage.py rollback c68677db8fb27a5fcf466218b53c347a09e39c70
python scripts/manage.py build
python scripts/manage.py check
```

回滚完全离线，先核验旧快照，保留当前自定义规则与配置逻辑。然后重新导入手机；仓库回滚不会遥控手机。完整配置逻辑回滚使用 Git 恢复 `config/`、`rules/custom.list`、`rules/lan.list` 和对应锁文件后重建。初始仓库尚无历史提交，完整历史需要自行提交后才存在。

快照不自动清理，以便离线回滚。上游 release 分支可能重建历史，固定 SHA 的远程 URL 不保证永久可达；仓库中保留的原始规则可继续生成离线版。

## 验证与设计依据

```powershell
python scripts/manage.py check
python -m unittest discover -s tests -v
# 可选：实际网络请求，结果只代表运行脚本的电脑
python scripts/probe_dns.py
```

已有离线 GitHub Actions 校验流程，未在远端运行。规则匹配测试是本项目支持子集的意图检查，不是 Shadowrocket 内核或其编译器。

- [设计取舍、文档与规则来源](docs/design.md)
- [iPhone 验收方法](docs/iphone-test.md)
- [实际自动验证记录](docs/verification.md)
- [第三方规则与许可说明](rules/NOTICE.md)
