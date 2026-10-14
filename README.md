# 支部/小组通知网页

一个手机优先的通知网页，支持三类身份：

- 支部通知管理员：发布所有人可见的支部通知
- 小组通知管理员：发布仅本小组可见的小组通知
- 订阅者：查看支部通知和本人所在小组通知

小组固定为第一小组、第二小组、第三小组。首次打开页面后选择身份和小组，三类身份可以多选。

## 功能

- 移动端页面，适合通过手机浏览器添加到主屏幕
- PWA manifest + service worker，基础页面资源可缓存
- 支部通知对所有登录身份可见
- 小组通知仅对同一小组成员可见
- 支部/小组管理员可直接发布通知
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

- 若要在中国大陆无需 VPN 访问，请部署到阿里云、腾讯云、华为云等大陆或大陆可直连节点，并按域名/服务器要求完成备案。
- 应用本身不加载 Google Fonts、国外 CDN 或第三方接口；通知数据保存在 `NOTICES_DATA_DIR` 指定目录的 `notifications.json` 中。
- 生产环境建议把 `NOTICES_DATA_DIR` 指向持久化磁盘或对象存储挂载目录，避免容器重启后丢失通知。

## API

- `GET /api/bootstrap`：身份、小组和通知类型配置
- `GET /api/notifications?group=第一小组`：获取支部通知和指定小组通知
- `POST /api/notifications`：发布通知
