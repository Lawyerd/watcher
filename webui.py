"""[v3.0] 화면 파일(web/) 읽기 — PC 화면(desktop.html)과 휴대폰 페이지(phone.html)가
같이 쓰는 팔레트·도우미(common.css / common.js)를 각 화면의 자리 표시에 끼워 넣는다."""
import os
import sys

if getattr(sys, "frozen", False):
    WEB_DIR = os.path.join(sys._MEIPASS, "web")   # 화면 파일은 exe 안에 묶음
else:
    WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def read(name):
    with open(os.path.join(WEB_DIR, name), encoding="utf-8") as f:
        return f.read()


def page(name, **subs):
    """web/<name>의 /*@COMMON_CSS@*/·/*@COMMON_JS@*/ 자리에 공통 파일을, /*@키@*/ 자리에 subs[키]를 넣는다"""
    html = read(name).replace("/*@COMMON_CSS@*/", read("common.css")).replace("/*@COMMON_JS@*/", read("common.js"))
    for key, value in subs.items():
        html = html.replace(f"/*@{key}@*/", value)
    return html
