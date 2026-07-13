# 胶片分格 FilmStrip Cutter

离线 Windows / macOS 桌面工具，用于把长条胶片扫描图自动分格并批量导出。

## 功能

- 支持 TIFF、JPG、PNG，以及 LibRaw 可解码的常见相机 RAW（DNG、NEF、CR2、CR3、ARW、RAF、RW2 等）
- 自动判断横向/纵向胶片并识别分格
- 自动识别同一张扫描图中并排摆放的多条胶片
- 可指定这一条的实际张数；分格网格会自动偏移，不会把片头、片尾余量均分进照片
- 可拖动裁剪框或四条边，双击补框，Delete 删除框
- 每个裁剪框带有垃圾桶按钮；空白区域悬停后提示双击补框
- 鼠标滚轮围绕指针位置缩放；在未识别区域按住左键，或用中/右键拖动画面
- 全卷统一画幅尺寸与节距，漏光、全黑和低对比照片不会单独改变框大小
- “纯照片 / 少量黑边 / 完整齿孔 / 自定义”四种裁剪方式
- TIFF 支持保留原始位深、16 位或 8 位；JPG 质量 85–100
- 所有裁剪均从原始分辨率图像导出，预览缩放不影响成片清晰度
- 一键负片反色，预览与 JPG/TIFF 导出同步生效，不修改源文件

## 使用

1. 打开或拖入一张长条扫描图。
2. 按需要填写整张扫描图的总张数；程序会自动排除片头、片尾余量。
3. 默认“标准”为 0% 扩展；也可选择其他黑边/齿孔范围，再点“按以上参数自动识别画格”。
4. 检查绿色裁剪框并拖动微调。
   滚轮可放大细看；在未识别区域按住左键，或用中/右键拖动可平移；按数字键 0 恢复全图。
5. 选择 TIFF 或 JPG，点击“导出全部裁剪框”。

> RAW 是相机厂商格式的统称。实际兼容性由内置 LibRaw 解码器决定；扫描仪私有 RAW 若并非标准相机 RAW，建议先转为 16 位 TIFF。

## 开发运行

```powershell
.venv\Scripts\python.exe main.py
```

## 构建 EXE

```powershell
.\build.ps1
```

成品为 `dist\FilmStripCutter-v5.exe`，可复制到其他 Windows 电脑直接运行。

## 构建 macOS 版

必须在 Mac 上执行（PyInstaller 不能从 Windows 交叉编译 `.app`）：

```bash
chmod +x build_macos.sh
./build_macos.sh
```

脚本默认按当前 Mac 的芯片架构生成 `dist/FilmStripCutter.app` 和对应的 DMG；
也可通过 `TARGET_ARCH=arm64`、`x86_64` 或 `universal2` 指定目标架构。
并进行本机临时签名。若提供 Apple Developer 签名证书，可通过
`SIGN_IDENTITY="Developer ID Application: ..." ./build_macos.sh` 正式签名。

没有 Mac 时，可使用仓库内的 `.github/workflows/build-macos.yml` 在 GitHub
Actions 云端同时生成 arm64 和 x86_64 两个 DMG，具体见
`GITHUB_ACTIONS_BUILD.md`。
