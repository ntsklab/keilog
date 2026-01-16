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

    def run(self):
        logger.info('[JsonHttpUploader START] target: %s', self.target_url)
        
        while not self.stopEvent.is_set():
            # get data from upload_que（queueからデータの取得）
            try:
                data = self.upload_que.get(timeout=self.timeout)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error('Queue get error: %s', e)
                continue

            logger.debug('Received data from queue: %s', data)

            # データフォーマット変換
            # keilog record format: [unit, sensor, value, dataid] (no timestamp)
            # 例: ['BR', 'E7', 524, 'X']
            try:
                from datetime import datetime, timezone
                
                if len(data) == 4:
                    # Format: [unit, sensor, value, dataid]
                    # Use UTC timestamp for InfluxDB
                    payload = {
                        "Timestamp": datetime.now(timezone.utc).strftime('%Y/%m/%d %H:%M:%S'),
                        "UnitID": data[0],         # "BR"
                        "SensorID": data[1],       # "E7", "E0", etc.
                        "Value": float(data[2]),   # 数値に変換
                        "DataID": data[3]          # "X"
                    }
                elif len(data) == 5:
                    # Format: [timestamp, unit, sensor, value, dataid]
                    payload = {
                        "Timestamp": data[0],      # "2026/01/16 12:34:56"
                        "UnitID": data[1],         # "BR"
                        "SensorID": data[2],       # "E7", "E0", etc.
                        "Value": float(data[3]),   # 数値に変換
                        "DataID": data[4]          # "x"
                    }
                else:
                    logger.warning('Invalid data format (expected 4 or 5 elements): %s', data)
                    continue

            except (ValueError, IndexError) as e:
                logger.error('Data conversion error: %s, data: %s', e, data)
                continue
            except Exception as e:
                logger.error('Unexpected error during conversion: %s, data: %s', e, data)
                continue

            logger.debug('Prepared payload: %s', payload)

            # POST実行
            try:
                response = requests.post(
                    self.target_url,
                    json=payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=5
                )
                
                if response.status_code in [200, 204]:
                    logger.info('POST success: SensorID=%s Value=%s', payload['SensorID'], payload['Value'])
                else:
                    logger.warning('POST failed: status=%d, response=%s', 
                                   response.status_code, response.text)
                    
            except requests.exceptions.RequestException as e:
                logger.error('POST error to %s: %s', self.target_url, e)
                continue

        logger.info('[JsonHttpUploader STOP]')
