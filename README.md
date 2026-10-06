# NotifyHub

Windows 登录后驻留的托盘通知网关，内部使用 Python + PowerShell，业务 hook 默认留空。
支持 UDP 请求触发 ntfy、edge-tts 语音播报和 Windows Toast。

## 从克隆开始部署

```powershell
git clone <仓库地址> NotifyHub
cd NotifyHub
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -PythonExecutable <本机Python绝对路径> -Topic <ntfy话题>
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1
```

需要 Windows 10/11、Python 3.11+、互联网（ntfy 和 edge-tts）。setup 创建独立 .venv，安装锁定依赖，生成 config/local.toml 和随机 UDP 密钥，注册通知身份及开始菜单快捷方式。安装不会开启自启动。
之后修改 config/local.toml；setup 重复执行保留已有配置和密钥。

相对路径以配置文件为基准，`${NAME}` 展开环境变量。基础解释器路径仅记录在忽略的本地配置中。源码不包含本机路径、IP、topic 或凭据。
迁移后重建 .venv、生成新的本地配置并注册通知身份；不要复制旧 .venv。迁移完成后重新勾选自启动以更新启动项。运行数据默认位于 %LOCALAPPDATA%/NotifyHub，源码目录可以移动。

## 调用

```powershell
powershell -File scripts/notify.ps1 -Method windows -Title "任务完成" -Text "备份成功" -Wait
powershell -File scripts/notify.ps1 -Method ntfy -Text "备份成功" -Wait
powershell -File scripts/notify.ps1 -Method speech -Text "备份已经完成" -Wait
```

Linux/WSL/其他主机仅需要 Python 标准库客户端：

```sh
python3 client/notify.py --host 127.0.0.1 --method windows --text "来自 WSL" --wait
python3 client/notify.py --host <Windows或Tailscale地址> --secret-file <安全分发的密钥文件> --method speech --text "来自其他主机" --wait
```

WSL 镜像网络优先测试 127.0.0.1，无法连接时检查实际网络模式、主机地址和防火墙。
远程必须携带 HMAC；通过文件提供密钥，不在命令行传密钥内容。ntfy 接收端订阅同一个 server/topic。
公共 ntfy 话题默认公开；根据用途配置受保护话题和 token。

## UDP 协议

```json
{"v":1,"id":"unique-id","method":"windows","content":{"title":"任务完成","text":"备份成功"}}
```

method 为 ntfy、speech、windows，title 可省略，text 非空。UTF-8 报文包含签名后最多 1200 字节。
`{"v":1,"id":"unique-id","op":"status"}` 查询结果，op=ping 检查服务。
远程签名：增加 Unix 秒 ts，去掉 auth 后按键排序、无空格、ensure_ascii=false 编码为 UTF-8；使用密钥字符串的 UTF-8 字节计算 HMAC-SHA256 hex，写入 auth。默认允许时钟误差 120 秒。
客户端使用同一 id 重试入队请求，再轮询最终状态。相同 id/不同内容拒绝；重启时未完成任务标记 interrupted，不自动重播。状态默认保存 24 小时；去重窗口到期，相同 id 可能再次执行。

状态：accepted、running、completed、failed、interrupted、rejected。
ntfy completed 表示服务器接受消息；Windows completed 表示 API 接受提交，勿扰模式可能阻止弹窗；speech completed 表示播放结束且音频已删除。
无确认时不要换新 id 立即重试，以免重复通知。ntfy 不自动重试结果不确定的发布。

## 托盘和生命周期

菜单提供三种测试通知、最近请求、日志、配置、登录自启动、后台重启、帮助和退出。
修改配置后使用 Reload / restart background。先校验本地配置和密钥，再停止后台。数据目录变更需退出后启动。
后台异常最多每 60 秒尝试三次重启。图标提示文字显示 Running / Starting / Stopped。
退出关闭 UDP、停止子进程并清理语音临时目录；自启动设置保留。重启中断当前语音，不重播。
Job Object 在托盘异常退出时终止后台及其子进程；下次启动清理遗留音频。
自启动通过 HKCU Run 在当前用户登录后执行；未登录时不接收消息。

## 代理与音频

ntfy.direct=true 使用 httpx trust_env=false，关闭代理继承。
speech.direct=true 在独立语音子进程清除代理环境变量并设置 NO_PROXY=*，绕过 Windows 注册表代理发现。父进程环境不受影响。
直连失败时返回失败，不自动回退代理。这不绕过 VPN/TUN 等系统路由。语音内容发送到在线 TTS 服务。
语音串行播放，ntfy 和 Windows 独立队列不会被语音阻塞。
MP3 使用 Windows MCI 播放，无需 mpv 或 Edge 浏览器。合成与播放分别有超时；finally 清理，强制退出后下次启动清理带 ownership 标记的目录。

## 网络与防火墙

默认 IPv4 0.0.0.0:39393；远程 HMAC 始终启用，allowed_sources 可进一步限制来源。loopback 可以不签名。
从管理员 PowerShell 执行，并明确填写可信来源：

```powershell
powershell -File scripts/firewall.ps1 -RemoteAddress <可信IP或网段> -InterfaceAlias <接口名>
```

WLAN 为 Public 时规则同样适用。跨网优先 Tailscale。

## 测试与诊断

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe scripts/preflight.py
```

preflight 在无效代理环境下检查 ntfy 直连和真实 edge-tts 合成，不发布、不播放，自动删除音频。
自动测试覆盖认证、UTF-8 大小、去重、恢复、队列隔离、代理绕行、音频清理及配置迁移。
部署验收结果保存至忽略的 reports/local-acceptance.json，自省记录在 docs/review.md。
日志和请求历史位于配置的 data_dir；托盘 Recent requests 会导出最近状态。

## 卸载

先在托盘取消 Start at login 并 Exit。删除开始菜单 NotifyHub 快捷方式；按需要删除源码目录与 data_dir。
通知身份位于 HKCU/Software/Classes/AppUserModelId/NotifyHub.Desktop。防火墙规则可运行 scripts/firewall.ps1 -Remove -RemoteAddress 127.0.0.1 删除。
