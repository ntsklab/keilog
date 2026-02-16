#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""ECHONET Lite EPC definitions for low-voltage smart electric energy meter.

主に下記に基づく定義:
* ECHONET機器オブジェクト詳細規定（低圧スマート電力量メータクラス）
* ECHONET Super Class
"""

EPC_DEFINITIONS = {
    # Super class properties
    '80': {'name': '動作状態', 'class': 'super'},
    '81': {'name': '設置場所', 'class': 'super'},
    '82': {'name': '規格Version情報', 'class': 'super'},
    '83': {'name': '識別番号', 'class': 'super'},
    '84': {'name': '瞬時消費電力計測値', 'class': 'super'},
    '85': {'name': '積算消費電力計測値', 'class': 'super'},
    '86': {'name': 'メーカ異常コード', 'class': 'super'},
    '87': {'name': '電流制限設定', 'class': 'super'},
    '88': {'name': '異常発生状態', 'class': 'super'},
    '89': {'name': '異常内容', 'class': 'super'},
    '8A': {'name': 'メーカコード', 'class': 'super'},
    '8B': {'name': '事業場コード', 'class': 'super'},
    '8C': {'name': '商品コード', 'class': 'super'},
    '8D': {'name': '製造番号', 'class': 'super'},
    '8E': {'name': '製造年月日', 'class': 'super'},
    '8F': {'name': '節電動作設定', 'class': 'super'},
    '93': {'name': '遠隔操作設定', 'class': 'super'},
    '97': {'name': '現在時刻設定', 'class': 'super'},
    '98': {'name': '現在年月日設定', 'class': 'super'},
    '99': {'name': '電力制限設定', 'class': 'super'},
    '9A': {'name': '積算運転時間', 'class': 'super'},
    '9B': {'name': 'SetMプロパティマップ', 'class': 'super'},
    '9C': {'name': 'GetMプロパティマップ', 'class': 'super'},
    '9D': {'name': '状変アナウンスプロパティマップ', 'class': 'super'},
    '9E': {'name': 'Setプロパティマップ', 'class': 'super'},
    '9F': {'name': 'Getプロパティマップ', 'class': 'super'},

    # Low-voltage smart electric energy meter class properties
    'D3': {'name': '係数', 'class': 'smart_meter'},
    'D7': {'name': '積算電力量有効桁数', 'class': 'smart_meter'},
    'E0': {'name': '積算電力量計測値(正方向計測値)', 'class': 'smart_meter'},
    'E1': {'name': '積算電力量単位', 'class': 'smart_meter'},
    'E2': {'name': '積算電力量計測値履歴1(正方向計測値)', 'class': 'smart_meter'},
    'E3': {'name': '積算電力量計測値(逆方向計測値)', 'class': 'smart_meter'},
    'E4': {'name': '積算電力量計測値履歴1(逆方向計測値)', 'class': 'smart_meter'},
    'E5': {'name': '積算履歴収集日1', 'class': 'smart_meter'},
    'E7': {'name': '瞬時電力計測値', 'class': 'smart_meter'},
    'E8': {'name': '瞬時電流計測値', 'class': 'smart_meter'},
    'EA': {'name': '定時積算電力量計測値(正方向計測値)', 'class': 'smart_meter'},
    'EB': {'name': '定時積算電力量計測値(逆方向計測値)', 'class': 'smart_meter'},
    'EC': {'name': '積算電力量計測履歴2(正方向、逆方向計測値)', 'class': 'smart_meter'},
    'ED': {'name': '積算履歴収集日2', 'class': 'smart_meter'},
}
