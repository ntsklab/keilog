#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""リモートへデータをアップロードする機能をもつクラスを定義する

ToDo:
    http POST 以外でアップロードするもの
    ツイッターへ投稿など（必要があれば）
"""
import threading
import requests
import sys
import queue
import datetime
from keilib.worker import Worker

from logging import getLogger, StreamHandler, DEBUG
logger = getLogger(__name__)

class HttpPostUploader ( Worker ):
    """upload_queに入っているデータを取り出して、httpサーバーにPOSTする
    """

    def __init__( self , upload_que, target_url, upload_key):
        """コンストラクタ
        引数：
            upload_que (Queue): データ受け取るための queue
            target_url (str): サーバーURL
            upload_key (str): アップロードキー(サーバー側で認証に使う)
        """
        super().__init__()
        self.upload_que = upload_que
        self.target_url = target_url
        self.upload_key = upload_key

    def run ( self ):
        logger.info('[START]')
        # self.upload_que.put(['test.txt', 'This is test data\n'])
        while not self.stopEvent.is_set():
            # get data from upload_que（queueからデータの取得）
            try:
                filename, data = self.upload_que.get(timeout=3)
            except:
                # logger.debug('upload que is empty')
                continue

            payload = {
                'type' : 'text',
                'key'  : self.upload_key,
                'fname': filename,
                'data' : data
            }
            logger.debug(payload)

            # POST execution（POST実行）
            try:
                response = requests.post(self.target_url, payload)
            except:
                logger.error('requests post error')
                continue

        logger.info('[STOP]')


class LokiUploader ( Worker ):
    """upload_queに入っている10分集計などのデータをLoki Push APIへ送信する

    * FileRecorderが10分平均を書き出すときに upload_que に [filename, data] 形式で追加する。
      data内の各行は `YYYY/MM/DD hh:mm:ss,unit,sensor,value[,dataid]` フォーマットを想定。
    * base_labels で共通ラベルを付与し、unit/sensorを行単位で動的に追加する。
    """

    def __init__( self, upload_que, loki_url, base_labels=None, tenant_id=None, timeout=5 ):  # noqa: E201
        super().__init__()
        self.upload_que = upload_que
        self.loki_url = loki_url.rstrip('/')
        self.base_labels = base_labels or {'app': 'keilog'}
        self.tenant_id = tenant_id
        self.timeout = timeout

    def _parse_line(self, line):
        """Parse one CSV line; return (ts_ns, labels_dict, text) or None"""
        parts = line.strip().split(',')
        if len(parts) < 4:
            return None

        ts_str = parts[0]
        try:
            dt = datetime.datetime.strptime(ts_str, '%Y/%m/%d %H:%M:%S')
            ts_ns = int(dt.timestamp() * 1_000_000_000)
        except Exception:
            return None

        unit = parts[1]
        sensor = parts[2]
        # keep original text (without trailing newline)
        text = ','.join(parts)
        labels = {**self.base_labels, 'unit': unit, 'sensor': sensor}
        return ts_ns, labels, text

    def _build_streams(self, data):
        streams = {}
        for line in data.splitlines():
            parsed = self._parse_line(line)
            if parsed is None:
                continue
            ts_ns, labels, text = parsed
            key = tuple(sorted(labels.items()))
            if key not in streams:
                streams[key] = {'stream': labels, 'values': []}
            streams[key]['values'].append([str(ts_ns), text])
        return list(streams.values())

    def run ( self ):
        logger.info('[START]')
        endpoint = self.loki_url + '/loki/api/v1/push'
        headers = {}
        if self.tenant_id:
            headers['X-Scope-OrgID'] = self.tenant_id

        while not self.stopEvent.is_set():
            try:
                filename, data = self.upload_que.get(timeout=3)
            except Exception:
                continue

            streams = self._build_streams(data)
            if not streams:
                logger.debug('no parsable lines for Loki: %s', filename)
                continue

            payload = {'streams': streams}
            try:
                resp = requests.post(endpoint, json=payload, headers=headers, timeout=self.timeout)
                if resp.status_code >= 300:
                    logger.error('Loki push failed %s: %s', resp.status_code, resp.text[:200])
            except Exception as exc:
                logger.error('Loki push exception: %s', exc)
                continue

        logger.info('[STOP]')
