# 不需要 Mac：用 GitHub Actions 生成两个 macOS 安装包

项目已经配置云端双架构构建：

- `FilmStripCutter-macOS-arm64.dmg`：Apple M1/M2/M3/M4/M5
- `FilmStripCutter-macOS-x86_64.dmg`：Intel Mac

## 操作

1. 注册或登录 GitHub。
2. 创建一个新仓库，把本构建包里的全部文件上传到仓库根目录；必须保留
   `.github/workflows/build-macos.yml`。
3. 打开仓库的 **Actions** 页面。
4. 左侧选择 **Build macOS DMGs**，点击 **Run workflow**。
5. 等两个任务完成后，进入该次运行记录，在 **Artifacts** 下载两个安装包。

构建产物采用临时签名，没有 Apple Developer 公证。朋友首次打开时需要在
“系统设置 → 隐私与安全性”中选择“仍要打开”。

仓库设为公开时，任何人都能看到源代码，但不会包含你的胶片照片；本项目不会
上传测试照片。若选择私有仓库，GitHub Actions 会消耗账户的私有仓库运行额度。
