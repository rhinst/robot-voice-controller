import os
from itertools import cycle
from time import sleep, time
from typing import Dict, Any, Union
from json import dumps, loads
import re
from random import choice
from uuid import uuid1

from redis import Redis
from redis.client import PubSub

from app.config import load_config
from app.logging import logger, initialize_logger
from app.handler import handlers


class ListeningTimeoutException(Exception):
    pass


def turn_on_led(redis_client: Redis, name: str):
    redis_client.publish("subsystem.led.command", dumps({"command": "turn_on", "name": name}))


def turn_off_led(redis_client: Redis, name: str):
    redis_client.publish("subsystem.led.command", dumps({"command": "turn_off", "name": name}))


def answer_affirmative(redis_client: Redis):
    phrases = [
        "okay",
        "you got it",
        "sure thing",
        "sure",
    ]
    say(redis_client, choice(phrases))


def prompt(redis_client: Redis):
    phrases = [
        "what's up?",
        "what can i do for you?",
        "what is it?",
        "what now?",
        "what do you need?",
    ]
    say(redis_client, choice(phrases))


def say(redis_client: Redis, phrase: str):
    logger.debug(f"Saying '{phrase}'")
    redis_client.publish("subsystem.speech.command", phrase)


def handle_command(command: str):
    logger.debug(f"TODO: handle command: '{command}'")


def get_phrase(redis_client: Redis, pubsub: PubSub, timeout: int = 0) -> str:
    start = time()
    request_id = str(uuid1())
    redis_client.publish("subsystem.listener.command", dumps({"mode": "phrase", "request_id": request_id}))
    logger.debug(f"Listening for phrase (request_id={request_id})")
    while cycle([True]):
        waited_so_far = time() - start
        if timeout and waited_so_far > timeout:
            raise ListeningTimeoutException(f"Timed out waiting for phrase after {waited_so_far} seconds")
        if redis_message := pubsub.get_message():
            message = loads(redis_message['data'])
            if message['request_id'] != request_id:
                logger.debug(f"ignoring request id #{message['request_id']}")
                continue
            logger.debug(f"Received a response to request_id #{message['request_id']}")
            logger.debug(f"Received phrase was {message['transcription']}")
            return message['transcription']
        sleep(0.01)


def wait_for_wake_word(redis_client: Redis, pubsub: PubSub, wake_word: str) -> str:
    logger.debug(f"Listening for wake word '{wake_word}'")
    phrase = get_phrase(redis_client, pubsub)
    while not(m := re.match(rf"{wake_word}\b(.*)", phrase, re.I)):
        phrase = get_phrase(redis_client, pubsub)
    return m.group(1)


def handle_on_wake(redis_client: Redis, pubsub: PubSub, wake_word: str):
    while cycle([True]):
        command_string = wait_for_wake_word(redis_client, pubsub, wake_word)
        if not command_string:
            logger.debug("No command received with wake word")
            turn_on_led(redis_client, "red")
            prompt(redis_client)
            try:
                logger.debug("Listening for a command")
                command_string = get_phrase(redis_client, pubsub, 10)
                logger.debug(f"got command string: '{command_string}'")
            except ListeningTimeoutException:
                say(redis_client, "you took too long.")
            finally:
                turn_off_led(redis_client, "red")
        if not command_string:
            logger.debug("No command received before timeout")
            continue
        answer_affirmative(redis_client)
        handle_command(command_string)
        sleep(0.01)


def main():
    environment: str = os.getenv("ENVIRONMENT", "dev")
    config: Dict = load_config(environment)
    initialize_logger(level=config['logging']['level'], filename=config['logging']['filename'])
    redis_host = config['redis']['host']
    redis_port = config['redis']['port']
    logger.debug(f"Connecting to redis at {redis_host}:{redis_port}")
    redis_client: Redis = Redis(
        host=redis_host, port=redis_port, db=0
    )
    pubsub: PubSub = redis_client.pubsub(ignore_subscribe_messages=True)

    try:
        pubsub.subscribe("subsystem.listener.recording", ignore_subscribe_messages=True)
        handle_on_wake(redis_client, pubsub, config['wake_word'])
    except Exception as e:
        logger.exception(f"Something bad happened: {str(e)}")
    finally:
        logger.debug("Cleaning up")
        pubsub.close()
        redis_client.close()
        logger.debug("Shutting down")


if __name__ == '__main__':
    main()