"""
GLaDOS 每日自动签到 (glados.network)
原理: 带 Cookie 直接调用签到接口,不走登录页,所以不需要账号密码/邮箱验证码.
新站登录是 邮箱 + 邮箱验证码 + Cloudflare Turnstile,无法用纯 requests 全自动登录,
所以用 Cookie 保活方案: 手动登录一次 -> 抓 Cookie -> 脚本每天带 Cookie 调 /api/user/checkin.

快速开始:
  1. pip install -r requirements.txt
  2. 手动登录 https://glados.network/console/checkin
  3. 按 F12 -> Network -> 刷新 -> 点第一个请求 -> Request Headers -> 复制 Cookie
     格式类似: koa:sess=eyJ1...; koa:sess.sig=xxx; gld:accts=...; gld:sess=...;
  4. 方式A(推荐): 设置环境变量 GLADOS_COOKIES=你的cookie, 多号用 & 连接
     方式B: 命令行 python checkin.py --cookies "cookie1&cookie2"
  5. python checkin.py, 每天跑一次即可 (GitHub Actions 见 README)
"""

import argparse
import os
import smtplib
import sys
import time
from email.mime.text import MIMEText

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============ 直接在这里填也行(方式B),多号用 & 连接 ============
CONFIG = {
    "COOKIES": "",  # 例: "koa:sess=xxx; koa:sess.sig=yyy" 或 "c1&c2"
    "DOMAINS": ["glados.network"],
    "EXCHANGE_PLAN": "none",  # none / plan100 / plan200 / plan500
    "NOTIFY_EMAIL": "",  # Cookie失效提醒收件人,推荐用 NOTIFY_EMAIL 环境变量 / Secret 传,不要写死
    "MAIL_SMTP": "smtp.qq.com",
    "MAIL_PORT": 465,
}

PLATFORM_UA = {
    "Windows": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36",
    "macOS": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36",
    "Linux": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36",
    "iPhone": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    "Android": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Mobile Safari/537.36",
}

EXCHANGE_POINTS = {"plan100": 100, "plan200": 200, "plan500": 500}


def build_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=1.0,
                  status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET", "POST"), raise_on_status=False)
    a = HTTPAdapter(max_retries=retry)
    s.mount("https://", a)
    s.mount("http://", a)
    return s


def api_call(session, domain, path, method="GET", data=None, cookie="", ua=None):
    url = f"https://{domain}/api{path}"
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "origin": f"https://{domain}",
        "referer": f"https://{domain}/console/checkin",
        "user-agent": ua or PLATFORM_UA["Windows"],
        "cookie": cookie,
        "sec-ch-ua": '"Google Chrome";v="155", "Chromium";v="155", "Not(A:Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "priority": "u=1, i",
    }
    try:
        if method.upper() == "POST":
            # 抓包证实: content-type 必须是 application/json, body 是 {"token":"glados.network"}
            headers["content-type"] = "application/json;charset=UTF-8"
            r = session.post(url, headers=headers, json=data or {}, timeout=(30, 60))
        else:
            r = session.get(url, headers=headers, timeout=(30, 60))
        if not r.ok:
            print(f"[E] [{domain}] {path} HTTP {r.status_code}: {r.text[:300]}")
            return None
        try:
            return r.json()
        except Exception:
            print(f"[E] [{domain}] {path} 非JSON响应: {r.text[:300]}")
            return None
    except Exception as e:
        print(f"[E] [{domain}] {path} 网络错误: {e}")
        return None


def send_notify(subject: str, body: str) -> None:
    """Cookie失效时发邮件提醒.GitHub Actions里用QQ SMTP发,本地没配就只打印."""
    to_addr = os.environ.get("NOTIFY_EMAIL", "") or CONFIG.get("NOTIFY_EMAIL", "")
    user = os.environ.get("MAIL_USERNAME", "")
    pwd = os.environ.get("MAIL_PASSWORD", "")
    smtp_host = os.environ.get("MAIL_SMTP", "") or CONFIG.get("MAIL_SMTP", "smtp.qq.com")
    smtp_port = int(os.environ.get("MAIL_PORT", "") or CONFIG.get("MAIL_PORT", 465))
    if not to_addr:
        print(f"[W] 未配置收件人,跳过邮件提醒: {subject}")
        return
    if not user or not pwd:
        # 本地没配发件人时不报错,只打印,方便你本地测试
        print(f"[W] 未配置 MAIL_USERNAME/MAIL_PASSWORD,跳过发邮件,请看日志: {subject}\n{body}")
        return
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = to_addr
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as s:
            s.login(user, pwd)
            s.send_message(msg)
        print(f"[I] 邮件提醒已发送到 {to_addr}")
    except Exception as e:
        print(f"[E] 邮件发送失败: {e}")


