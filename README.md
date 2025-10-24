# 机翻空洞骑士: 丝之歌（Hollow Knight: Silksong）文本处理工具

本仓库提供一组用于导出、机翻与重新打包 **空洞骑士:丝之歌** 文本资源的脚本。代码写得直观可运行为主，欢迎在备份原始文件后使用并根据需要修改。

## 主要功能概览
- `export.py`：调用解密工具并导出资源文本（生成可编辑的中间 JSON）。
- `translate.py`：批量机器翻译文本并保存中间版本（支持多次迭代）。
- `import_data.py`：将翻译后的文本打包并加密回游戏所需格式。
- `localization_core.py`：本项目的本地化辅助函数。
- `qcloud_core.py`：调用腾讯机器翻译（QCloud）的封装。

## 快速开始（Windows）
先决条件：
- Python 3.8+（推荐）
- 在 Windows 上运行（资源解密依赖外部 exe 工具，只在 Windows 下可用）
- 配置好 `config.json` 中的 `Tencent_Secret_Id` 与 `Tencent_Secret_Key`（若使用腾讯翻译）

示例运行流程（在项目根目录下，PowerShell 篇）：

```powershell
python -m pip install -r requirements.txt
# 导出并解密游戏文本
python export.py
# 进行一次或多次翻译迭代（根据翻译顺序.csv）
python translate.py
# 将翻译结果打包回资源文件
python import_data.py
```

工具输出和中间文件位置：
- `data/`：整理后的可编辑文本（JSON）及历次翻译版本。
- `temp_hk_modding/`：解密后的原始游戏文件与临时输出。
- `output/`：打包后的资源文件（例如 `resources_packed_vXX.assets`）。

要将打包结果应用回游戏：备份原始 `resources.assets`，将 `output/resources_packed_vXX.assets` 重命名为 `resources.assets`，并复制到游戏目录 `.../Hollow Knight Silksong/Hollow Knight Silksong_Data` 下替换原文件。

## 推荐工作流程（详解）
1. 运行 `export.py`，得到解密并导出的原始文本（保存在 `data/` 与 `temp_hk_modding/output_decrypted/`）。
2. 编辑或直接运行 `translate.py` 进行机器翻译。默认只做一次迭代；如需链式多语言机翻以改善结果，请修改 `翻译顺序.csv`（从 v7 开始加入了多语种流程以最大化机翻效果）。
3. 翻译满意后运行 `import_data.py`，它会把翻译后的文本加密并生成可替换的资源文件。

## 配置说明
- `config.json`：包含程序配置项。
	- `Tencent_Secret_Id` 与 `Tencent_Secret_Key` 为必须填项（若使用腾讯翻译服务）。
	- 其他配置项可保留默认，除非你确切知道要做什么调整。

## 使用技巧与注意事项
- 请务必先备份原始游戏文件再替换资源。
- 解密部分基于外部工具 `HollowKnight_TextAssetDecryptor.exe`（来源见下），因此目前只在 Windows 环境中完全可用。
- 若翻译质量不理想，可通过修改 `翻译顺序.csv` 来添加中转语言进行多轮翻译, 也可以直接修改`data`中的对应josn文件.

## 文件说明
- `resources.assets`：官方资源文件（位于游戏安装目录 `Hollow Knight Silksong_Data`）。
- `data/`：整理并保存的文本数据与翻译历史。
- `temp_hk_modding/`：解密的原始文件与临时中间产物。

## 致谢与来源
- 文本解密脚本来源：HollowKnight_TextAssetDecryptor.exe，来自 Nexus Mods（https://www.nexusmods.com/hollowknightsilksong/mods/10）。
- 作者主页：https://next.nexusmods.com/profile/zhoppers/mods?gameId=8136

## 免责声明
- 请仅在拥有游戏合法副本的前提下使用本工具并遵守相关平台与法律规定。

<!-- ## 联系与贡献 -->
<!-- 欢迎提交 issue 或 pull request 来改进。若你有更好的翻译流程、脚本优化或自动化建议，欢迎贡献。 -->