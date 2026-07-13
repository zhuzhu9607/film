# FilmStrip Cutter macOS 构建

此目录已经包含 macOS 所需的 `.icns` 图标和自动打包脚本。

不熟悉终端时，直接双击 `双击构建Mac版.command`。脚本会自动识别当前 Mac
的芯片并在完成后打开 `dist` 文件夹。如果提示没有 Python，请按提示安装后
再双击一次。

## 生成 App 与 DMG

1. 在 Mac 上安装 Python 3.12。
2. 将整个项目目录复制到 Mac。
3. 打开“终端”，进入项目目录后执行：

```bash
chmod +x build_macos.sh
TARGET_ARCH=arm64 ./build_macos.sh
```

完成后会得到：

- `dist/FilmStripCutter.app`
- `dist/FilmStripCutter-macOS-arm64.dmg`（Apple 芯片）
- `dist/FilmStripCutter-macOS-x86_64.dmg`（Intel 芯片）

目标架构可以明确指定：

```bash
TARGET_ARCH=arm64 ./build_macos.sh
TARGET_ARCH=x86_64 ./build_macos.sh
TARGET_ARCH=universal2 ./build_macos.sh
```

Universal 2 要求 Python 及所有原生依赖同时包含两种架构；如果其中任一依赖
不是通用二进制，PyInstaller 会停止构建。这种情况下请分别在 Apple 芯片和
Intel 环境生成两个原生 DMG，它们更容易测试，也更可靠。

脚本默认进行本机临时签名。若要分发给其他 Mac 且不出现开发者警告，仍需
Apple Developer ID 证书签名并由 Apple 公证。
