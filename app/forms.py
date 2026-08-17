import ipaddress

from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import (
    BooleanField,
    HiddenField,
    IntegerField,
    PasswordField,
    RadioField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    URL,
    DataRequired,
    EqualTo,
    Length,
    NumberRange,
    Optional,
    Regexp,
    ValidationError,
)

from app.services.email_templates import (
    MAIL_TEMPLATE_KEYS,
    clean_email_subject,
    contains_unsafe_email_html,
    missing_required_placeholders,
    sanitize_email_html,
    unknown_placeholders,
)


def smtp_host_validator(_form, field) -> None:
    value = (field.data or "").strip()
    if not value or len(value) > 255:
        raise ValidationError("请输入有效的SMTP服务器地址。")
    if any(character in value for character in "\r\n /\\?#@"):
        raise ValidationError("SMTP服务器只能填写主机名或IP地址。")
    normalized = value.strip("[]")
    try:
        ipaddress.ip_address(normalized)
        return
    except ValueError:
        pass
    try:
        labels = normalized.encode("idna").decode("ascii").split(".")
    except UnicodeError as error:
        raise ValidationError("SMTP服务器地址格式无效。") from error
    if any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or not all(character.isalnum() or character == "-" for character in label)
        for label in labels
    ):
        raise ValidationError("SMTP服务器地址格式无效。")


