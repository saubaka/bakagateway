# baka 身份平台

统一账号、个人中心和应用登录网关，使用 Flask API、Vue 3 / TypeScript、PostgreSQL 和 Docker Compose。

## 启动

需要 Docker、Docker Compose 和 Python 3.9+。在项目根目录运行：

```bash
python3 scripts/prepare_local.py
docker compose -p bakagateway up -d --build --wait
```

访问 http://127.0.0.1:5180 。首次安装没有默认账号、密码、接入应用或业务数据，注册默认关闭。初始化脚本生成本实例的随机秘密；签名密钥在首次启动时写入独立卷，源码不包含任何预置密钥。

创建首位管理员，密码在终端交互输入，不放进命令参数：

```bash
docker compose -p bakagateway exec api flask --app app:create_app create-admin --username YOUR_NAME --email YOUR_EMAIL
```

登录后在管理后台配置邮件、站点信息和注册开关。普通用户可以管理资料、头像、密码、邮箱、设备及已连接应用；管理员可以管理账号、接入应用、站点与邮件设置。

应用接入使用标准 OAuth 2.0 授权码 + S256 PKCE / OpenID Connect，支持资料分享、刷新和撤销。接入密钥由应用后端保管，不放在浏览器代码或URL中。

## 配置与维护

生产配置参考 `.env.production.example`，使用自己的受控HTTPS域名和邮件服务。`.env.example`只含配置示例，不含密码。依赖已锁定，数据库、上传和签名分别持久化。

[部署与维护说明](docs/DEPLOYMENT.md)包含环境变量、首管/邮件配置、备份恢复和升级步骤。停止容器可使用`docker compose -p bakagateway down`，正式数据不要使用`down -v`。

开发热更新：

```bash
docker compose -p bakagateway -f compose.yaml -f compose.dev.yaml up -d --build --wait
```

本仓库只发布应用源码、依赖锁和部署文件，不包含本机运行资料、个人会话、测试夹具、截图、验收报告、数据库、上传文件、凭据或目录归档。不要将这些文件加入Git。
