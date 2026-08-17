# baka网关 bakagateway

baka网关是一个本地优先、可自托管的统一登录网关：为博客等接入应用提供 OAuth 2.0 / OpenID Connect 单点登录，并内置账号管理、双重验证与管理员后台。

> 这是全新未初始化副本：没有数据库、没有管理员账号、没有任何业务数据与密钥。
> 初始化步骤：运行 `start.bat`（自动创建虚拟环境、离线安装依赖、迁移并初始化数据库），
> 访问 `http://127.0.0.1:5100/` 完成"创建首位管理员"向导，或用 `start.bat --create-admin` 在命令行创建。

## 主要功能

- OAuth 2.0 授权码模式 + PKCE（S256）、刷新令牌、令牌撤销与自省。
- OpenID Connect：发现文档、RS256 签名 ID Token、JWKS、UserInfo。
- 用户名或邮箱登录、注册、邮箱验证码、找回密码。
- scrypt 密码哈希、服务器端会话、登录限流与锁定、设备会话撤销。
- RFC 6238 TOTP 双重验证，二维码由本地离线渲染，不依赖外部服务。
- 个人中心：我的主页、修改资料（本地圆形头像裁剪）、我的平台、登录设备、操作日志、账号安全。
- 管理员后台：用户与角色权限、接入应用登记、登录与审计日志、外观主题、邮件模板可视化编辑、SMTP 连接与邮件策略。
- 首次启动无管理员时，自动进入一次性"创建首位管理员"向导。
- 全部前端资源本地提供，无 CDN 与外部图片依赖。

## 快速开始

环境要求：Windows 与 Python 3.12～3.14，依赖已随 `wheelhouse/` 离线提供，无需联网。

```bat
start.bat
```

启动后访问 `http://127.0.0.1:5100/`：

- 没有管理员时进入"创建首位管理员"向导，完成后自动登录；
- 也可以在命令行交互创建首位管理员：

```bat
start.bat --create-admin
```

只做完整预检而不启动服务：

```bat
start.bat --check-only
```

修改监听地址或端口（默认 127.0.0.1:5100）：

```bat
set CLOUD_GATEWAY_HOST=127.0.0.1
set CLOUD_GATEWAY_PORT=5101
start.bat
```

环境变量样例见 `.env.example`；正式部署必须设置长随机 `CLOUD_GATEWAY_SECRET_KEY`。

## 技术要点

- Python + Flask + Jinja2 + SQLAlchemy + Flask-Migrate，数据保存在本地 SQLite。
- 数据库结构全部由迁移脚本管理（`flask db upgrade`），内置触发器保护"至少一位可用管理员"不变量。
- 邮件验证码内容使用 AES-GCM 加密存储，定时任务清理过期记录。
- 管理员邮件模板支持白名单净化后的 HTML 可视化编辑，危险标签与脚本一律过滤。
- 安全基线：HttpOnly 会话 Cookie、CSP、登录限流、审计日志、密钥本地生成。

## OAuth/OIDC 端点

- `/.well-known/openid-configuration`
- `/oauth/authorize`
- `/oauth/token`
- `/oauth/userinfo`
- `/oauth/jwks.json`
- `/oauth/revoke`
- `/oauth/introspect`

客户端必须登记精确回调地址并使用授权码 + PKCE；生产环境只接受 HTTPS 回调，本机 `127.0.0.1` 调试例外。

## 部署概述

- 本地开发：`start.bat`（Windows）或 `scripts/dev.ps1`。
- 生产环境：Debian 12 + Gunicorn 启动 `wsgi:app`，本机 nginx/Caddy 反向代理终止 TLS，开启 Cookie Secure 与 HSTS。
- 定期清理过期邮件验证记录：`flask --app wsgi:app purge-email-security`，示例定时任务见 `scripts/debian/`（每天本地时间 03:15）。
- SQLite 适合单机中小规模场景；持续高并发写入需另行迁移数据库。

## 目录结构

```
app/                  应用源码（蓝图、服务层、模板、静态资源）
migrations/           数据库迁移脚本
scripts/              启动与部署脚本（PowerShell、systemd 样例）
wheelhouse/           离线依赖包
start.bat             Windows 一键启动入口
wsgi.py               WSGI 入口
.env.example          环境变量样例
requirements*.txt     依赖清单
```
