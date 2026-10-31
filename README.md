# GLaDOS 自动签到

每天帮你自动打开 [签到页](https://glados.network/console/checkin) 点一次签到,领积分,不用自己操心。

核心思路很简单:你手动登录一次,把浏览器里的 Cookie 复制出来,脚本每天带着这个 Cookie 去调签到接口就行,不需要账号密码,也不会碰你的邮箱验证码。

## 目录结构

```shell
checkin.py                  # 签到脚本,每天跑它就行
requirements.txt            # 依赖,只有 requests
README.md                   # 你正在看的这份说明
.github/workflows/         # GitHub 定时任务配置
    gladosCheck.yml         # 每天北京时间 09:30 自动跑
```

## 准备工作

### 1. 拿个账号

已经有号的跳过。没有号的话点我的邀请链接注册,新用户多得 14 天:

<https://glados.space/landing/BCMRD-FM8H2-ECUCT-MGCU7>

下单时再填优惠码 `MESSI` 打 9 折。

### 2. 抓一次 Cookie

这一步只需要做一次,拿到之后后面几个月都不用管:

1. 浏览器打开 [https://glados.network/console/checkin](https://glados.network/console/checkin) 并登录,顺手点一次签到确认能领积分
2. 按 `F12` 打开开发者工具,切到 `Network(网络)` 标签,刷新页面
3. 点列表里第一个请求,找到 `Request Headers` 里的 `Cookie`,右键复制整串
4. 长这样:`koa:sess=eyJ1...; koa:sess.sig=xxx; gld:accts=...; gld:sess=...;`

多账号的把几串 Cookie 用 `&` 拼起来就行,例如 `c1&c2&c3`。

## 放到 GitHub 上每天自动跑

### 1. Fork 本仓库

打开 [perfect6566/glados-checkin](https://github.com/perfect6566/glados-checkin) 点右上角 `Fork`,选你自己的账号,就有了个一模一样的仓库,后面都在你 Fork 出来的仓库里操作,不用敲 git 命令。

记住 Cookie 别写进代码,只放到下面说的 Secret 里。

### 2. 填 4 个 Secret

打开你仓库的 `Settings` → `Secrets and variables` → `Actions` → `New repository secret`,逐个添加:

| Name | 内容 | 必填 |
|---|---|---|
| `GLADOS_COOKIES` | 上一步复制的那整串 Cookie | 是 |
| `NOTIFY_EMAIL` | 收件邮箱,Cookie 失效时收到提醒 | 否,配了才有邮件提醒 |
| `MAIL_USERNAME` | 发件 QQ 邮箱,和收件填同一个就行 | 否,配了才有邮件提醒 |
| `MAIL_PASSWORD` | QQ 邮箱授权码 | 否,配了才有邮件提醒 |

QQ 邮箱授权码拿法:QQ 邮箱 → 设置 → 账户 → 开启 `IMAP/SMTP服务`,按提示用手机发条短信就行。注意填的是授权码,不是 QQ 登录密码。

发件和收件可以用同一个 QQ 邮箱,自己发自己。兑换计划 `GLADOS_EXCHANGE_PLAN` 默认 `none`(不自动兑换),想开再去 `gladosCheck.yml` 里改。

### 3. 先手动跑一遍

`Actions` → 左边选工作流 → 点 `Run workflow` → 等 1 分钟看日志:

- `签到成功 points=4` → 今天第一次签,完美
- `重复签到 Today's observation logged` → 今天已经在网页上签过了,说明 Cookie 是好的
- `签到失败(Cookie失效?) No permission` → Cookie 贴错了或者过期了,重新抓一次

没问题的话,以后每天北京时间 09:30 自动跑,电脑关机也没事。想换时间就改 `gladosCheck.yml` 里的 `cron`,注意那是 UTC 时间,北京时间要加 8 小时。

## 在自己电脑上跑也行

```powershell
pip install -r requirements.txt

# 直接传 Cookie
python checkin.py --cookies "koa:sess=...; koa:sess.sig=..."

# 或者走环境变量
$env:GLADOS_COOKIES="你的cookie整串"
python checkin.py
```

## Cookie 多久换一次

不用定期换。Cookie 自带 30 天有效期,平时用着会自动续,几个月换一次是常态。

只有签到返回 `code=-2 No permission` 时才需要换,脚本已经帮你盯着了:当天全部失败会让 Action 变红,并且给你收件邮箱发一封提醒,标题是 `GLaDOS 签到失败:Cookie可能失效`。

邮件正文里有签到页链接,点开就能操作:

```text
1. 打开签到页(登录后手动点一次签到,不断签):
   https://glados.network/console/checkin
2. F12 -> Network -> 刷新 -> 第一个请求
   -> Request Headers -> 复制 Cookie
3. 回到 GitHub 仓库 Settings -> Secrets -> Actions,
   把 GLADOS_COOKIES 更新成新的
```

建议收到邮件后先手动点一次签到兜底,再去更新 Secret。

## 积分兑换

默认不自动兑换,想开的话去 `gladosCheck.yml` 把 `GLADOS_EXCHANGE_PLAN` 改成下面之一:

| 值 | 要多少分 | 换多少天 |
|---|---|---|
| `plan100` | 100 | 10 天 |
| `plan200` | 200 | 30 天 |
| `plan500` | 500 | 100 天 |

## 常见情况

- 显示重复签到:正常的,说明今天已经签过了,明天会继续签
- 显示设备不匹配(`device-mismatch`):脚本会自己换个 UA 重试一次,还不行再看登录设备
- Action 很久没跑:GitHub 会暂停长期没提交的仓库的定时任务,手动 `Run workflow` 一次就恢复了
- 接口变了:新站改版比较勤,如果突然全挂了,大概率是接口变了,重新抓个包看看 `Network` 里签到请求的样子就行

## 邀请信息

- 邀请码 `BCMRD-FM8H2-ECUCT-MGCU7`
- 优惠码 `MESSI`
- 邀请页 <https://glados.network/console/invites>
