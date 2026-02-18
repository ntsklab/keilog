#!/usr/bin/python3
# -*- coding: utf-8 -*-

'''Bルート経由で電力情報を取得し、ファイルに記録すると同時に、JSONフォーマットでHTTPサーバーにアップロードする設定

keiconf.py にリネームして使用

JsonHttpUploaderは、Telegraf http_listener_v2プラグインと互換性があります。
'''

import queue
from keilib.json_uploader import JsonHttpUploader
from keilib.recorder import FileRecorder
from keilib.broute   import BrouteReader, WiSunRL7023
from keilib.envconf import (
    load_dotenv,
    get_env_bool,
    get_env_int,
    get_env_json,
    get_env_str,
)


load_dotenv()


# shared queue (BrouteReader -> JsonHttpUploader)
upload_que = queue.Queue(get_env_int('RECORD_QUEUE_SIZE', 50))
fname_base = get_env_str('FNAME_BASE', 'mylogfile')

# Telegraf http_listener_v2のエンドポイント
# 例: http://192.168.1.100:8080/smartmeter
target_url = get_env_str('UPLOAD_TARGET_URL', 'http://192.168.1.100:8080/smartmeter')

# settings for BrouteReader
broute_port = get_env_str('BROUTE_PORT', '/dev/serial/by-id/usb-FTDI_FT230X_Basic_UART_xxxxxxxx-if00-port0')
broute_baudrate = get_env_int('BROUTE_BAUDRATE', 115200)
wisun_type_name = get_env_str('WISUN_TYPE', 'IPS').upper()
wisun_type = WiSunRL7023.IPS if wisun_type_name == 'IPS' else WiSunRL7023.DSS

wisundev = WiSunRL7023 (
                port=broute_port,
                baud=broute_baudrate,
                type=wisun_type
            )

broute_id = get_env_str('BROUTE_ID', 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx')
broute_pwd = get_env_str('BROUTE_PASSWORD', 'xxxxxxxxxxxx')
default_requests = [
    { 'epc':['D3','D7','E1'], 'cycle': 3600 },  # 係数(D3),有効桁数(D7),単位(E1),3600秒ごと
    { 'epc':['E7'], 'cycle': 10 },              # 瞬時電力(E7),10秒ごと
    { 'epc':['E0'], 'cycle': 300 },             # 積算電力量(E0),300秒ごと
    { 'epc':['8D'], 'cycle': 86400 },           # 製造番号(8D),86400秒ごと
]
requests = get_env_json('BROUTE_REQUESTS', default_requests)
broute_record_raw_epc = get_env_bool('BROUTE_RECORD_RAW_EPC', True)
# definition fo worker objects

worker_def = [
    {
        'class': JsonHttpUploader,
        'args': {
            'upload_que': upload_que,
            'target_url': target_url
        }
    },

    {
        'class': BrouteReader,
        'args': {
            'wisundev': wisundev,
            'broute_id': broute_id,
            'broute_pwd': broute_pwd,
            'requests': requests,
            'record_que': upload_que,
            'record_raw_epc': broute_record_raw_epc,
        }
    }
]
