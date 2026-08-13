# WinAppMigrator 更新服务器

官网 + Web 管理后台 + 客户端更新 API。架构：Spring Boot 3 + MySQL + Redis + nginx（HTTPS/域名）。

```
update-server/
├── pom.xml
├── deploy/nginx.conf          # nginx 配置（SSL + 域名反代）
├── src/main/java/com/zhuzhu/update/
│   ├── UpdateServerApplication.java
│   ├── config/WebConfig.java           # 拦截器 / 上传资源 / /admin 路由
│   ├── security/AdminAuthService.java  # 管理员登录（ADMIN_PASSWORD 环境变量 + Redis token）
│   ├── security/AdminAuthInterceptor.java
│   ├── entity/  repo/  service/        # 版本/下载日志/官网内容
│   └── web/    SiteController | UpdateController | AdminController
├── src/main/resources/
│   ├── application.yml                 # 全部敏感项走环境变量
│   ├── db/schema.sql                   # MySQL 建表（可选，JPA 也会自动建表）
│   └── static/                         # 官网（/）+ 管理后台（/admin）
│       ├── index.html  css/site.css  js/site.js
│       └── admin/      index.html  admin.css  admin.js
└── uploads/                           # 运行时生成：安装包 pkg/ + 官网图片 img/
```

## 1. 环境准备（服务器）

- JDK 21、Maven
- MySQL 8：建库 `winapp_update`（执行 `src/main/resources/db/schema.sql`，或让 JPA 自动建表）
- Redis 6+：默认连 `127.0.0.1:6379`

## 2. 配置环境变量（务必设置）

```bash
export ADMIN_PASSWORD='换成强密码'     # 管理后台登录密码（必须，空则后台拒绝登录）
export DB_HOST=127.0.0.1
export DB_PORT=3306
export DB_NAME=winapp_update
export DB_USER=root
export DB_PASSWORD='数据库密码'
export REDIS_HOST=127.0.0.1
export REDIS_PORT=6379
# export UPLOAD_DIR=/opt/update-server/uploads   # 可选，默认 ./uploads
```

## 3. 构建与运行

```bash
mvn -DskipTests package
java -jar target/update-server-1.0.0.jar
# 服务只监听 127.0.0.1:8080
```

## 4. nginx + SSL + 域名

将 `deploy/nginx.conf` 放到 `/etc/nginx/conf.d/`，替换 `example.com` 与证书路径：

```bash
sudo nginx -t && sudo systemctl reload nginx
```

外网访问：`https://example.com`（官网）与 `https://example.com/api/update/check?version=1.0.0`（客户端轮询接口）。
**管理后台 `/admin` 未在 nginx 放行**，外网不可达，只能走 SSH 隧道。

## 5. 通过 SSH 隧道访问管理后台

```bash
# 本机执行：把服务器的 8080 端口映射到本地 8080
ssh -N -L 8080:127.0.0.1:8080 user@服务器IP
# 然后浏览器打开 http://127.0.0.1:8080/admin 输入 ADMIN_PASSWORD 登录
```

后台功能：编辑官网内容（文字/图片上传）、发布新版本安装包、查看总下载量与 30 天下载趋势图。

## 6. 客户端接入

客户端轮询接口（每 30s）：

```
GET /api/update/check?version=1.0.0&platform=windows
→ {"hasUpdate":true,"latest":"1.1.0","notes":"...","size":52428800,
   "md5":"...","force":false,"url":"/api/update/download/12"}
```

下载：`GET /api/update/download/{id}`（返回安装包文件流并记录下载量）。
