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

带前缀的 .jrlp、/jrlp、.hlp 等指令形式同样兼容。

## 特性

- **自动配置图库**：图库资源托管在 Release 附件解耦发布。初次使用若本地无图库，后台自动通过国内加速源拉取 260MB+ 完整角色立绘并自动解压，即装即用
- **LLM 人设生动回复**：所有回复（抽老婆、换老婆、结婚、离婚、已婚状态、上限提示等）完全由 LLM 用机器人当前人设生成，没有固定模板
- **容灾保底机制**：LLM 不可用时自动回退到简洁的内置文案，保证功能不中断
- **数据持久化**：数据持久化在 `jrlp_data.json`，跨天自动重置换老婆次数与抽取状态

## 配置项

- `daily_hlp_limit`：每天最多换老婆次数（默认 5）
- `marriage_duration`：结婚维持天数（默认 7）

## 问题反馈聊天群（想玩bot的也可以来）
<img width="360" height="640" alt="8e8ff33bef82fc0160feafcd1e06b75c" src="https://github.com/user-attachments/assets/72bde825-011a-4e58-a1e9-4cf369073586" />
