#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Custom JSON HTTP Uploader for keilog
Sends data to Telegraf http_listener_v2 in JSON format
"""

import threading
import requests
import json
import queue
import time
from datetime import datetime
from keilib.worker import Worker
from logging import getLogger

logger = getLogger(__name__)


class JsonHttpUploader(Worker):
    """upload_queに入っているデータを取り出して、JSON形式でhttpサーバーにPOSTする
    
    Telegraf http_listener_v2プラグインと互換性があります。
    """

    def __init__(self, upload_que, target_url, timeout=3):
        """コンストラクタ
        
        引数：
            upload_que (Queue): データ受け取るための queue
            target_url (str): サーバーURL (例: http://192.168.1.100:8080/smartmeter)
            timeout (int): queue取得のタイムアウト秒数
        """
        super().__init__()
        self.upload_que = upload_que
        self.target_url = target_url
        self.timeout = timeout
        self.session = requests.Session()

    def _normalize_value(self, value):
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return value
        try:
            return float(value)
        except Exception:
            return str(value)

    def _normalize_timestamp(self, timestamp):
        local_tz = datetime.now().astimezone().tzinfo
        if timestamp is None:
            return datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            dt = datetime.strptime(str(timestamp), "%Y/%m/%d %H:%M:%S")
            return dt.replace(tzinfo=local_tz).isoformat(timespec="seconds")
        except Exception:
            return str(timestamp)

    def _short_text(self, text, limit=300):
        if text is None:
            return ''
        s = str(text)
        if len(s) <= limit:
            return s
        return s[:limit] + '...(truncated)'

    def _log_http_request(self, method, url, payload):
        logger.debug('[HTTP REQUEST] %s %s', method, url)
        logger.debug('[HTTP REQUEST] payload=%s', self._short_text(json.dumps(payload, ensure_ascii=False)))

    def _log_http_response(self, method, url, response):
        elapsed_sec = None
        try:
            elapsed_sec = response.elapsed.total_seconds()
        except Exception:
            elapsed_sec = None

        if elapsed_sec is None:
            logger.debug('[HTTP RESPONSE] %s %s status=%d', method, url, response.status_code)
        else:
            logger.debug('[HTTP RESPONSE] %s %s status=%d elapsed=%.3fs', method, url, response.status_code, elapsed_sec)

        logger.debug('[HTTP RESPONSE] body=%s', self._short_text(response.text))

    def run(self):
        logger.info('[JsonHttpUploader START] target: %s', self.target_url)
        try:
            logger.debug('[HTTP QUEUE] id=%s maxsize=%s', id(self.upload_que), self.upload_que.maxsize)
        except Exception:
            logger.debug('[HTTP QUEUE] id=%s', id(self.upload_que))
        last_empty_log = 0
        last_activity = time.time()
        
        while not self.stopEvent.is_set():
            # get data from upload_que（queueからデータの取得）
            try:
                data = self.upload_que.get(timeout=self.timeout)
            except queue.Empty:
                now = time.time()
                if now - last_empty_log >= 60:
                    try:
                        qsize = self.upload_que.qsize()
                    except Exception:
                        qsize = -1
                    logger.debug('[HTTP QUEUE] empty for %.0fs qsize=%s', now - last_activity, qsize)
                    last_empty_log = now
                continue
            except Exception as e:
                logger.error('Queue get error: %s', e)
                continue

            last_activity = time.time()
            logger.debug('[HTTP QUEUE] received item: %s', self._short_text(data))

            # データフォーマット変換
            # keilog record format: [unit, sensor, value, dataid] (no timestamp)
            # 例: ['BR', 'E7', 524, 'X']
            try:
                if len(data) == 4:
                    # Format: [unit, sensor, value, dataid]
                    payload = {
                        "Timestamp": self._normalize_timestamp(None),
                        "UnitID": str(data[0]),
                        "SensorID": str(data[1]),
                        "Value": self._normalize_value(data[2]),
                        "DataID": str(data[3])
                    }
                elif len(data) == 5:
                    # Format: [timestamp, unit, sensor, value, dataid]
                    payload = {
                        "Timestamp": self._normalize_timestamp(data[0]),
                        "UnitID": str(data[1]),
                        "SensorID": str(data[2]),
                        "Value": self._normalize_value(data[3]),
                        "DataID": str(data[4])
                    }
                else:
                    logger.warning('Invalid data format (expected 4 or 5 elements): %s', data)
                    continue

            except (ValueError, IndexError, TypeError) as e:
                logger.error('Data conversion error: %s, data: %s', e, data)
                continue
            except Exception as e:
                logger.error('Unexpected error during conversion: %s, data: %s', e, data)
                continue

            logger.debug('Prepared payload: %s', payload)

            # POST実行
            response = None
            try:
                self._log_http_request('POST', self.target_url, payload)
                response = self.session.post(
                    self.target_url,
                    json=payload,
                    timeout=5
                )
                self._log_http_response('POST', self.target_url, response)

                if response.status_code in [200, 204]:
                    logger.debug('POST success: SensorID=%s Value=%s', payload['SensorID'], payload['Value'])
                else:
                    logger.warning('POST failed: status=%d', response.status_code)

            except Exception as e:
                logger.exception('POST error to %s: %s', self.target_url, e)
                continue
            finally:
                if response is not None:
                    response.close()

        self.session.close()
        logger.info('[JsonHttpUploader STOP]')
