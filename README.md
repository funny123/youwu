# 闲置商品 Docker 独立部署

商品展示页为 `/`，发布管理后台为 `/admin`。后台可以编辑商品、上传图片和 MP4 视频、保存草稿、发布和下架，并更新卖家的邮箱、WhatsApp 和 Telegram。商品价格统一使用瓦图（VT）。初次启动时商品目录为空。

## 启动

需要 Docker 和 Docker Compose。在本目录执行：

```sh
cp .env.example .env
openssl rand -hex 32
```

编辑 `.env`，把生成的随机值填入 `SESSION_SECRET`，再为 `ADMIN_PASSWORD` 设置一个至少 12 个字符的强密码。然后运行：

```sh
docker compose up -d --build
```

- 商品页：<http://localhost:8000/>
- 管理后台：<http://localhost:8000/admin>

默认只绑定主机的本地地址。部署到公网时，可通过 HTTPS 反向代理转发到 8000 端口，在 `.env` 设置 `SECURE_COOKIES=1`。

## 自动翻译

后台编辑商品时，可将中文名称、介绍和看货说明翻译到空白的英文栏。校对后保存即可。在 `.env` 中将 `TRANSLATE_URL` 设为支持中文到英文的 LibreTranslate 服务的完整 `/translate` 地址。若服务要求密钥，再设置 `TRANSLATE_API_KEY`。应用通过服务器发送所选商品文字，密钥只在服务器端使用。修改配置后运行 `docker compose up -d`。

## 上传限制

照片和视频共用单次请求上限，默认为 256 MiB，可在 `.env` 中设置 `UPLOAD_MAX_MIB`。修改后运行 `docker compose up -d --build`。反向代理的请求体限制也需覆盖该值，例如 Nginx 对应站点可设置 `client_max_body_size 256m;`。如果公网入口有固定上限，需压缩视频，或先发布商品照片，再编辑商品单独上传视频。

## 数据和更新

SQLite 数据库和上传文件都保存在 Compose 的 `catalog` 命名卷。重新构建、重启容器会复用该卷。备份时先停止服务，再备份该卷里的整个 `/data` 目录，恢复时也应同时恢复数据库和媒体。删除命名卷会清空商品、联系方式和上传文件。
