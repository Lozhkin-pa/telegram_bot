from dotenv import load_dotenv
import logging
import os
import time
import sys
import requests
from exceptions import HTTPStatusException, MyTelegramException
from http import HTTPStatus
import telegram

load_dotenv()

logger = logging.getLogger(__name__)
handlers = [logging.StreamHandler(sys.stdout)]

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет доступность переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        logger.debug('Начало отправки сообщения в Telegram')
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except Exception as error:
        logger.error(
            f'Сбой при отправке сообщения "{message}" в Telegram: {error}'
        )
        raise MyTelegramException(error)
    else:
        logger.debug(f'Сообщение "{message}" успешно отправлено в Telegram')


def get_api_answer(timestamp):
    """Делает запрос к эндпоинту Практикум.Домашка."""
    request_params = {
        'headers': HEADERS,
        'url': ENDPOINT,
        'params': {
            'from_date': timestamp
        },
    }
    try:
        logger.debug('Начало отправки запроса к эндпоинту')
        response = requests.get(**request_params)
    except Exception as error:
        logger.error(f'Сбой при запросе к эндпоинту: {error}')
    if response.status_code != HTTPStatus.OK:
        raise HTTPStatusException(
            f'Получен код ответа HTTP-статуса: {response.status_code}. '
            f'Заголовки ответа: {response.headers} '
            f'Содержание ответа: {response.text}'
        )
    return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError('В ответе API получен не словарь!')
    homework = response.get('homeworks')
    current_date = response.get('current_date')
    if homework is None:
        raise KeyError('В ответе API отсутствует ключ "homeworks"!')
    if current_date is None:
        raise KeyError('В ответе API отсутствует ключ "current_date"!')
    if not isinstance(homework, list):
        raise TypeError(
            'В ответе API под ключом "homework" получен не список!'
        )
    return homework


def parse_status(homework):
    """Извлекает из информации о конкретной домашней работе её статус."""
    if len(homework) == 0:
        raise ValueError('Новый статус не появился. Список работ пуст')
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if homework_name is None:
        raise KeyError('Ключ homework_name не найден')
    if homework_status is None:
        raise KeyError('Ключ homework_status не найден')
    if homework_status not in HOMEWORK_VERDICTS:
        raise ValueError(
            f'В ответе API обнаружен неожиданный статус домашней работы:'
            f'{homework_status}'
        )
    else:
        verdict = HOMEWORK_VERDICTS[homework_status]
    return (f'Изменился статус проверки работы "{homework_name}". {verdict}')


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical('Отсутствие обязательных переменных окружения!')
        sys.exit()

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    logger.info('Бот запущен!')
    timestamp = int(time.time())

    current_report = {}
    prev_report = {}

    while True:
        try:
            response = get_api_answer(timestamp)
            timestamp = response.get('current_date', timestamp)
            homework = check_response(response)[0]
            if homework:
                message = parse_status(homework)
                current_report[
                    homework.get('homework_name')
                ] = homework.get('status')
                if current_report != prev_report:
                    logger.info(message)
                    send_message(bot, message)
                    prev_report = current_report.copy()
                    current_report[
                        homework.get('homework_name')
                    ] = homework.get('status')
                else:
                    logger.debug('В ответе отсутствует новый статус')
        except Exception as error:
            logger.critical(f'Сбой в работе программы: {error}!')
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format=('%(asctime)s - %(name)s - %(funcName)s - %(lineno)d'
                '- [%(levelname)s] - %(message)s'),
        handlers=handlers
    )
    main()
