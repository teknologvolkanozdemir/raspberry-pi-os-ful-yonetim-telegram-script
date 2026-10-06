#!/usr/bin/env python3
"""Raspberry Pi OS yönetimi için Telegram botu (yalnızca standart kütüphane).

Kurulum: BOT_TOKEN ve CHAT_ID ortam değişkenleri ya da config.json
({"bot_token": "...", "chat_id": 123}) ile tanımlanır; yoksa ilk çalıştırmada sorulur.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
PKG_RE = re.compile(r"^[a-z0-9][a-z0-9+.\-]*(\s+[a-z0-9][a-z0-9+.\-]*)*$")
APT = "DEBIAN_FRONTEND=noninteractive apt-get -y"

# (buton, komut, sudo gerekli mi)
ACTIONS = {
    "update": ("🔄 Güncelle (update)", f"{APT} update", True),
    "upgrade": ("⬆️ Upgrade", f"{APT} upgrade", True),
    "full_upgrade": ("⏫ Full-upgrade", f"{APT} full-upgrade", True),
    "autoremove": ("🧹 Autoremove", f"{APT} autoremove", True),
    "autoclean": ("🧽 Autoclean", f"{APT} autoclean", True),
    "shutdown": ("⏻ Kapat", "shutdown -h now", True),
    "reboot": ("🔁 Yeniden başlat", "reboot", True),
    "logout": ("🚪 Oturum kapat", "loginctl terminate-user \"$(logname 2>/dev/null || id -un)\"", False),
    "lock": ("🔒 Ekranı kilitle", "loginctl lock-sessions", False),
    "status": ("📊 Durum", "uptime; free -h; df -h /; vcgencmd measure_temp 2>/dev/null", False),
}
CONFIRM = {"shutdown", "reboot", "logout"}
LAYOUT = [["update", "upgrade"], ["full_upgrade", "autoremove"], ["autoclean", "status"],
          ["install", "remove"], ["lock", "logout"], ["reboot", "shutdown"]]
LABELS = {"install": "📦 Program kur", "remove": "🗑 Program kaldır"}


def load_config():
    token = os.environ.get("BOT_TOKEN")
    chat = os.environ.get("CHAT_ID")
    if not (token and chat) and os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            data = json.load(f)
        token, chat = data.get("bot_token"), data.get("chat_id")
    if not (token and chat):
        token = input("Bot token: ").strip()
        chat = input("Chat ID: ").strip()
        with open(os.open(CONFIG_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
            json.dump({"bot_token": token, "chat_id": int(chat)}, f)
    return token, int(chat)


def valid_packages(text):
    return bool(PKG_RE.match(text.strip()))


def run_command(cmd, use_sudo, pw=None, timeout=3600):
    """Komutu çalıştırır. sudo için şifre stdin'den (-S) verilir. (rc, çıktı) döner."""
    if use_sudo:
        cmd = f"sudo -S -p '' sh -c {shell_quote(cmd)}"
    try:
        p = subprocess.run(cmd, shell=True, input=(pw + "\n") if (use_sudo and pw) else None,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "Zaman aşımı"
    return p.returncode, (p.stdout + p.stderr).strip()


def shell_quote(s):
    import shlex
    return shlex.quote(s)


def sudo_needs_password():
    return subprocess.run("sudo -n true", shell=True, capture_output=True).returncode != 0


class Bot:
    def __init__(self, token, chat_id):
        self.api = f"https://api.telegram.org/bot{token}/"
        self.chat_id = chat_id
        self.pending = None  # ("install"|"remove"|"password", ...)
        self.password = None
        self.password_time = 0

    def call(self, method, **params):
        data = urllib.parse.urlencode({k: json.dumps(v) if isinstance(v, (dict, list)) else v
                                       for k, v in params.items()}).encode()
        with urllib.request.urlopen(self.api + method, data, timeout=70) as r:
            return json.load(r)

    def send(self, text, markup=None):
        params = {"chat_id": self.chat_id, "text": text[-4000:] or "(boş)"}
        if markup:
            params["reply_markup"] = markup
        self.call("sendMessage", **params)

    def menu(self):
        kb = [[{"text": ACTIONS[a][0] if a in ACTIONS else LABELS[a], "callback_data": a} for a in row]
              for row in LAYOUT]
        self.send("Ne yapmak istersiniz?", {"inline_keyboard": kb})

    def execute(self, cmd, use_sudo):
        if use_sudo and sudo_needs_password():
            if not (self.password and time.time() - self.password_time < 300):
                self.pending = ("password", cmd)
                self.send("🔑 sudo şifresi gerekiyor. Lütfen şifrenizi yazın "
                          "(mesaj okunduktan sonra silinir):")
                return
        self.send("⏳ Çalışıyor...")
        rc, out = run_command(cmd, use_sudo, self.password)
        if rc != 0 and use_sudo and "incorrect password" in out:
            self.password = None
        self.send(f"{'✅' if rc == 0 else '❌'} Çıkış kodu: {rc}\n{out}")
        self.menu()

    def on_callback(self, cb):
        action = cb["data"]
        self.call("answerCallbackQuery", callback_query_id=cb["id"])
        if action in ("install", "remove"):
            self.pending = (action,)
            self.send("Paket adı(ları)nı yazın:")
        elif action.startswith("yes_") and action[4:] in ACTIONS:
            _, cmd, sudo = ACTIONS[action[4:]]
            self.execute(cmd, sudo)
        elif action == "cancel":
            self.pending = None
            self.menu()
        elif action in ACTIONS:
            label, cmd, sudo = ACTIONS[action]
            if action in CONFIRM:
                self.send(f"{label} onaylıyor musunuz?", {"inline_keyboard": [[
                    {"text": "Evet", "callback_data": "yes_" + action},
                    {"text": "İptal", "callback_data": "cancel"}]]})
            else:
                self.execute(cmd, sudo)

    def on_message(self, msg):
        text = msg.get("text", "")
        pending, self.pending = self.pending, None
        if pending and pending[0] == "password":
            self.password, self.password_time = text, time.time()
            try:
                self.call("deleteMessage", chat_id=self.chat_id, message_id=msg["message_id"])
            except Exception:
                pass
            self.execute(pending[1], True)
        elif pending and not text.startswith("/"):
            if not valid_packages(text):
                self.send("Geçersiz paket adı.")
                return self.menu()
            verb = "install" if pending[0] == "install" else "purge"
            self.execute(f"{APT} {verb} {text.strip()}", True)
        else:
            self.menu()

    def run(self):
        offset = None
        self.menu()
        while True:
            try:
                res = self.call("getUpdates", timeout=50, **({"offset": offset} if offset else {}))
            except Exception as e:
                print("Hata:", e, file=sys.stderr)
                time.sleep(5)
                continue
            for u in res.get("result", []):
                offset = u["update_id"] + 1
                cb, msg = u.get("callback_query"), u.get("message")
                src = cb["message"]["chat"]["id"] if cb else msg["chat"]["id"] if msg else None
                if src != self.chat_id:
                    continue
                try:
                    self.on_callback(cb) if cb else self.on_message(msg)
                except Exception as e:
                    print("Hata:", e, file=sys.stderr)


if __name__ == "__main__":
    Bot(*load_config()).run()