def do_checkin(session, domain, cookie):
    # token 固定为当前域名,抓包证实: POST /api/user/checkin {token: location.hostname}
    raw = api_call(session, domain, "/user/checkin", "POST",
                   data={"token": domain}, cookie=cookie)
    if raw is None:
        return {"code": -2, "status": "签到失败(网络)", "message": "网络请求失败"}
    code = raw.get("code", -2)
    msg = raw.get("message", "")
    pts = raw.get("points", 0)
    # 设备不匹配时切换 UA 重试一次 (服务端会返回 loginDevice 告诉你上次登录设备)
    if code == 4 and raw.get("reason") == "device-mismatch":
        login_device = raw.get("loginDevice")
        ua = PLATFORM_UA.get(login_device)
        if ua:
            print(f"[W] [{domain}] 设备不匹配(loginDevice={login_device}),切换UA重试一次")
            raw = api_call(session, domain, "/user/checkin", "POST",
                           data={"token": domain}, cookie=cookie, ua=ua)
            if raw is None:
                return {"code": -2, "status": "签到失败(网络)", "message": "重试网络失败"}
            code = raw.get("code", -2)
            msg = raw.get("message", "")
            pts = raw.get("points", 0)
        else:
            return {"code": 4, "status": "签到失败(设备风控)",
                    "message": f"device-mismatch loginDevice={login_device}"}
    if code == 0:
        return {"code": 0, "status": "签到成功", "message": msg, "points": pts, "raw": raw}
    if code == 1:
        return {"code": 1, "status": "重复签到", "message": msg, "points": 0, "raw": raw}
    if code == -2:
        return {"code": -2, "status": "签到失败(Cookie失效?)",
                "message": f"{msg} | 请重新登录抓Cookie更新 GLADOS_COOKIES", "raw": raw}
    return {"code": code, "status": "签到失败", "message": msg, "points": 0, "raw": raw}


def main():
    ap = argparse.ArgumentParser(description="GLaDOS 每日自动签到")
    ap.add_argument("--cookies", default="", help="Cookie,多号用&连接,优先于环境变量")
    ap.add_argument("--domains", default="", help="逗号分隔域名,默认 glados.network")
    ap.add_argument("--exchange", default="", help="none/plan100/plan200/plan500")
    args = ap.parse_args()

    raw_cookies = args.cookies or os.environ.get("GLADOS_COOKIES", "") or CONFIG["COOKIES"]
    domains = [d.strip() for d in (args.domains or os.environ.get("GLADOS_DOMAINS", "") or ",".join(CONFIG["DOMAINS"])).split(",") if d.strip()]
    exchange_plan = (args.exchange or os.environ.get("GLADOS_EXCHANGE_PLAN", "") or CONFIG["EXCHANGE_PLAN"]).strip() or "none"

    cookies = [c.strip() for c in raw_cookies.split("&") if c.strip()]
    if not cookies:
        print("[E] 未找到 Cookie!")
        print("     1) 登录 https://glados.network/console/checkin")
        print("     2) F12 -> Network -> 刷新 -> 第一个请求 -> Request Headers -> 复制 Cookie")
        print("     3) 设置环境变量 GLADOS_COOKIES=你的cookie  或  python checkin.py --cookies \"你的cookie\"")
        sys.exit(1)

    print(f"[I] 共 {len(cookies)} 个Cookie, {len(domains)} 个域名: {domains}, 兑换计划: {exchange_plan}")
    session = build_session()
    ok = repeat = fail = 0
    for idx, cookie in enumerate(cookies, 1):
        print(f"\n===== Cookie {idx} =====")
        # 脱敏打印
        print(f"[I] Cookie长度 {len(cookie)}, 开头 {cookie[:25]}...")
        for domain in domains:
            print(f"----- [{domain}] 查询剩余天数 -----")
            st = api_call(session, domain, "/user/status", "GET", cookie=cookie)
            if st and st.get("code") == 0:
                print(f"[I] [{domain}] 剩余: {st.get('data', {}).get('leftDays')}")
            else:
                print(f"[W] [{domain}] /user/status: {st}")

            print(f"----- [{domain}] 签到 -----")
            res = do_checkin(session, domain, cookie)
            print(f"[{'I' if res['code'] in (0,1) else 'E'}] [{domain}] {res['status']}: {res.get('message')} points={res.get('points',0)} raw={res.get('raw')}")
            if res["code"] == 0:
                ok += 1
            elif res["code"] == 1:
                repeat += 1
            else:
                fail += 1
                # -2 大概率是该域名下Cookie不对/没登录过,继续试下一个域名,不中断
                time.sleep(1)
                continue

            print(f"----- [{domain}] 查询积分 -----")
            pt = api_call(session, domain, "/user/points", "GET", cookie=cookie)
            if pt:
                print(f"[I] [{domain}] 积分: {pt.get('points')} streak={pt.get('streak')}")

            if exchange_plan in EXCHANGE_POINTS:
                print(f"----- [{domain}] 兑换 {exchange_plan} -----")
                ex = api_call(session, domain, "/user/exchange", "POST",
                              data={"planType": exchange_plan}, cookie=cookie)
                print(f"[I] [{domain}] 兑换结果: {ex}")
            time.sleep(1)

    print(f"\n========== 签到总结: 成功 {ok} / 重复 {repeat} / 失败 {fail} ==========")
    session.close()
    if fail > 0 and ok == 0 and repeat == 0:
        # 全部失败大概率是 Cookie 失效,发邮件提醒你去换
        subject = "GLaDOS 签到失败:Cookie可能失效,请更新 GLADOS_COOKIES"
        body = (
            "GLaDOS 每日签到全部失败,很可能是 Cookie 过期/失效。\n\n"
            f"成功 {ok} / 重复 {repeat} / 失败 {fail}\n\n"
            "请按下面步骤更新 Cookie:\n"
            "1. 打开签到页(点下面链接,登录后手动点一次 签到):\n"
            "   https://glados.network/console/checkin\n"
            "2. 按 F12 -> Network -> 刷新 -> 点第一个请求\n"
            "   -> Request Headers -> 复制 Cookie\n"
            "3. 去 GitHub 仓库 Settings -> Secrets -> Actions,\n"
            "   更新 GLADOS_COOKIES Secret 为新 Cookie。\n"
        )
        print(f"[E] {subject}")
        send_notify(subject, body)
        sys.exit(2)


if __name__ == "__main__":
    main()
