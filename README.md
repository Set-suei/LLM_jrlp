# galgame-LLM-jrlp（astrbot_plugin_LLM_jrlp）

随机抽一位 gal 角色作为今日老婆，支持换老婆/结婚/离婚，回复完全由 LLM 生成。
移植自 [shifeifenming/jrlp](https://github.com/shifeifenming/jrlp)（海豹骰「今日老婆」插件），保留原项目全部功能，并且增加了 LLM 回复功能，回复完全由 AstrBot 的 LLM 用当前人设生成。

大概效果
<img width="914" height="528" alt="L3 ULJT7XM4AZWRXKC@(J_O" src="https://github.com/user-attachments/assets/6f055c68-e073-4f49-80ef-f46782f27051" />

## 触发方式（无需前缀）

直接发送以下任意文字即可：

| 发送内容 | 功能 |
| ---- | ---- |
| jrlp / 今日老婆 | 抽取今日老婆（每天第一次随机，之后固定） |
| hlp / 换老婆 | 换老婆（每日有上限，默认 5 次） |
| 结婚 / jrlp 结婚 | 与今日老婆结婚（默认维持 7 天） |
| 离婚 / jrlp 离婚 | 解除婚姻关系 |
| jrlp status / jrlp状态 | 查看插件状态与图库加载数量 |
| jrlp download / 下载图库 | 查看图库下载解压进度或手动触发下载 |
| jrlp help / jrlp帮助 | 查看完整指令使用说明 |

带前缀的 `~jrlp`、`.jrlp`、`/jrlp`、`~hlp` 等指令形式同样兼容。

## 图库资源说明与下载提示

- **解耦发布**：为保持插件仓库轻量，包含 320 位角色立绘的完整图库包（约 263MB）独立托管于 GitHub Release 附件中。
- **显式确认下载（Opt-in）**：安装插件后，若本地尚未放置图库，默认不会未经确认静默消耗大额流量。您可以随时通过发送 **`jrlp 下载图库`** 显式启动后台异步流式下载，下载与解压完成后自动载入，无需重启。
- **手动安装方式**：您也可以直接从本仓库 Release 下载 `jrlp_img.zip`，解压所有图片至 `data/plugin_data/astrbot_plugin_LLM_jrlp/img/` 目录下即可即时生效。

## 特性

- **非阻塞异步流式下载**：采用 aiohttp 异步流式分块拉取，完全不占用主线程与事件循环，下载过程平滑稳定。
- **LLM 人设生动回复**：所有回复（抽老婆、换老婆、结婚、离婚、已婚状态、上限提示等）完全由 LLM 用机器人当前人设生成，没有固定模板。
- **GENIE 语音联动兼容**：已开启语音插件时自动按双语格式驱动语音合成；未开语音插件时自动严格清洗为自然中文对白。
- **容灾保底机制**：LLM 不可用或请求失败时自动回退到内置文案，保证基础功能不中断。
- **数据持久化规范**：数据遵循 AstrBot 官方规范持久化保存在 `data/plugin_data/astrbot_plugin_LLM_jrlp/`，跨天自动重置换老婆次数与抽取状态。

## 配置项

可在 AstrBot 管理面板或插件配置文件中调整：

- `daily_hlp_limit`：每天最多换老婆次数（整数，默认 5）
- `marriage_duration`：结婚维持天数（整数，默认 7）
- `auto_download_images`：图库为空时是否自动拉取 Release 资源包（布尔值，默认 false，建议显式发送「jrlp 下载图库」确认）
- `use_mirror_accelerate`：下载图库时是否优先使用国内加速镜像（布尔值，默认 false，直连 GitHub 官方源）

## 问题反馈聊天群（想玩bot的也可以来）
<img width="360" height="640" alt="8e8ff33bef82fc0160feafcd1e06b75c" src="https://github.com/user-attachments/assets/72bde825-011a-4e58-a1e9-4cf369073586" />
