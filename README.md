<div align="center">

# 🐝 Imperal Quantum SDK (`imperal-sdk`)

### The Official Next-Gen AI Cloud OS Framework for Imperal Cloud & Webbee 🐝

**Write autonomous, context-aware AI tools and extensions in pure Python. Zero manifests. 0 lines of JSON. Automatic reactive UI. Ambient cloud context. Multi-surface morphing across Terminal, Web Panel, Telegram, and Voice.**

[![PyPI](https://img.shields.io/pypi/v/imperal-sdk?color=FFB800&label=PyPI&logo=pypi&logoColor=white)](https://pypi.org/project/imperal-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/imperal-sdk?color=blue&logo=python&logoColor=white)](https://pypi.org/project/imperal-sdk/)
[![Protocol](https://img.shields.io/badge/protocol-ICNLI%20v6.0%20Quantum-00D2FF?style=flat-square)](https://icnli.org)
[![License](https://img.shields.io/badge/license-Apache--2.0-green.svg?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-1632%20passed%20%7C%20100%25-success?style=flat-square)]()
[![DX](https://img.shields.io/badge/DX-Zero--Boilerplate%20%E2%9A%A1-orange?style=flat-square)]()

[Documentation](https://docs.imperal.io) · [ICNLI Protocol Spec](https://icnli.org) · [Imperal Cloud Panel](https://panel.imperal.io) · [Marketplace](https://panel.imperal.io/marketplace)

</div>

---

## 🌌 Квантовый скачок: Забудьте старый мир AI-агентов

В мире Web2 и раннего AI разработка инструментов для агентов превратилась в бюрократический ад:
- ❌ Ручное написание сотен строк `manifest.json` и громоздких схем JSON Schema.
- ❌ Многоэтажные абстрактные классы, жесткие интерфейсы и куча клея.
- ❌ Необходимость держать отдельную команду фронтендеров, чтобы отрисовать результаты работы инструмента в веб-панели.
- ❌ Потеря контекста между поверхностями: то, что работает в CLI, ломается в вебе и Telegram.

### ⚡ Встречайте ICNLI Quantum SDK v6.0

**Imperal Quantum SDK** делает для автономных облачных ИИ-агентов то же, что **FastAPI** сделал для веб-сервисов — переводит разработку на **квантовый мета-уровень**:

1. **Zero-Manifest (0 строк JSON)**: Манифест приложения, типы аргументов, описания для нейросетей, RBAC-скоупы и правила биллинга синтезируются автоматически из стандартных Python `type-hints` и docstrings.
2. **Auto-IR (UI-as-Data)**: Вы просто возвращаете Python-словарь или структуру — а ядро Imperal Cloud на лету проецирует её в реактивные Declarative UI карточки, таблицы и метрики без единой строчки фронтенд-кода!
3. **Ambient Context Injection**: Контекст сессии (`Context`), кошелек пользователя, защищенное хранилище (`Store`), файловая система (`Storage`) и доступ к LLM (`AI`) инжектируются невидимо для нейросетей, не засоряя промпт токенами.
4. **Liquid Multi-Surface Morphing**: Один и тот же инструмент нативно адаптируется под **Терминал (TUI)**, **Веб-панель (Declarative Cards)**, **Telegram (Inline-кнопки)** и **Голос (Voice Synthesizer)**.
5. **100% Обратная совместимость**: Полная поддержка классических корпоративных расширений на `imperal_sdk.Extension` (1630+ тестов на 100% PASS).

---

## 🚀 Быстрый старт за 60 секунд

### 1. Установка

```bash
pip install imperal-sdk
```

### 2. Ваше первое приложение за 15 строк (`server_pulse.py`)

```python
from imperal_sdk import App, Context

# Создаем квантовое приложение — манифест уже готов!
app = App("server-pulse", name="Server Pulse", category="devops")

@app.tool(pricing=5, destructive=False)
def check_host(host: str, port: int = 443, ctx: Context = None) -> dict:
    """Проверить доступность сервера и статус SSL сертификата в реальном времени."""
    # Чистая бизнес-логика:
    is_online = True
    ssl_days = 89
    
    # Возвращаем данные — ядро САМО построит интерактивный UI!
    return {
        "status": "online" if is_online else "down",
        "host": host,
        "ssl_days": ssl_days,
        "metric": f"{ssl_days} days left"
    }
```

**Что произошло автоматически под капотом?**
- ✅ Сгенерирован валидный ICNLI Manifest v6.0.
- ✅ Аргументы `host` и `port` превращены в типизированную JSON Schema.
- ✅ Docstring стал описанием для ИИ-мозга Webbee.
- ✅ Зарегистрирован RBAC-скоуп `server-pulse:check_host`.
- ✅ Аргумент `ctx: Context` скрыт от LLM, но готов к работе в рантайме.
- ✅ Результат выполнения в панели `panel.imperal.io` автоматически отобразится как стильная адаптивная **Metric Card** с бейджем и статусом!

---

## 💎 Главные квантовые суперсилы

### 1. ⚡ Автоматический синтез схем (Type-to-Schema Engine)

Больше никаких ручных JSON-схем. Пишите идиоматичный Python:

```python
from typing import List, Optional

@app.tool()
async def deploy_services(
    environment: str, 
    replicas: int = 3, 
    tags: Optional[List[str]] = None,
    dry_run: bool = False
) -> dict:
    """Развернуть микросервисы в целевом окружении с авто-масштабированием."""
    ...
```

SDK автоматически построит:
```json
{
  "name": "deploy_services",
  "description": "Развернуть микросервисы в целевом окружении с авто-масштабированием.",
  "parameters": {
    "type": "object",
    "properties": {
      "environment": {"type": "string"},
      "replicas": {"type": "integer", "default": 3},
      "tags": {"type": "array", "items": {"type": "string"}},
      "dry_run": {"type": "boolean", "default": false}
    },
    "required": ["environment"]
  }
}
```

---

### 2. 🎨 Auto-IR: UI-as-Data (Фронтенд без фронтендеров)

Ядро Imperal Cloud понимает возвращаемые типы данных и мгновенно проецирует их в Declarative UI:

| Что вы возвращаете из функции | Как это выглядит в Imperal Panel |
| :--- | :--- |
| `{"status": "ok", "metric": "99.9%", ...}` | 🎴 **Metric Card**: стильная карточка с бейджем, трендом и деталями |
| `[{"id": 1, "name": "srv-1", "cpu": 12}, ...]` | 📊 **Data Table**: адаптивная таблица с сортировкой и фильтрами |
| `{"_ui": {"type": "custom", ...}}` | 🧩 **Custom IR**: полный контроль над Declarative UI деревом |

---

### 3. 🔮 Ambient Context: Невидимый доступ ко всей Cloud OS

Параметр `ctx: Context` скрыт от нейросети (не тратит токены промпта!), но внутри функции предоставляет суперсилы всей операционной системы:

```python
@app.tool()
async def analyze_logs(service_name: str, ctx: Context = None) -> dict:
    # 1. Доступ к защищенному хранилищу ключ-значение (Redis):
    await ctx.store.set(f"last_scan:{service_name}", "in_progress")
    
    # 2. Обращение к встроенному ИИ-мозгу Webbee (LLM):
    ai_verdict = await ctx.ai.complete(f"Проанализируй аномалии сервиса {service_name}")
    
    # 3. Данные текущего пользователя и организации:
    user_email = ctx.user.email
    tenant_id = ctx.user.tenant_id
    
    return {"analysis": ai_verdict.text, "analyzed_by": user_email}
```

---

### 4. 🔀 Multi-Surface Morphing: Единая логика на всех устройствах

Webbee работает везде. SDK автоматически адаптирует презентацию:
- **Терминал (Webbee Code TUI)**: компактный вывод, псевдографика, нумерованные хоткеи.
- **Веб-консоль (Imperal Panel)**: живые графики, интерактивные формы, таблицы.
- **Telegram Bot**: мобильные карточки с callback-кнопками.
- **Voice / Ambient**: лаконичный голосовой синтез ключевых фактов.

---

### 5. 🔗 Unix-Piping между расширениями

Инструменты разных расширений можно объединять в конвейеры данных прямо в чате:
```
"Webbee, возьми домены из DNS-чекера, прогони через SSL-аудитор и отправь алерт в Telegram"
```
Благодаря типизированным контрактам входов и выходов, расширения стыкуются между собой как детали Lego.

---

## 🧪 Герметичное тестирование без интернета

В SDK встроен автономный тестовый набор (`autonomous_mock`), позволяющий прогонять тесты за миллисекунды:

```python
import pytest
from imperal_sdk.testing.autonomous_mock import MockContext
from server_pulse import check_host

def test_check_host():
    mock_ctx = MockContext(user_id="imp_u_test", role="admin")
    result = check_host(host="imperal.io", ctx=mock_ctx)
    
    assert result["status"] == "online"
    assert "_ui" in result
    assert result["_ui"]["type"] == "metric_card"
```

Запуск:
```bash
pytest -v
```

---

## 🏗️ Архитектура Imperal Cloud OS

```
                     ┌───────────────────────────────┐
                     │          Webbee Brain         │
                     │    (Agentic AI Reasoning)     │
                     └───────────────┬───────────────┘
                                     │ Intent & Tool Calls
                                     ▼
                     ┌───────────────────────────────┐
                     │    ICNLI Quantum SDK v6.0     │
                     │   imperal_sdk.App / Extension │
                     └───────────────┬───────────────┘
                                     │ Declarative IR & Telemetry
                ┌────────────────────┼────────────────────┐
                ▼                    ▼                    ▼
        ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
        │ Imperal Panel│     │  Webbee Code │     │   Telegram   │
        │   (Web UI)   │     │ (Terminal)   │     │  (Messenger) │
        └──────────────┘     └──────────────┘     └──────────────┘
```

---

## 📜 Совместимость и требования

- **Python**: 3.10, 3.11, 3.12, 3.13+
- **Зависимости**: ультра-легковесный кор, отсутствие тяжелых зависимостей в рантайме.
- **Стандарты**: 100% совместимость со спецификацией [ICNLI Protocol](https://icnli.org).
- **Лицензия**: [Apache-2.0](LICENSE).

---

<div align="center">

**Imperal Cloud — The First Autonomous ICNLI AI Cloud OS.**  
*Создано с любовью, дерзостью и 🐝 командой Imperal, Valentin Scerbacov и открытым сообществом.*

</div>
