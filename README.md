# AstrBot NewAPI 站点查询与管理插件 (astr_newapi_plugin)

为 AstrBot 量身定制的 **NewAPI** 站点信息查询与全能管理插件。
支持用户绑定专属账号自主查询用量、余额与订阅，集成全站消费与热度排行，搭载轻量高效的暗色 PIL 画图模版与中英文无缝指令匹配。

---

## 🌟 核心特性

1. **👥 所有人自主绑定账号**：
   - 普通群友/用户可通过 `/newapi bind <用户名或ID>` 将自己的聊天身份与 NewAPI 账号绑定。
   - 绑定后，随时发送 `/newapi my`（或 `/newapi 余额`、`/newapi 订阅`）即可一键查询个人可用额度、累计消耗、请求数及套餐订阅到期时间。
2. **💾 规范化数据存储与一键备份导出**：
   - **遵循 AstrBot 官方规范**：所有持久化数据统一存放在 AstrBot 指定的数据目录：`data/plugin_data/astr_newapi_plugin/`。
   - **一键备份导出为 ZIP（复制即带走）**：管理员执行 `/newapi backup`，即可将用户绑定数据（`user_bindings.json`）、站点缓存（`cache.json`）与配置备份（`config_backup.json`）一键打包为 `.zip` 压缩包，支持聊天窗口直接发送文件下载或在服务器复制。
   - **解压即复原**：更换机器或重新部署时，只需将压缩包内容解压至 `data/plugin_data/astr_newapi_plugin/` 覆盖，或发送 `/newapi restore` 即可秒级复原全部数据！
3. **🎨 动静分离渲染（信息多时暗色画图，少时文字速回）**：
   - **信息项较多时自动使用 PIL 绘制紧凑精美的暗色卡片**：菜单、用户排行榜、模型排行榜、系统与服务器硬件状态、渠道列表等均采用轻量暗色模版（<30ms 极速生成，内存与带宽占用极低）。
   - **信息项较少或需复制时直接返回文字**：账户余额简报、兑换码 CDK 生成（方便直接长按复制）、增减额度结果、封禁解禁等。
4. **🖥️ 状态监控包含硬件资源负载**：
   - `/newapi status` 不仅展示 NewAPI 站点名称、版本与启动时间，还包含服务器实时 **CPU 使用率**、**内存占用（已用/总计）**、**磁盘空间占用** 的进度条与数值显示。
5. **🔤 灵活的前缀与中英文指令兼容**：
   - **全兼容中文别名**：如 `/newapi 菜单`、`/newapi 余额`、`/newapi 绑定`、`/newapi 排行`、`/newapi 备份`、`/newapi 恢复` 等。
   - **有空格与无空格均可识别**：如 `/newapi menu` 与 `/newapimenu`、`/newapi 余额` 与 `/newapi余额`、`/newapi 备份` 与 `/newapi备份`。
6. **🔕 静默鉴权与安全控制**：
   - 当在设置中关闭管理功能（`enable_admin: false`）或非管理员尝试调用管理类指令时，插件直接静默阻断，不再向群聊中发送冗余的权限报错打扰对话。

---

## ⚙️ 配置说明

在 AstrBot 控制面板的 **插件管理** 页面配置以下参数：

| 配置项 | 类型 | 默认值 | 说明 |
| :--- | :---: | :---: | :--- |
| `site_url` | 字符串 | `""` | NewAPI 站点地址，例如 `https://api.example.com` 或 `http://127.0.0.1:3000` |
| `api_token` | 字符串 | `""` | NewAPI 访问令牌（PAT `nap_...` 或系统令牌） |
| `enable_admin` | 布尔值 | `true` | 是否启用管理功能。关闭后管理指令直接静默失效 |
| `admin_only` | 布尔值 | `true` | 管理类指令是否仅限 AstrBot 机器人管理员调用（非管理员调用直接静默） |
| `request_timeout` | 整数 | `15` | 请求 NewAPI 超时时间（秒） |
| `proxy` | 字符串 | `""` | 可选 HTTP/SOCKS 代理地址 |
| `quota_per_unit` | 整数 | `500000` | 1 美元额度点数（插件会自动从站点获取） |

> 📁 **官方数据持久化目录**：
> `data/plugin_data/astr_newapi_plugin/`
> - `user_bindings.json`：用户聊天 ID 与 NewAPI 账号映射
> - `cache.json`：站点缓存与换算比例
> - `config_backup.json`：配置参数安全备份
> - `backups/`：备份文件归档目录（存储自动生成的 `.zip` 压缩包）

---

## 📖 指令对照表

支持指令带前缀与空格（如 `/newapi my`），也支持紧凑无空格写法（如 `/newapi余额`）。

