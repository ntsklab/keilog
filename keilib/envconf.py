#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
from pathlib import Path


def load_dotenv(dotenv_path=None):
    """Load .env file values into os.environ if not already defined."""
    if dotenv_path is None:
        dotenv_path = Path(__file__).resolve().parent.parent / '.env'
    else:
        dotenv_path = Path(dotenv_path)

    if not dotenv_path.exists():
        return False

    with dotenv_path.open('r', encoding='utf-8') as fp:
        for raw_line in fp:
            line = raw_line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue

            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()

            if not key:
                continue

            if value and ((value[0] == '"' and value[-1] == '"') or (value[0] == "'" and value[-1] == "'")):
                value = value[1:-1]

            if key not in os.environ:
                os.environ[key] = value

    return True


def get_env_str(name, default=None, required=False):
    value = os.getenv(name, default)
    if required and (value is None or value == ''):
        raise ValueError(f'{name} is required but not set')
    return value


def get_env_int(name, default=0):
    value = os.getenv(name)
    if value is None or value == '':
        return default
    return int(value)


def get_env_bool(name, default=False):
    value = os.getenv(name)
    if value is None or value == '':
        return default
    return value.lower() in ('1', 'true', 'yes', 'on')


def get_env_json(name, default=None):
    value = os.getenv(name)
    if value is None or value == '':
        return default
    return json.loads(value)
