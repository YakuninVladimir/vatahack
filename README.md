Пайплайн обработки чата:

1. Все ГС расшифровываются при помощи speech-to-text модели
2. К картинкам применяется метод для векторизации и извлечения текста. 
3. мультимодальная модель выделяет основные темы в текущем чате (чанками, соответствующими эффективной длине контекста)
4. производится мэтчинг тем.
5. сообщения классифициируются по темам
6. подгружаются темы из истории чата
7. происходит саммаризация по каждой из тем и составление вывода:
- для старых тем описываем, что нового добавилось 
- для новых описываем саммари всего 
8. формируем готовых отчёт

## Переменные окружения

Бот:
- TG_BOT_TOKEN (обязательно)
- DB_DSN (обязательно)
- REDIS_URL (опционально, для чекпоинтов)
- AGENT_URL (по умолчанию http://stub-service:8001)
- SUMMARY_MAX_MESSAGES (по умолчанию 1000)
- SUMMARY_MIN_TOPIC_SIZE (по умолчанию 10)
- SUMMARY_INCLUDE_NOISE (по умолчанию true)
- SUMMARY_OLLAMA_MODEL (по умолчанию qwen2.5:1.5b-instruct)
- SUMMARY_CONTEXT_WINDOW_TOKENS (по умолчанию 4096)
- LOG_LEVEL (по умолчанию INFO)

Агент:
- OLLAMA_BASE_URL (по умолчанию http://localhost:11434)
- LOG_LEVEL (по умолчанию INFO)

## Kubernetes запуск (отдельные сервисы)

1) Соберите образы:
```
docker build -t vatahack/stub-service:latest -f Dockerfile.stub .
docker build -t vatahack/client:latest -f Dockerfile.client .
```

2) Примените манифесты:
```
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/ollama.yaml
kubectl apply -f k8s/stub-service.yaml
kubectl apply -f k8s/client-job.yaml
```

3) Укажите TG_BOT_TOKEN в `k8s/client-job.yaml` (или задайте через `kubectl set env`).

4) Проверьте логи бота:
```
kubectl logs deployment/bot
```

## Остановить/удалить Kubernetes ресурсы

```
kubectl delete -f k8s/client-job.yaml
kubectl delete -f k8s/stub-service.yaml
kubectl delete -f k8s/ollama.yaml
kubectl delete -f k8s/redis.yaml
kubectl delete -f k8s/postgres.yaml
```

Если нужно полностью убрать данные Postgres:
```
kubectl delete pvc postgres-data
```
