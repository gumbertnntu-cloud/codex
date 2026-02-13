# TJR: Быстрый старт с нуля

Этот файл нужен, чтобы продолжать проект без потери контекста.

## 1) Что это за проект
- `TJR` — macOS GUI-приложение для поиска релевантных вакансий в Telegram-чатах под аккаунтом пользователя.
- Текущая дата фиксации этого документа: `2026-02-13`.

## 2) Где запускать
- Корень проекта: `/Users/steshinaleksandr/ai-sufler/TJR`
- Основной запуск (dev):
```bash
cd /Users/steshinaleksandr/ai-sufler/TJR
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m tjr
```
- Сборка `.app`:
```bash
cd /Users/steshinaleksandr/ai-sufler/TJR
./scripts/build_mac_app.sh
```
- Готовое приложение:
`/Users/steshinaleksandr/ai-sufler/TJR/dist/TJR.app`

## 3) Где данные пользователя
- Конфиг: `~/Library/Application Support/TJR/config.json`
- Логи: `~/Library/Application Support/TJR/logs/app.log`
- Telegram session: `~/Library/Application Support/TJR/sessions/user_session`

## 4) Что уже реализовано
- Настройки Telegram (`API ID`, `API Hash`, `phone`) с сохранением.
- Скан Telegram-источников (только каналы/чаты, где пользователь состоит).
- Поиск по 3 блокам: `название`, `профиль`, `отрасль`.
- Исключающие фразы (anti-noise).
- Учет склонений (лемматизация).
- Бан сообщений по ссылке (чекбокс в отчете, в обе стороны: бан/разбан).
- Живой прогресс сканирования + ETA.
- Крупный счетчик найденных вакансий в центре главного окна (обновляется в процессе).
- Отчет с сортировкой по дате, кликабельными ссылками, изменяемой шириной столбцов, экспортом в `.xlsx`.
- Сброс лога при каждом новом запуске проверки.
- Кнопка открытия последнего отчета без повторного скана.

## 5) Текущий порядок столбцов в отчете
- `Бан` (служебный),
- `Дата`,
- `Сообщение`,
- `Ссылка`,
- `Канал`,
- `Совпавшие слова`.

`Score` из отчета и экспорта убран.

## 6) Ключевые файлы кода
- UI:
  - `src/tjr/ui/main_window.py`
  - `src/tjr/ui/results_window.py`
  - `src/tjr/ui/settings_dialog.py`
  - `src/tjr/ui/smooth_scroll.py`
- Core:
  - `src/tjr/core/scanner.py`
  - `src/tjr/core/matching.py`
  - `src/tjr/core/input_parser.py`
- Storage:
  - `src/tjr/storage/config_store.py`
- Тесты:
  - `tests/test_ui_smoke.py`
  - `tests/test_scanner.py`
  - `tests/test_matching.py`
  - `tests/test_input_parser.py`

## 7) Как проверить, что всё живо
```bash
cd /Users/steshinaleksandr/ai-sufler/TJR
python3 -m compileall src tests
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
```

## 8) Что читать дальше
- Общий обзор: `README.md`
- Детальный план: `docs/PROJECT_PLAN.md`
- Ролевые сессии и решения: `docs/ROLE_ROOM.md`
- Продуктовый бэклог: `docs/BACKLOG.md`

