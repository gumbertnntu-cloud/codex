# TJR (Telegram Job Radar for macOS)

Desktop-приложение для macOS с GUI, которое подключается к Telegram под учеткой пользователя, сканирует выбранные чаты/группы и находит релевантные предложения по работе.

## Что уже есть
- Базовое GUI-приложение (`PySide6`).
- Отдельное окно `Настройки`:
- Telegram API ID/API Hash.
- Телефон Telegram.
- Список чатов/ссылок сообщений для мониторинга.
- Критерии релевантности: совпадение по названию, профилю, отрасли.
- Исключающие фразы: если найдены в сообщении, оно не попадет в выдачу.
- Минимальный порог совпадений (1-3).
- Поддержка склонений слов (например, `директор` -> `директора`, `директоры`).
- Отдельное окно найденных совпадений: канал, дата, текст, совпавшие слова, ссылка на сообщение.
- В окне результатов:
- кликабельные ссылки;
- ручное изменение ширины столбцов;
- переключаемая сортировка по дате (новые/старые);
- экспорт в Excel (`.xlsx`).
- Локальное сохранение настроек:
- macOS: `~/Library/Application Support/TJR/config.json`
- Windows: `%APPDATA%\\TJR\\config.json`
- Подробные логи:
- macOS: `~/Library/Application Support/TJR/logs/app.log`
- Windows: `%APPDATA%\\TJR\\logs\\app.log`
- При каждом новом поиске лог автоматически очищается.

## Формат ввода в настройках
- Чаты/ссылки сообщений: можно вводить через запятую, `;` или перенос строки.
- Ключевые слова/позиции: можно вводить через `/`, запятую, `;` или перенос строки.
- Исключающие фразы: можно вводить через `/`, запятую, `;` или перенос строки.

## Быстрый старт
```bash
cd /Users/steshinaleksandr/ai-sufler/TJR
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m tjr
```

## Сборка macOS .app
```bash
cd /Users/steshinaleksandr/ai-sufler/TJR
./scripts/build_mac_app.sh
```

После успешной сборки приложение будет в:
`/Users/steshinaleksandr/ai-sufler/TJR/dist/TJR.app`

## Сборка Windows .exe (onefile)
Выполняется на Windows (PowerShell):
```powershell
cd C:\path\to\TJR
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows_exe.ps1
```

Результат: `dist\TJR.exe`.

По умолчанию приложение стартует с пустым конфигом, если файла конфигурации еще нет.
Шаблон пустого конфига: `release/empty-config.json`.

См. план: `docs/PROJECT_PLAN.md`.
Ролевой протокол и сессии: `docs/ROLE_ROOM.md`.
Бэклог развития: `docs/BACKLOG.md`.
Быстрый вход в проект с нуля: `docs/START_FROM_ZERO.md`.
