# Бриз

Сайт кафе «Бриз» (Пермь, Кировоградская, 12/2): банкеты, меню, обеды с доставкой,
позже — чат «вопрос-ответ» в реальном времени и приложение для гостей.

FastAPI + Jinja2, без сборщиков: CSS и JS лежат в `static/` как есть.

## Запуск локально

```powershell
python -m venv venv
venv\Scripts\pip install -r requirements-dev.txt
copy .env.example .env
venv\Scripts\python -m uvicorn app.main:app --port 8200
```

Сайт: http://127.0.0.1:8200

## Проверки

```powershell
venv\Scripts\ruff check app tests
venv\Scripts\ruff format app tests
venv\Scripts\python -m pytest -q
```

## Что где

| Путь | Что |
| --- | --- |
| `app/content.py` | Блюда, пакеты, обеды, контакты — до базы и админки (что настоящее, а что заглушка — в начале файла) |
| `tools/photos.py` | Кадрирование и сжатие фото в WebP: исходники в `data/photos_src`, результат в `static/img/briz` |
| `app/banquet.py` | Проверка и сохранение заявки на банкет (пока в `data/*.jsonl`) |
| `app/routers/pages.py` | Страницы |
| `templates/` | Шаблоны, `_base.html` — общий каркас с кнопкой чата |
| `static/css/site.css` | Все стили, сначала телефон |

## План

1. ~~Каркас, дизайн, страницы на заглушках~~
2. База (PostgreSQL) и админка: меню и пакеты из БД
3. Банкеты: календарь занятых дат, заявки в админке, уведомления
4. Чат в реальном времени (WebSocket) с лентой диалогов для администратора
5. Заказ обедов и онлайн-оплата
6. Бот: готовые ответы, затем ИИ по базе знаний кафе
7. Выкладка на поддомен
