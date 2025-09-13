
<div align="center">

![:name](https://count.getloli.com/@astrbot_plugin_lmarena?name=astrbot_plugin_lmarena&theme=minecraft&padding=6&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

# astrbot_plugin_lmarena

_✨ [astrbot](https://github.com/AstrBotDevs/AstrBot) LMArena插件 ✨_  

[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-3.4%2B-orange.svg)](https://github.com/Soulter/AstrBot)
[![GitHub](https://img.shields.io/badge/作者-Zhalslar-blue)](https://github.com/Zhalslar)

</div>

## 🤝 介绍

对接lmarena调用nano_banana等模型进行生图，如手办化

## 📦 安装
  
### 1.安装本插件

- 直接在astrbot的插件市场搜索astrbot_plugin_lmarena，点击安装

### 2.安装油猴脚本

- **安装油猴脚本管理器**
    为你的浏览器安装 [Tampermonkey](https://www.tampermonkey.net/) 扩展。

- **安装本项目油猴脚本**
    1. 打开 Tampermonkey 扩展的管理面板。
    2. 点击“添加新脚本”或“Create a new script”。
    3. 打开 [`LMArenaApiBridge.js`](https://github.com/Zhalslar/astrbot_plugin_lmarena/blob/main/LMArenaApiBridge.js) 文件，将文件里的所有代码复制并粘贴到编辑器中。
    4. 确保有权限运行（谷歌浏览器示例）：浏览器设置 -> 管理拓展 -> 篡改猴 -> 详情 -> 允许运行用户脚本（打开）。

### 3.插件与油猴对接

- 开启/重载插件时，日志显示：[bridge.server:74]: WebSocket 端点: ws://127.0.0.1:5102/ws
- 开启脚本刷新[LMArena.ai](https://lmarena.ai/)页面时，日志显示：✅ 油猴脚本已成功连接 WebSocket。并且[LMArena.ai](https://lmarena.ai/)页面页面标题会以 ✅ 开头。

### 3.捕获会话ID

- 在[竞技场](<https://lmarena.ai>)找到你想要的模型(比如nano_banana)并对话一次。
- Direct_chat模式寻找nano_banana示例：点聊天栏左下角的图片图标，此时就可以页面上方看见模型列表里有nano_banana可选了。
- Battle模式寻找nano_banana示例：battle模式下上传一张图，输入手办化的提示词进行生图，效果像下面示例图的就是nano_banana了，提示词：（Use the nano-banana model to create a 1/7 scale commercialized figure of thecharacter in the illustration, in a realistic styie and environment.Place the figure on a computer desk, using a circular transparent acrylic base without any text.On the computer screen, display the ZBrush modeling process of the figure.Next to the computer screen, a transparent board with a wooden base on which the original artwork is printed.）。
- 在 Battle 模式下，要进入插件配置面板选择更新的目标（左侧为A，右侧为B），改变目标时要重载插件
- 一切准备就绪后，给bot发送命令 `lm捕获`或`lmc`激活油猴脚本的捕获模式，然后点模型右上角的重试按钮，刷新目标模型从而捕获会话ID，然后就可以正常使用了

## ⌨️ 使用说明

### 配置

| 配置项       | 说明                                                                 |
|:-------------|:---------------------------------------------------------------------|
| server       | 插件内部服务器配置，用于设置服务器的主机、端口和API Key等信息。       |
| host         | 服务器主机地址，默认为本机地址 `127.0.0.1`。                         |
| port         | 服务器端口号，默认为 `5102`。                                        |
| api_key      | 服务器API Key，用于访问服务器时的身份验证，不填则无需验证直接访问。   |
| base_url     | Lmarena请求地址，用于指定远程服务器地址，默认为本机地址。             |
| prefix       | 是否启用触发前缀，启用后需要前缀或@bot来触发命令。                    |
| retries      | 生图失败重试次数，最后一次重试失败时返回错误。                        |
| prompt       | 生图触发词与提示词，具体配置在 `data/plugins/astrbot_plugin_lmarena/prompt.py` 文件中。 |
| save_image   | 是否保存生成的图片，保存目录为 `data/plugin_data/astrbot_plugin_lmarena`。 |
| battle_target| 在Battle模式下，要更新的目标，可选 `A` 或 `B`，切换时需重载插件。      |

### 命令表

|     命令      |                    说明                    |
|:-------------:|:-----------------------------------------------:|
| `(引用图片)/一段描述词`  | 将图片引用的图片按照描述词进行处理  |
| `lm捕获` or `lmc`  | 发送命令激活油猴脚本的捕获模式, 然后请在浏览器中刷新目标模型从而捕获会话ID    |
| `lm刷新` or `lmr` | 刷新lmarena网页    |
| `lm帮助` or `lmh` | 查看所有预设好的描述词，如办化1、手办化2、手办化3、手办化4、手办化5、手办化6、Q版化、cos化、cos自拍、痛屋化、痛屋化2、痛车化、孤独的我、第一人称、第三视角、鬼图、贴纸化、玉足、fumo化     |

### 示例图

![d5f0d1d36a439991a87eaba0db70950e](https://github.com/user-attachments/assets/d6dc6404-71e1-4b74-94c5-026bd05c7309)

## 👥 贡献指南

- 🌟 Star 这个项目！（点右上角的星星，感谢支持！）
- 🐛 提交 Issue 报告问题
- 💡 提出新功能建议
- 🔧 提交 Pull Request 改进代码

## 📌 注意事项

- 想第一时间得到反馈的可以来作者的插件反馈群（QQ群）：460973561（不点star不给进）

## 🤝 鸣谢

- [LMArena.ai](https://lmarena.ai/) - 模型竞技场, 网站上提供的海量先进测试大语言模型
- [LMArenaBridge](https://github.com/Lianues/LMArenaBridge)  - AI模型竞技场API代理器， 充当一座桥梁，让你能通过任何兼容 OpenAI API 的应用程序来使用 LMArena，欢迎大家前去[LMArenaBridge](https://github.com/Lianues/LMArenaBridge)点个star！
