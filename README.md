# raspberry-pi-os-ful-yonetim-telegram-script
raspberry pi os terminalinde yapılacak her şeyi, telegramdan yönetebilirsiniz. tek yapmanız gereken bot token, chat id tanımlamaktır.

## Kullanım
Yalnızca Python 3 gerekir (ek paket yok).

```
export BOT_TOKEN=123:ABC CHAT_ID=123456789   # veya ilk çalıştırmada sorulur (config.json)
python3 bot.py
```
Bot, tek tıklamalı menü sunar: update, upgrade, full-upgrade, autoremove, autoclean, program kur/kaldır,
ekran kilitleme, oturum kapatma, yeniden başlatma, kapatma. sudo şifresi gerekirse bot Telegram'dan sorar
(şifre mesajı silinir, 5 dk bellekte tutulur). Yalnızca tanımlı chat ID'ye yanıt verir.