### 1. 👥 用户查询与绑定指令
| 指令格式（中英均可，支持有/无空格） | 参数 | 返回形式 | 功能说明 |
| :--- | :--- | :---: | :--- |
| `/newapi menu` 或 `/newapi 菜单` | 无 | 🖼️ 暗色卡片 | 展示全部可用指令与功能菜单 |
| `/newapi bind` 或 `/newapi 绑定` | `<用户名或用户ID>` | 📝 文字 | 绑定个人的 NewAPI 账号 |
| `/newapi unbind` 或 `/newapi 解绑` | 无 | 📝 文字 | 解绑当前账号 |
| `/newapi my` 或 `/newapi 余额` / `/newapi 订阅` | 无 | 📝 文字 | 查询个人绑定的余额、已消耗、请求次数与订阅到期情况 |
| `/newapi my_stat` 或 `/newapi 我的消耗` | `[today/week/month/all]` | 📝 文字 | 查询个人在指定时间周期内的详细消耗统计 |
| `/newapi stat` 或 `/newapi 全站统计` | `[today/week/month/all]` | 📝 文字 | 查询全站总消耗金额、当前 RPM 与 TPM |
| `/newapi ranking` 或 `/newapi 排行` | `[day/week/month/total]` | 🖼️ 暗色卡片 | 全站用户消耗排行榜 Top 10（天/周/月/总） |
| `/newapi model_ranking` 或 `/newapi 模型排行` | `[today/week/month/year]` | 🖼️ 暗色卡片 | AI 模型与各厂商 Token 消耗排行 |
| `/newapi status` 或 `/newapi 状态` | 无 | 🖼️ 暗色卡片 | 查询站点系统参数与服务器 CPU/内存/磁盘占用 |
| `/newapi redeem` 或 `/newapi 兑换` | `<兑换码CDK>` | 📝 文字 | 使用充值卡 CDK 为当前账号充值 |

### 2. 👑 管理员指令（权限不足或关闭时静默）
| 指令格式（中英均可，支持有/无空格） | 参数 | 返回形式 | 功能说明 |
| :--- | :--- | :---: | :--- |
| `/newapi admin` 或 `/newapi 管理` | 无 | 🖼️ 暗色卡片 | 显示管理员专用功能菜单 |
| `/newapi backup` 或 `/newapi 备份` | 无 | 📦 ZIP文件 + 📝 文字 | **一键打包备份全部数据并导出 ZIP 压缩包** |
| `/newapi restore` 或 `/newapi 恢复` | `[备份文件名]` | 📝 文字 | **从指定或最新备份压缩包一键复原数据** |
| `/newapi user` 或 `/newapi 查用户` | `<用户名或用户ID>` | 📝 文字 | 查询指定用户的完整信息与余额 |
| `/newapi create_user` 或 `/newapi 创建用户` | `<用户名> <密码> [昵称]` | 📝 文字 | 创建普通用户账号 |
| `/newapi add_quota` 或 `/newapi 加额度` | `<用户> <美元金额>` | 📝 文字 | 为指定用户增加额度（如 `加额度 test 5`） |
| `/newapi sub_quota` 或 `/newapi 扣额度` | `<用户> <美元金额>` | 📝 文字 | 扣减指定用户额度 |
| `/newapi set_quota` 或 `/newapi 设置额度` | `<用户> <美元金额>` | 📝 文字 | 重置覆盖指定用户额度 |
| `/newapi enable_user` 或 `/newapi 解封` | `<用户>` | 📝 文字 | 解封/启用指定用户 |
| `/newapi disable_user` 或 `/newapi 封号` | `<用户>` | 📝 文字 | 禁用/封禁指定用户 |
| `/newapi create_cdk` 或 `/newapi 生成兑换码` | `<美元面额> [数量] [名称]` | 📝 文字 | 批量并发生成指定面额的 CDK 兑换码（支持复制） |
| `/newapi channels` 或 `/newapi 渠道列表` | 无 | 🖼️ 暗色卡片 | 查看所有上游渠道配置、权重与延迟 |
| `/newapi test_channel` 或 `/newapi 测速` | `[渠道ID]` | 📝 文字 | 测试上游渠道响应速度与可用性 |
| `/newapi token_list` 或 `/newapi 令牌列表` | 无 | 📝 文字 | 查看当前账户的所有 API Key |
| `/newapi token_add` 或 `/newapi 创建令牌` | `<名称> [额度美元]` | 📝 文字 | 创建新的 API Key |
| `/newapi token_del` 或 `/newapi 删除令牌` | `<令牌ID>` | 📝 文字 | 删除指定的 API Key |
| `/newapi token_key` 或 `/newapi 查看秘钥` | `<令牌ID>` | 📝 文字 | 提取完整的 API Key 秘钥 (`sk-...`) |
