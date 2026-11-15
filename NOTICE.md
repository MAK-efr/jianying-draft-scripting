# 第三方组件与来源说明

本仓库自有代码以 MIT 许可发布（见 `LICENSE`）。以下第三方内容按各自许可随附，版权归原作者。

## 1. jy-draftc.exe

- 路径：`scripts/bin/jy-draftc.exe`（及其说明 `jy-draftc-README.md`、`jy-draftc-USAGE.txt`）
- 作者：wenshui330
- 许可：MIT License © 2026 wenshui330
- 作用：借剪映自身的 `videoeditor.dll` 完成草稿内容加解密、结构版本升降级、无头导出
- 说明：本仓库仅调用其命令行接口，未修改二进制内容。其上游说明文档已原样随附，使用前请阅读其中"适用版本"表格——工具版本必须与运行时剪映版本匹配。

## 2. references/transition_meta.py

- 转场元数据（名称 / effect_id / resource_id / 资源 md5 / 默认时长 / 是否重叠）
- 来源：[pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft)（MIT License）
- 说明：仅作数据表使用，未包含其代码。

## 3. references/draft_skeleton.json

- 剪映草稿的空骨架结构（28 个顶层键 / 45 个空素材表）
- 从本机剪映实例保存的工程文件中提取字段结构，**不含任何素材、文本或个人信息**
- 用途：作为"从零建稿"的容器模板

## 4. 关于剪映（JianyingPro / CapCut）

本项目与字节跳动无任何关联，未分发剪映的任何程序文件。使用时需自行安装剪映，并遵守其用户协议。`jy-draftc` 通过调用本机已安装剪映的 DLL 工作，不提供、也不绕过任何账号或付费校验。
