# baka网关 bakagateway

baka网关是一个本地优先、可自托管的统一登录网关。它为博客等接入应用提供 OAuth 2.0 / OpenID Connect 单点登录，自带完整的账号体系、双重验证和管理员后台，全部资源本地提供，开箱即用。

## 主要功能

**协议能力**

- OAuth 2.0 授权码模式 + PKCE（S256）、刷新令牌、令牌撤销与自省。
- OpenID Connect：发现文档、RS256 签名 ID Token、JWKS、UserInfo。

**账号与安全**

- 用户名或邮箱登录、注册、邮箱验证码、找回密码。
- 新设备或新网络登录时，可强制要求绑定邮箱验证码，验证通过才建立会话；邮件服务异常时自动停用该保护。
- scrypt 密码哈希、服务器端会话、登录限流与锁定、设备会话撤销。
- RFC 6238 TOTP 双重验证，二维码由本地离线渲染，不依赖外部服务。

**个人中心**

- 我的主页、修改资料（本地圆形头像裁剪）、我的平台、登录设备、操作日志、账号安全。
- 更换绑定邮箱需先向新邮箱发送验证码并确认。

**管理员后台**

- 用户与角色权限、接入应用登记、登录与审计日志。
- 外观主题、页尾配置、系统弹窗与动效设置。
- 邮件与验证：SMTP 连接管理、验证策略开关、邮件模板可视化编辑。
- 首次启动没有管理员时，会自动进入一次性的"创建首位管理员"向导。

界面采用浅蓝圆角卡片风格，全部前端资源本地提供，无 CDN 与外部图片依赖。

## 快速开始

环境要求：Windows 与 Python 3.12～3.14，依赖已随 `wheelhouse/` 离线提供，无需联网。

```bat
start.bat
```

首次启动会自动创建虚拟环境、离线安装依赖、迁移并初始化数据库。启动后访问 `http://127.0.0.1:5100/`，按向导创建首位管理员即可开始使用；也可以在命令行交互创建：

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

环境变量样例见 `.env.example`；正式部署请设置足够长的随机 `CLOUD_GATEWAY_SECRET_KEY`。

## 开启邮箱验证能力

注册验证、更换邮箱、找回密码以及新设备登录验证都依赖 SMTP：

1. 以管理员身份进入后台「邮件与验证 → 邮件服务」，添加 SMTP 连接并完成测试。
2. 在「验证策略」页验证管理员自身邮箱，解锁公开邮件策略。
3. 按需开启各流程开关，例如"新设备或新网络登录需要邮箱验证"。

任一门槛失效或邮件投递出现故障时，相关能力会自动停用，不会让用户卡在无法收到的验证码上。

## 接入应用

- `/.well-known/openid-configuration`
- `/oauth/authorize`
- `/oauth/token`
- `/oauth/userinfo`
- `/oauth/jwks.json`
- `/oauth/revoke`
- `/oauth/introspect`

客户端必须登记精确回调地址并使用授权码 + PKCE；生产环境只接受 HTTPS 回调，本机 `127.0.0.1` 调试例外。

## 部署建议

- 本地运行：`start.bat`（Windows）或 `scripts/dev.ps1`。
- 生产环境：Debian 12 + Gunicorn 启动 `wsgi:app`，由 nginx/Caddy 反向代理终止 TLS，并开启 Cookie Secure 与 HSTS。
- 定期清理过期邮件验证记录：`flask --app wsgi:app purge-email-security`，示例定时任务见 `scripts/debian/`（每天本地时间 03:15）。
- SQLite 适合单机中小规模场景；持续高并发写入需另行迁移数据库。

## 技术要点

- Python + Flask + Jinja2 + SQLAlchemy + Flask-Migrate，数据保存在本地 SQLite。
- 数据库结构全部由迁移脚本管理，内置触发器保护"至少一位可用管理员"不变量。
- 敏感信息（SMTP 密码、待验证邮箱、验证码等）使用 AES-GCM 加密或密钥哈希存储，审计日志不落明文。
- 邮件模板支持白名单净化后的 HTML 可视化编辑，危险标签与脚本一律过滤。
- 安全基线：HttpOnly 会话 Cookie、CSP、登录限流、审计日志、密钥本地生成。

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