PASSWORD_VALIDATORS = [
    DataRequired(),
    Length(min=10, max=256),
    Regexp(r"^(?=.*[A-Za-z])(?=.*\d).+$", message="密码必须同时包含字母和数字。"),
]
EMAIL_VALIDATORS = [
    DataRequired(),
    Length(max=254),
    Regexp(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", message="请输入有效的邮箱地址。"),
]
HEX_COLOR_VALIDATORS = [
    DataRequired(),
    Regexp(r"^#[0-9A-Fa-f]{6}$", message="请输入六位十六进制颜色。"),
]


class LoginForm(FlaskForm):
    identifier = StringField("账号名称", validators=[DataRequired(), Length(max=254)])
    password = PasswordField("密码", validators=[DataRequired(), Length(max=256)])
    remember = BooleanField("在这台设备上保持登录", default=True)
    policy_consent = BooleanField(
        "我已同意隐私条款和服务政策",
        validators=[DataRequired(message="请先同意隐私条款和服务政策。")],
    )
    submit = SubmitField("安全登录")


class RegisterForm(FlaskForm):
    username = StringField(
        "ID（唯一）",
        validators=[
            DataRequired(message="请输入baka网关 ID。"),
            Length(min=3, max=50, message="baka网关 ID 需要 3 到 50 个字符。"),
            Regexp(
                r"^[A-Za-z0-9_.-]+$",
                message="只能使用字母、数字、点、短横线和下划线。",
            ),
        ],
    )
    display_name = StringField(
        "用户名",
        validators=[
            DataRequired(message="请输入用户名。"),
            Length(min=2, max=80, message="用户名需要 2 到 80 个字符。"),
        ],
    )
    email = StringField(
        "电子邮箱",
        validators=[
            DataRequired(message="请输入电子邮箱。"),
            Length(max=254, message="电子邮箱不能超过 254 个字符。"),
            Regexp(
                r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
                message="请输入有效的邮箱地址。",
            ),
        ],
    )
    password = PasswordField(
        "密码",
        validators=[
            DataRequired(message="请输入密码。"),
            Length(min=10, max=256, message="密码至少需要 10 个字符。"),
            Regexp(
                r"^(?=.*[A-Za-z])(?=.*\d).+$",
                message="密码必须同时包含字母和数字。",
            ),
        ],
    )
    password_confirm = PasswordField(
        "确认密码",
        validators=[
            DataRequired(message="请再次输入密码。"),
            EqualTo("password", message="两次密码不一致。"),
        ],
    )
    policy_consent = BooleanField(
        "我已同意隐私条款和服务政策",
        validators=[DataRequired(message="请先同意隐私条款和服务政策。")],
    )
    submit = SubmitField("创建账号")


class FirstAdministratorForm(FlaskForm):
    username = StringField(
        "管理员 ID",
        validators=[
            DataRequired(),
            Length(min=3, max=50),
            Regexp(r"^[A-Za-z0-9_.-]+$", message="只能使用字母、数字、点、短横线和下划线。"),
        ],
    )
    display_name = StringField("管理员昵称", validators=[DataRequired(), Length(min=2, max=80)])
    email = StringField("管理员邮箱", validators=EMAIL_VALIDATORS)
    password = PasswordField("管理员密码", validators=PASSWORD_VALIDATORS)
    password_confirm = PasswordField(
        "确认管理员密码",
        validators=[DataRequired(), EqualTo("password", message="两次密码不一致。")],
    )
    submit = SubmitField("创建首位管理员")


class ForgotPasswordForm(FlaskForm):
    identifier = StringField("用户名或邮箱", validators=[DataRequired(), Length(max=254)])
    submit = SubmitField("提交恢复申请")

class ForgotPasswordRequestForm(FlaskForm):
    """Request code for password reset."""

    submit = SubmitField("发送验证码")


class PasswordResetConfirmForm(FlaskForm):
    """Confirm password reset with new password."""
    
    new_password = PasswordField(
        "新密码",
        validators=[
            DataRequired(message="请输入新密码。"),
            Length(min=10, max=256, message="密码至少需要 10 个字符。"),
            Regexp(r"^(?=.*[A-Za-z])(?=.*\d).+$", message="密码必须同时包含字母和数字。"),
        ],
    )
    new_password_confirm = PasswordField(
        "确认新密码",
        validators=[
            DataRequired(message="请再次输入新密码。"),
            EqualTo("new_password", message="两次密码不一致。"),
        ],
    )
    submit = SubmitField("重置密码")


class TwoFactorForm(FlaskForm):
    code = StringField(
        "六位验证码",
        validators=[DataRequired(), Regexp(r"^\d{6}$", message="请输入六位数字验证码。")],
    )
    submit = SubmitField("完成验证")


class ProfileForm(FlaskForm):
    username = StringField(
        "baka网关 ID",
        validators=[
            DataRequired(),
            Length(min=3, max=50),
            Regexp(r"^[A-Za-z0-9_.-]+$", message="只能使用字母、数字、点、短横线和下划线。"),
        ],
    )
    display_name = StringField("显示名称", validators=[DataRequired(), Length(min=2, max=80)])
    email = StringField("邮箱", validators=EMAIL_VALIDATORS)
    avatar = FileField("头像图片")
    remove_avatar = BooleanField("移除当前头像")
    submit = SubmitField("保存资料")


class ClientForm(FlaskForm):
    name = StringField("应用名称", validators=[DataRequired(), Length(min=2, max=100)])
    description = TextAreaField("应用说明", validators=[Optional(), Length(max=240)])
    homepage_url = StringField("应用首页", validators=[DataRequired(), URL(), Length(max=500)])
    privacy_policy_url = StringField(
        "隐私条款地址", validators=[DataRequired(), URL(), Length(max=500)]
    )
    service_terms_url = StringField(
        "服务政策地址", validators=[DataRequired(), URL(), Length(max=500)]
    )
    icon_url = StringField("应用图标地址", validators=[Optional(), URL(), Length(max=500)])
    redirect_uris = TextAreaField("允许的回调地址", validators=[DataRequired()])
    scopes = HiddenField(validators=[Optional(), Length(max=300)])
    allow_profile = BooleanField("昵称", default=True)
    allow_email = BooleanField("电子邮箱", default=True)
    allow_avatar = BooleanField("头像", default=True)
    is_active = BooleanField("允许接入", default=True)
    submit = SubmitField("保存应用")


class MailProviderForm(FlaskForm):
    name = StringField("连接名称", validators=[DataRequired(), Length(min=2, max=80)])
    host = StringField("SMTP服务器", validators=[DataRequired(), smtp_host_validator])
    port = IntegerField(
        "端口",
        validators=[DataRequired(), NumberRange(min=1, max=65535)],
        default=587,
    )
    security_mode = SelectField(
        "连接安全",
        choices=[
            ("starttls", "STARTTLS（推荐）"),
            ("ssl", "SSL / TLS"),
            ("plain", "无加密（仅限本机）"),
        ],
        validators=[DataRequired()],
        default="starttls",
    )
    username = StringField("SMTP账号", validators=[Optional(), Length(max=254)])
    password = PasswordField("SMTP密码", validators=[Optional(), Length(max=512)])
    clear_password = BooleanField("清除已经保存的SMTP密码")
    sender_email = StringField("发件邮箱", validators=EMAIL_VALIDATORS)
    sender_name = StringField(
        "发件人名称",
        validators=[DataRequired(), Length(min=1, max=100)],
        default="baka网关",
    )
    reply_to = StringField(
        "回复邮箱",
        validators=[Optional(), *EMAIL_VALIDATORS[1:]],
    )
    timeout_seconds = IntegerField(
        "连接超时（秒）",
        validators=[DataRequired(), NumberRange(min=3, max=60)],
        default=15,
    )
    is_active = BooleanField("启用这条邮件连接", default=True)
    is_default = BooleanField("设为默认发送连接")
    submit = SubmitField("保存邮件连接")


class MailTestForm(FlaskForm):
    recipient = StringField("测试收件邮箱", validators=EMAIL_VALIDATORS)
    submit = SubmitField("发送测试邮件")


class MailTemplateForm(FlaskForm):
    template_key = HiddenField(validators=[DataRequired()])
    subject = StringField("邮件主题", validators=[DataRequired(), Length(max=150)])
    body_html = TextAreaField("邮件正文", validators=[DataRequired(), Length(max=50000)])
    submit = SubmitField("保存邮件模板")

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        try:
            self.subject.data = clean_email_subject(self.subject.data)
        except ValueError as error:
            self.subject.errors.append(str(error))
            return False
        if self.template_key.data not in MAIL_TEMPLATE_KEYS:
            self.body_html.errors.append("邮件模板类型无效。")
            return False
        if contains_unsafe_email_html(self.body_html.data):
            self.body_html.errors.append("邮件正文包含不允许的标签、链接或样式内容。")
            return False
        unknown = unknown_placeholders(self.template_key.data, self.body_html.data)
        if unknown:
            self.body_html.errors.append(
                "邮件正文包含未知参数：" + "、".join(sorted(unknown)) + "。"
            )
            return False
        missing = missing_required_placeholders(
            self.template_key.data,
            f"{self.subject.data}\n{self.body_html.data}",
        )
        if missing:
            self.body_html.errors.append(
                "邮件正文缺少必填参数：" + "、".join(sorted(missing)) + "。"
            )
            return False
        self.body_html.data = sanitize_email_html(self.body_html.data)
        if not self.body_html.data:
            self.body_html.errors.append("邮件正文不能为空。")
            return False
        return True


class AdminEmailVerificationForm(FlaskForm):
    code = StringField(
        "六位邮箱验证码",
        validators=[
            DataRequired(message="请输入邮件中的六位验证码。"),
            Regexp(r"^\d{6}$", message="验证码必须是六位数字。"),
        ],
    )
    submit = SubmitField("验证管理员邮箱")


class EmailVerificationForm(FlaskForm):
    code = StringField(
        "六位邮箱验证码",
        validators=[
            DataRequired(message="请输入邮件中的六位验证码。"),
            Regexp(r"^\d{6}$", message="验证码必须是六位数字。"),
        ],
    )
    submit = SubmitField("完成邮箱验证")


class EmailPolicyForm(FlaskForm):
    registration_enabled = BooleanField("注册必须完成邮箱验证")
    profile_verification_enabled = BooleanField("允许账号验证已有邮箱")
    password_reset_enabled = BooleanField("允许通过邮箱安全找回密码")
    code_ttl_minutes = SelectField(
        "验证码有效时间",
        choices=[(5, "5 分钟"), (10, "10 分钟（推荐）"), (15, "15 分钟")],
        coerce=int,
        validators=[DataRequired()],
        default=10,
    )
    resend_seconds = SelectField(
        "再次发送等待",
        choices=[
            (60, "60 秒（推荐）"),
            (90, "90 秒"),
            (120, "120 秒"),
            (300, "300 秒"),
        ],
        coerce=int,
        validators=[DataRequired()],
        default=60,
    )
    max_attempts = SelectField(
        "单个验证码尝试次数",
        choices=[(3, "3 次"), (4, "4 次"), (5, "5 次（推荐）")],
        coerce=int,
        validators=[DataRequired()],
        default=5,
    )
    submit = SubmitField("保存验证策略")


class UserAdminForm(FlaskForm):
    status = SelectField(
        "账号状态",
        choices=[("active", "正常"), ("suspended", "已停用"), ("locked", "已锁定")],
        validators=[DataRequired()],
    )
    role = SelectField("角色", choices=[("member", "普通用户"), ("administrator", "管理员")])
    new_password = PasswordField(
        "设置新密码",
        validators=[
            Optional(),
            Length(min=10, max=256),
            Regexp(r"^(?=.*[A-Za-z])(?=.*\d).+$", message="密码必须同时包含字母和数字。"),
        ],
    )
    new_password_confirm = PasswordField(
        "确认新密码",
        validators=[Optional(), EqualTo("new_password", message="两次密码不一致。")],
    )
    submit = SubmitField("保存账号")


class TransitionSettingsForm(FlaskForm):
    transition_style = RadioField("页面过渡方式", validators=[DataRequired()])
    transition_duration = IntegerField(
        "动画时间（毫秒）",
        validators=[DataRequired(), NumberRange(min=300, max=2400)],
    )
    transition_color_start = StringField("覆盖起始色", validators=HEX_COLOR_VALIDATORS)
    transition_color_middle = StringField("覆盖过渡色", validators=HEX_COLOR_VALIDATORS)
    transition_color_end = StringField("覆盖结束色", validators=HEX_COLOR_VALIDATORS)
    submit = SubmitField("保存动效设置")


class DialogAppearanceForm(FlaskForm):
    dialog_style = RadioField("弹窗样式", validators=[DataRequired()])
    dialog_color_start = StringField("弹窗起始色", validators=HEX_COLOR_VALIDATORS)
    dialog_color_end = StringField("弹窗结束色", validators=HEX_COLOR_VALIDATORS)
    dialog_accent = StringField("弹窗强调色", validators=HEX_COLOR_VALIDATORS)
    dialog_radius = IntegerField(
        "弹窗圆角", validators=[DataRequired(), NumberRange(min=14, max=42)]
    )
    dialog_width = IntegerField(
        "弹窗宽度", validators=[DataRequired(), NumberRange(min=360, max=720)]
    )
    dialog_backdrop_blur = IntegerField(
        "背景模糊", validators=[DataRequired(), NumberRange(min=0, max=30)]
    )
    dialog_shadow = RadioField("阴影强度", validators=[DataRequired()])
    submit = SubmitField("保存弹窗外观")


class InterfaceAppearanceForm(FlaskForm):
    font_style = RadioField("全局字体", validators=[DataRequired()])
    submit = SubmitField("保存界面风格")


class AuthorizationRequestForm(FlaskForm):
    stage = HiddenField(validators=[DataRequired()])
    decision = StringField(validators=[DataRequired()])
    response_type = HiddenField(validators=[DataRequired()])
    client_id = HiddenField(validators=[DataRequired()])
    redirect_uri = HiddenField(validators=[DataRequired()])
    scope = HiddenField(validators=[DataRequired()])
    state = HiddenField()
    nonce = HiddenField()
    code_challenge = HiddenField(validators=[DataRequired()])
    code_challenge_method = HiddenField(validators=[DataRequired()])


class ConsentPermissionsForm(AuthorizationRequestForm):
    policy_consent = BooleanField(
        "我同意该应用的服务政策和隐私条款",
        validators=[DataRequired(message="请先同意应用政策，再进入下一步。")],
    )


class ConsentConfirmationForm(AuthorizationRequestForm):
    pass


class ChangeEmailRequestForm(FlaskForm):
    """Request code for new email verification."""

    new_email = StringField("新邮箱", validators=[DataRequired(), Length(max=254)])
    submit = SubmitField("发送验证码")


class EmptyForm(FlaskForm):
    submit = SubmitField("确认")
