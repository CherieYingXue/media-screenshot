# 支部通知网页

一个手机优先的通知网页，支持六类身份：

- 支部书记
- 支委
- 组长
- 第一组成员
- 第二组成员
- 第三组成员

首次打开页面后选择身份，身份可以多选。支部书记、支委、组长可发布和删除通知。

## 功能

- 移动端页面，适合通过手机浏览器添加到主屏幕
- PWA manifest + service worker，基础页面资源可缓存
- 发布者可选择通知范围：全体、支委、组长、第一组成员、第二组成员、第三组成员
- 用户只看到与自己身份匹配的通知；支部书记可查看全部通知
- 支部书记、支委、组长可直接发布和删除通知
- 最新通知始终显示在列表顶端
- 未读通知数量显示在页面角标、浏览器标题，并尝试使用浏览器 Badging API 显示到主屏幕图标
- 无外部 CDN、字体或境外接口依赖，部署到中国大陆可访问的服务器后无需 VPN

> 说明：主屏幕图标红色数字依赖浏览器支持 Badging API。Android Chrome/部分 Chromium 浏览器支持较好；iOS Safari 目前支持有限，因此页面同时提供标题和站点图标兜底提示。

## 本地运行

```bash
pip install -r requirements.txt
python server.py
```

打开终端输出的地址。手机和电脑在同一 Wi-Fi 时，也可以用电脑局域网 IP 访问。

## 部署建议

- 这是一个独立项目目录。如果在当前仓库里部署，请把云平台的 Root Directory / 工作目录设置为 `branch-notice-pwa`。
- 若要在中国大陆无需 VPN 访问，请部署到阿里云、腾讯云、华为云等大陆或大陆可直连节点，并按域名/服务器要求完成备案。
- 应用本身不加载 Google Fonts、国外 CDN 或第三方接口；通知数据保存在 `NOTICES_DATA_DIR` 指定目录的 `notifications.json` 中。
- 生产环境建议把 `NOTICES_DATA_DIR` 指向持久化磁盘或对象存储挂载目录，避免容器重启后丢失通知。

## API

- `GET /api/bootstrap`：身份和通知范围配置
- `GET /api/notifications?roles=支委&roles=第一组成员`：获取与身份匹配的通知
- `POST /api/notifications`：发布通知
- `DELETE /api/notifications/<id>`：删除已发布通知
