# Worker API v1

Интерфейс страницы вызывает `runPython(tool, payload, buffer?, onStatus?)`. Bridge присваивает уникальный request ID и отправляет в единственный Worker текущей страницы:

```javascript
{
  version: 1,
  id: 42,
  tool: 'url-cleaner',
  payload: { text: 'https://example.com/?utm_source=test&id=42', remove_ref: false },
  buffer: undefined
}
```

`buffer` — необязательный transferable ArrayBuffer; он передаётся отдельным полем, а не сериализуется в JSON. Поля `payload` содержат строки, числа или boolean из формы. Worker передаёт данные в Python `execute_tool(tool, payload, data)`. Выбор Python-функции централизован в `python/dispatch.py`.

## Ответы

```javascript
// Промежуточное состояние; Promise остаётся открытым.
{ id: 42, status: 'Processing locally…' }

// Успех.
{
  id: 42, version: 1, success: true,
  result: { text: 'https://example.com/?id=42', removed: ['utm_source'] },
  metadata: {}
}

// Ошибка ввода.
{
  id: 42, version: 1, success: false,
  error: { code: 'INVALID_INPUT', message: 'Enter a complete HTTP or HTTPS URL.' }
}
```

`INVALID_JSON` обозначает ошибки JSON-инструментов, `INVALID_INPUT` — остальные ошибки валидации, `ENGINE_ERROR` — ошибки runtime/Worker. Bridge отклоняет Promise с `Error`, сохраняющим `code`. Не следует помещать секретный ввод в сообщения об ошибках или логи.

Поля `result` зависят от типа результата:

| Поле | Назначение |
| --- | --- |
| `text` | Текстовый результат для readonly textarea и Copy |
| `details` | Список пояснений/статистики, выводимых через textContent |
| `extension` | Расширение скачиваемого результата |
| `sensitive` | Отключает стандартное скачивание секретов; история отсутствует для всех инструментов |
| `items` | Отдельные UUID для Copy one |
| `removed` | Удалённые URL-параметры |
| `base64`, `mime`, `size` | Бинарный результат Python, из которого интерфейс создаёт Blob |
| `width`, `height`, `original_size`, `metadata` | Размеры и исходные метаданные изображения |
| `iso` | UTC instant для дополнительного локального отображения браузером |

Внешнее `metadata` зарезервировано для протокольных дополнений. Изображения сохраняют исходные EXIF-сведения в `result.metadata`, отдельно от протокольного контейнера.

## Идентификаторы

`hash`, `hash-start`, `hash-chunk`, `hash-finish`, `url-cleaner`, `json`, `json-validator`, `base64`, `image-inspect`, `image-metadata`, `image-compressor`, `image-resizer`, `image-converter`, `password-generator`, `uuid-generator`, `random-token`, `csv-json`, `text-cleaner`, `remove-duplicate-lines`, `text-diff`, `timestamp`, `url-encoder`, `jwt-decoder`.

Страница `qr-generator` использует отдельный локальный JS-модуль и bundled Nayuki, без Worker/Pyodide. Она возвращает Blob для PNG/SVG и использует общие состояния результата/ошибки интерфейса.

## Потоковый hash

1. `hash-start`, payload `{ algorithm }` создаёт состояние hashlib.
2. Страница читает файл по 4 MiB и отправляет `hash-chunk` с buffer. Следующий чанк читается только после ответа, исключая неограниченную очередь в памяти.
3. Прогресс вычисляется по подтверждённым байтам на стороне интерфейса.
4. `hash-finish` возвращает digest и удаляет состояние.

Пустой файл проходит start → finish. На Worker допускается один поток хеша; UI блокирует второй запуск. Отмена завершает весь Worker, поэтому незавершённое состояние не переиспользуется. Следующая операция запускает новый runtime. Ограничение 64 MiB относится к целиком передаваемым файлам других инструментов, а не к streamed hash.

## Жизненный цикл

Worker создаётся лениво. Очередь сериализует операции. Pillow загружается только для `image-*`. На каждый запрос установлен тайм-аут 180 секунд; у потокового хеша это тайм-аут отдельного чанка, не всего файла. Cancel и Clear завершают Worker и отклоняют незавершённые запросы. Поля Python globals с входными байтами очищаются в finally. Blob URL освобождаются при новом вводе, Clear или уходе со страницы.

Протокол не исполняет пользовательский код и не принимает имя произвольной Python-функции. HTML/JS отвечают за интерфейс и передачу данных, Python — за преобразования; C++-backend пока отсутствует.
