# 📅 Telegram Planner Bot — Railway Deploy

Бот-планировщик с напоминаниями, статистикой и системой «ещё 5 минуточек».

---

## Возможности

- Планирование на **день / неделю / месяц**
- Добавление задач с временными интервалами (`10:00–11:30`)
- **Напоминания** точно в указанное время
- Если нет ответа — повтор через 5 минут автоматически
- Кнопки: ✅ Сделал / 🔄 В процессе / ⏰ Ещё 5 минуточек
- **Отчёт**: сколько выполнено в срок vs отложено

---

## Быстрый старт

### 1. Получить токен бота

Откройте [@BotFather](https://t.me/BotFather) в Telegram:
```
/newbot
```
Скопируйте полученный токен.

### 2. Установить зависимости

```bash
pip install -r requirements.txt
```

### 3. Настроить токен

**Вариант A — переменная окружения (рекомендуется):**
```bash
export BOT_TOKEN="123456:ABC-DEF..."
export TIMEZONE="Europe/Moscow"   # опционально
```

**Вариант B — напрямую в `config.py`:**
```python
BOT_TOKEN = "123456:ABC-DEF..."
TIMEZONE  = "Europe/Moscow"
```

### 4. Запустить

```bash
python bot.py
```

---

## Структура проекта

```
planner_bot/
├── bot.py           # основная логика, хэндлеры, планировщик
├── database.py      # SQLite-обёртка
├── config.py        # токен и таймзона
├── requirements.txt
└── README.md
```

---

## Команды бота

| Команда     | Описание                        |
|-------------|----------------------------------|
| `/start`    | Приветствие                      |
| `/plan`     | Начать планирование              |
| `/mytasks`  | Посмотреть предстоящие задачи    |
| `/report`   | Статистика выполнения            |
| `/help`     | Справка                          |

---

## Логика напоминаний

```
В указанное время → отправляет напоминание
    │
    ├─ ✅ Сделал      → задача помечена выполненной
    ├─ 🔄 В процессе  → повтор через 5 мин
    ├─ ⏰ Ещё 5 мин   → повтор через 5 мин
    └─ (нет ответа)   → автоповтор через 5 мин
```

---

## Деплой на сервере (опционально)

Создайте файл `/etc/systemd/system/planner-bot.service`:

```ini
[Unit]
Description=Telegram Planner Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/planner_bot
ExecStart=/usr/bin/python3 bot.py
Restart=always
Environment=BOT_TOKEN=ВАШ_ТОКЕН
Environment=TIMEZONE=Europe/Moscow

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable planner-bot
sudo systemctl start planner-bot
```

---

## Часовые пояса

Примеры значений для `TIMEZONE`:
- `Europe/Moscow` — Москва (UTC+3)
- `Asia/Yekaterinburg` — Екатеринбург (UTC+5)
- `Asia/Novosibirsk` — Новосибирск (UTC+7)
- `Europe/Kiev` — Киев (UTC+2/+3)
- `Europe/Madrid` — Мадрид (UTC+1/+2)
