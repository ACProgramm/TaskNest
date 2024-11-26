# pylint: skip-file
import pika
import json

# Настройки RabbitMQ
RABBITMQ_HOST = "localhost"
QUEUE_NAME = "notifications"

# Функция для настройки очереди уведомлений
def setup_notification_queue():
    """
    Настраивает очередь уведомлений в RabbitMQ.
    """
    try:
        # Подключение к RabbitMQ
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        channel = connection.channel()

        # Создание очереди, если она еще не создана
        channel.queue_declare(queue=QUEUE_NAME, durable=True)

        print(f"Queue '{QUEUE_NAME}' is set up successfully.")
        connection.close()
    except Exception as e:
        print(f"Failed to set up the queue: {e}")

# Функция для публикации уведомлений
def publish_notification(message: dict):
    """
    Публикует сообщение в очередь RabbitMQ.

    :param message: Словарь с данными уведомления.
    """
    try:
        # Подключение к RabbitMQ
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        channel = connection.channel()

        # Убедимся, что очередь существует
        channel.queue_declare(queue=QUEUE_NAME, durable=True)

        # Публикуем сообщение
        channel.basic_publish(
            exchange='',
            routing_key=QUEUE_NAME,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2  # Сообщение сохраняется даже при перезапуске RabbitMQ
            )
        )
        print(f" [x] Sent notification: {message}")
        connection.close()
    except Exception as e:
        print(f"Failed to publish notification: {e}")

# Функция для обработки уведомлений
def start_consumer():
    """
    Запускает консумер для обработки уведомлений из RabbitMQ.
    """
    def callback(ch, method, properties, body):
        try:
            # Декодируем сообщение
            message = json.loads(body)
            print(f" [x] Received notification: {message}")

            # Здесь можно добавить логику обработки уведомлений
            # Например: сохранить в базу данных, отправить email, логировать и т.д.

            # Подтверждаем успешную обработку
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            print(f"Failed to process notification: {e}")
            # Отправить сообщение обратно в очередь (опционально)
            ch.basic_nack(delivery_tag=method.delivery_tag)

    try:
        # Подключение к RabbitMQ
        connection = pika.BlockingConnection(pika.ConnectionParameters(host="localhost"))
        channel = connection.channel()

        # Убедимся, что очередь существует
        channel.queue_declare(queue="notifications", durable=True)

        # Подключаем консумер
        channel.basic_consume(
            queue="notifications",
            on_message_callback=callback,
            auto_ack=False
        )

        print(" [*] Waiting for notifications. To exit press CTRL+C")
        channel.start_consuming()
    except Exception as e:
        print(f"Failed to start consumer: {e}")