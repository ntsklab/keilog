#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
スマートメーターから取得可能な全EPCを取得するスクリプト

まず0x9F (Getプロパティマップ)を取得して、取得可能なEPC一覧を得る。
その後、一覧に含まれる全てのEPCを取得する。
"""

import sys
import os
import time
import logging
import argparse
import json
from logging import getLogger, StreamHandler, DEBUG, INFO
from pathlib import Path

# .envファイルを読み込む
try:
    from dotenv import load_dotenv
    # スクリプトと同じディレクトリの.envファイルを読み込む
    env_path = Path(__file__).parent / '.env'
    load_dotenv(dotenv_path=env_path)
except ImportError:
    print('警告: python-dotenvがインストールされていません。')
    print('インストールするには: pip install python-dotenv')
    print('環境変数から直接読み込みます。')

# keilib をインポート
from keilib.broute import WiSunRL7023, BrouteReader, DataFrame
from keilib.echonet_epc import EPC_DEFINITIONS

# セキュアモードのグローバルフラグ
SECURE_MODE = False

# ログ設定
logger = getLogger(__name__)
handler = StreamHandler()
handler.setLevel(DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.setLevel(DEBUG)
logger.addHandler(handler)

# broute.pyのロガー設定（セキュアモードの場合はINFOレベルに）
broute_logger = logging.getLogger('keilib.broute')
broute_logger.setLevel(DEBUG)
broute_logger.addHandler(handler)


def mask_string(value, show_chars=4, mask_char='*'):
    """文字列を部分的にマスクする
    
    Args:
        value (str): マスクする文字列
        show_chars (int): 表示する文字数
        mask_char (str): マスク文字
    
    Returns:
        str: マスクされた文字列
    """
    if not value or len(value) <= show_chars:
        return mask_char * len(value) if value else ''
    return value[:show_chars] + mask_char * min(8, len(value) - show_chars)


def mask_ipv6(ipv6_addr):
    """IPv6アドレスを部分的にマスクする
    
    Args:
        ipv6_addr (str): IPv6アドレス
    
    Returns:
        str: マスクされたIPv6アドレス
    """
    if not ipv6_addr or ':' not in ipv6_addr:
        return ipv6_addr
    parts = ipv6_addr.split(':')
    if len(parts) >= 4:
        # 最初の2セグメントと最後の2セグメントだけ表示
        return f"{parts[0]}:{parts[1]}:****:****:****:****:{parts[-2]}:{parts[-1]}"
    return ipv6_addr


def mask_sensitive_value(epc, value):
    """EPCの種類に応じて機密情報をマスクする
    
    Args:
        epc (str): EPCコード
        value (str): 値
    
    Returns:
        str: マスクされた値（セキュアモードでない場合は元の値）
    """
    if not SECURE_MODE:
        return value
    
    # 製造番号、識別番号などをマスク
    if epc in ['8D', '83']:  # 製造番号、識別番号
        if len(value) > 8:
            return value[:4] + '****' + value[-4:]
        else:
            return mask_string(value, 2)
    
    return value


def decode_property_map(rawdata):
    """プロパティマップをデコードしてEPCリストを返す
    
    Args:
        rawdata (str): 16進文字列のプロパティマップデータ
    
    Returns:
        list: EPCコードのリスト (例: ['80', '81', 'E7'])
    """
    logger.debug(f'decode_property_map: rawdata={rawdata}, length={len(rawdata)}')
    
    if len(rawdata) < 2:
        logger.warning('プロパティマップが短すぎます')
        return []
    
    count = int(rawdata[:2], 16)
    logger.debug(f'プロパティ数: {count}')
    
    # プロパティ数が16未満の場合（列挙形式）
    if count < 16:
        epc_list = []
        for i in range(count):
            base = 2 + i * 2
            if base + 2 <= len(rawdata):
                epc_list.append(rawdata[base:base + 2].upper())
        logger.debug(f'列挙形式で解析: {epc_list}')
        return epc_list
    
    # プロパティ数が16以上の場合（ビットマップ形式）
    if len(rawdata) < 2 + 32:
        logger.warning(f'ビットマップ形式ですがデータが短すぎます: {len(rawdata)}')
        return []
    
    epc_list = []
    bitmap_hex = rawdata[2:2+32]
    logger.debug(f'ビットマップ: {bitmap_hex}')
    
    # プロパティマップのビット配置（ECHONET Lite 仕様）：
    # バイトは縦方向（+0x01）、ビットは横方向（+0x10）に並ぶ
    # 例: 2バイト目 = [0x80, 0x90, 0xA0, 0xB0, 0xC0, 0xD0, 0xE0, 0xF0]（ビット0-7）
    #     3バイト目 = [0x81, 0x91, 0xA1, 0xB1, 0xC1, 0xD1, 0xE1, 0xF1]（ビット0-7）
    for byte_idx in range(16):
        byte_hex = rawdata[2 + byte_idx * 2: 2 + byte_idx * 2 + 2]
        byte_val = int(byte_hex, 16)
        if byte_val > 0:
            found_epcs = []
            for bit in range(8):
                if byte_val & (1 << bit):
                    # 正しい計算式: EPC = 0x80 + ビット位置*16 + バイトインデックス
                    epc = 0x80 + bit * 16 + byte_idx
                    epc_str = '{:02X}'.format(epc)
                    epc_list.append(epc_str)
                    found_epcs.append(epc_str)
            logger.debug(f'  バイト{byte_idx} (0x{byte_hex}={byte_val:08b}): {", ".join(found_epcs)}')
    logger.debug(f'ビットマップ形式で解析完了: 合計{len(epc_list)}個のEPC')
    return epc_list


def _parse_epc_csv(value):
    """カンマ区切りEPC文字列を正規化してリスト化する。"""
    if not value:
        return []
    epcs = []
    for token in value.split(','):
        epc = token.strip().upper().replace('0X', '')
        if len(epc) == 2 and all(ch in '0123456789ABCDEF' for ch in epc):
            epcs.append(epc)
        elif epc:
            logger.warning(f'無効なEPC指定を無視します: {token}')
    return epcs


def _apply_epc_filters(epc_list):
    """.envの設定でEPCリストを絞り込み/追加/除外する。"""
    only_epcs = _parse_epc_csv(os.getenv('GET_ALL_EPC_ONLY', ''))
    include_epcs = _parse_epc_csv(os.getenv('GET_ALL_EPC_INCLUDE', ''))
    exclude_epcs = set(_parse_epc_csv(os.getenv('GET_ALL_EPC_EXCLUDE', '')))

    selected = list(epc_list)

    if only_epcs:
        selected = [epc for epc in only_epcs]
        logger.info(f'.env適用: GET_ALL_EPC_ONLY = {", ".join(only_epcs)}')

    if include_epcs:
        added = []
        for epc in include_epcs:
            if epc not in selected:
                selected.append(epc)
                added.append(epc)
        if added:
            logger.info(f'.env適用: GET_ALL_EPC_INCLUDE で追加 = {", ".join(added)}')

    if exclude_epcs:
        before = len(selected)
        selected = [epc for epc in selected if epc not in exclude_epcs]
        removed = before - len(selected)
        if removed > 0:
            logger.info(f'.env適用: GET_ALL_EPC_EXCLUDE で除外 = {", ".join(sorted(exclude_epcs))}')

    return selected


def _build_broute_requests(valid_results):
    """取得結果からBROUTE_REQUESTS候補を生成する。"""
    available = set(valid_results.keys())
    requests = []

    # 日次（交換しないと変わりにくいメータ固有情報）
    daily_group = [epc for epc in ['81', '82', '8A', '8D', 'C0', 'D3', 'D7', 'E1'] if epc in available]
    if daily_group:
        requests.append({'epc': daily_group, 'cycle': 86400})

    # 低頻度（状態・時刻など）
    low_group = [epc for epc in ['88', '97', '98', 'E5'] if epc in available]
    if low_group:
        requests.append({'epc': low_group, 'cycle': 3600})

    # 高頻度（瞬時値）
    high_group = [epc for epc in ['E7', 'E8'] if epc in available]
    if high_group:
        requests.append({'epc': high_group, 'cycle': 10})

    # 中頻度（積算値）
    mid_group = [epc for epc in ['E0', 'E3'] if epc in available]
    if mid_group:
        requests.append({'epc': mid_group, 'cycle': 300})

    # 任意履歴系（必要な場合のみ）
    hist_group = [epc for epc in ['EA', 'EB', 'EC', 'ED', 'E2', 'E4', 'E5'] if epc in available]
    if hist_group:
        requests.append({'epc': hist_group, 'cycle': 1800})

    return requests


def get_all_epc_values(wisundev, broute_id, broute_pwd, force_important_epcs=False):
    """スマートメーターから全EPCを取得
    
    Args:
        wisundev: WiSUNデバイスインスタンス
        broute_id (str): BルートID
        broute_pwd (str): Bルートパスワード
        force_important_epcs (bool): 重要なEPCを強制的に追加するか
    
    Returns:
        dict: EPCコードをキーとした値の辞書
    """
    
    results = {}
    
    # Step 1: デバイスオープン
    logger.info('=== Step 1: デバイスオープン ===')
    if not wisundev.open():
        logger.error('デバイスのオープンに失敗しました')
        return results
    logger.info('デバイスオープン成功')
    
    # Step 2: デバイスのリセットとセットアップ
    logger.info('=== Step 2: デバイスのリセットとセットアップ ===')
    if not wisundev.reset():
        logger.error('デバイスのリセットに失敗しました')
        wisundev.close()
        return results
    logger.info('デバイスリセット成功')
    
    if not wisundev.setup(broute_id, broute_pwd):
        logger.error('デバイスのセットアップに失敗しました')
        wisundev.close()
        return results
    logger.info('デバイスセットアップ成功')
    
    # Step 3: アクティブスキャン
    logger.info('=== Step 3: アクティブスキャン ===')
    if not wisundev.scan():
        logger.error('スキャンに失敗しました')
        wisundev.close()
        return results
    logger.info('スキャン成功')
    
    # Step 4: PANA認証
    logger.info('=== Step 4: PANA認証 ===')
    if not wisundev.join():
        logger.error('PANA認証に失敗しました')
        wisundev.close()
        return results
    logger.info('PANA認証成功')
    
    # Step 5: Getプロパティマップ (0x9F) を取得
    logger.info('=== Step 5: Getプロパティマップ (0x9F) を取得 ===')
    cmd = DataFrame.cmd_get_property(['9F'])
    if not wisundev.sendto(cmd):
        logger.error('0x9F送信に失敗しました')
        wisundev.term()
        wisundev.close()
        return results
    
    # 応答待機
    logger.info('0x9F応答待機中...')
    max_wait = 30  # 最大30秒待機
    wait_count = 0
    property_map_data = None
    
    while wait_count < max_wait:
        dataframe = wisundev.receive()
        if dataframe and '9F' in dataframe.properties:
            property_map_data = dataframe.properties['9F']
            logger.info('Getプロパティマップ取得成功: ' + property_map_data)
            break
        time.sleep(1)
        wait_count += 1
    
    if property_map_data is None:
        logger.error('Getプロパティマップの取得に失敗しました')
        wisundev.term()
        wisundev.close()
        return results
    
    # Step 6: プロパティマップをデコード
    logger.info('=== Step 6: プロパティマップをデコード ===')
    epc_list_raw = decode_property_map(property_map_data)
    
    # プロパティマップ系EPCは取得できないので除外
    # 9B, 9C: SetM/GetMプロパティマップ（ECHONET Lite機器は非搭載）
    # 9D, 9E, 9F: 状変アナウンス/Set/Getプロパティマップ（取得リクエスト不可）
    exclude_epcs = {'9B', '9C', '9D', '9E', '9F'}
    epc_list = [epc for epc in epc_list_raw if epc not in exclude_epcs]
    
    logger.info(f'取得可能なEPC数: {len(epc_list_raw)} (除外後: {len(epc_list)})')
    logger.info(f'EPC一覧: {", ".join(epc_list)}')
    if epc_list_raw != epc_list:
        excluded = [epc for epc in epc_list_raw if epc in exclude_epcs]
        logger.info(f'除外したEPC: {", ".join(excluded)} (プロパティマップ系)')
    
    # 各EPCに名前を付けて表示
    for epc in epc_list:
        epc_info = EPC_DEFINITIONS.get(epc)
        if epc_info:
            logger.info(f'  {epc}: {epc_info["name"]} ({epc_info["class"]})')
        else:
            logger.info(f'  {epc}: (定義なし)')
    
    # 強制モードの場合、重要なEPCを追加
    if force_important_epcs:
        important_epcs = ['D3', 'D7', 'E0', 'E1', 'E7', '82', '8A', '8D', '97', '98']
        added_epcs = []
        for epc in important_epcs:
            if epc not in epc_list:
                epc_list.append(epc)
                added_epcs.append(epc)
        
        if added_epcs:
            logger.info('')
            logger.info(f'強制モード: 以下の重要EPCを追加しました: {", ".join(added_epcs)}')
            for epc in added_epcs:
                epc_info = EPC_DEFINITIONS.get(epc)
                if epc_info:
                    logger.info(f'  {epc}: {epc_info["name"]} ({epc_info["class"]})')
                else:
                    logger.info(f'  {epc}: (定義なし)')

    # .env のフィルタ設定を適用
    epc_list = _apply_epc_filters(epc_list)
    logger.info(f'最終取得対象EPC数: {len(epc_list)}')
    logger.info(f'最終EPC一覧: {", ".join(epc_list)}')
    
    # 
    # Step 7: 全EPCを取得
    logger.info('=== Step 7: 全EPCを取得 ===')
    
    # EPCを数個ずつまとめて取得（一度に多数のEPCを要求すると失敗する可能性があるため）
    batch_size = 10
    for i in range(0, len(epc_list), batch_size):
        batch = epc_list[i:i + batch_size]
        logger.info(f'バッチ {i // batch_size + 1}: {", ".join(batch)}')
        
        cmd = DataFrame.cmd_get_property(batch)
        if not wisundev.sendto(cmd):
            logger.warning(f'バッチ送信に失敗: {", ".join(batch)}')
            continue
        
        # 応答待機
        time.sleep(2)  # 少し待つ
        max_batch_wait = 10
        batch_wait_count = 0
        
        while batch_wait_count < max_batch_wait:
            dataframe = wisundev.receive()
            if dataframe and dataframe.properties:
                for epc, edt in dataframe.properties.items():
                    results[epc] = edt
                    epc_info = EPC_DEFINITIONS.get(epc)
                    epc_name = epc_info['name'] if epc_info else '(定義なし)'
                    display_value = mask_sensitive_value(epc, edt)
                    logger.info(f'  EPC {epc} ({epc_name}): {display_value}')
                break
            time.sleep(0.5)
            batch_wait_count += 1
        
        time.sleep(1)  # バッチ間の待機

    # バッチ応答で欠落したEPCは単独で再取得する
    missing_epcs = [epc for epc in epc_list if epc not in results]
    if missing_epcs:
        logger.info('')
        logger.info(f'バッチ未取得EPCの単独再取得を実施: {", ".join(missing_epcs)}')

    for epc in missing_epcs:
        retry_count = 0
        max_retry = 3
        while retry_count < max_retry:
            cmd = DataFrame.cmd_get_property([epc])
            if not wisundev.sendto(cmd):
                retry_count += 1
                time.sleep(0.5)
                continue

            got_response = False
            wait_count = 0
            while wait_count < 8:
                dataframe = wisundev.receive()
                if dataframe and epc in dataframe.properties:
                    edt = dataframe.properties[epc]
                    results[epc] = edt
                    epc_info = EPC_DEFINITIONS.get(epc)
                    epc_name = epc_info['name'] if epc_info else '(定義なし)'
                    display_value = mask_sensitive_value(epc, edt)
                    logger.info(f'  単独取得 EPC {epc} ({epc_name}): {display_value}')
                    got_response = True
                    break
                time.sleep(0.5)
                wait_count += 1

            if got_response:
                break

            retry_count += 1

        if epc not in results:
            logger.warning(f'  単独再取得失敗 EPC {epc}')
    
    # Step 8: クリーンアップ
    logger.info('=== Step 8: クリーンアップ ===')
    wisundev.term()
    wisundev.close()
    
    return results


def main():
    """メイン処理"""
    global SECURE_MODE
    
    # コマンドライン引数のパース
    parser = argparse.ArgumentParser(
        description='スマートメーターから取得可能な全EPCを取得',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用例:
  %(prog)s                          # .envから設定を読み込んで実行
  %(prog)s -s                       # セキュアモードで実行（機密情報をマスク）
  %(prog)s -f                       # 強制モード（E0/E7等の重要EPCも取得）
  %(prog)s -s -f                    # セキュア+強制モード
  %(prog)s ID PASSWORD              # IDとパスワードを直接指定
  %(prog)s -s ID PASSWORD /dev/ttyUSB0  # すべて指定
        '''
    )
    parser.add_argument('-s', '--secure', action='store_true',
                        help='セキュアモード: ID/パスワード/シリアル番号等を部分的にマスクして表示')
    parser.add_argument('-f', '--force', action='store_true',
                        help='強制モード: プロパティマップに含まれていない重要EPCも取得を試みる')
    parser.add_argument('broute_id', nargs='?', 
                        help='BルートID（省略時は環境変数から取得）')
    parser.add_argument('broute_pwd', nargs='?',
                        help='Bルートパスワード（省略時は環境変数から取得）')
    parser.add_argument('port', nargs='?',
                        help='シリアルポート（省略時は環境変数から取得）')
    
    args = parser.parse_args()
    SECURE_MODE = args.secure
    
    # セキュアモードの場合はbroute.pyのログレベルを上げる（機密情報を出さないため）
    if SECURE_MODE:
        logging.getLogger('keilib.broute').setLevel(logging.WARNING)
        logger.info('セキュアモード有効: 詳細ログを抑制します')
    
    # .envファイルおよび環境変数から設定を取得
    port = args.port or os.getenv('BROUTE_PORT', '/dev/ttyUSB0')
    baudrate = int(os.getenv('BROUTE_BAUDRATE', '115200'))
    # 既存の設定ファイルとの互換性のため両方の変数名をサポート
    broute_id = args.broute_id or os.getenv('BROUTE_ID')
    broute_pwd = args.broute_pwd or os.getenv('BROUTE_PASSWORD') or os.getenv('BROUTE_PWD')
    device_type = os.getenv('WISUN_TYPE') or os.getenv('BROUTE_DEVICE_TYPE', 'DSS')  # DSS or IPS
    
    if not broute_id or not broute_pwd:
        print('エラー: BルートIDとパスワードが設定されていません。')
        print('')
        parser.print_help()
        print('')
        print('設定方法:')
        print('  1. .envファイルを作成して設定:')
        print('     BROUTE_ID=xxxxx')
        print('     BROUTE_PASSWORD=xxxxx')
        print('     BROUTE_PORT=/dev/ttyUSB0  # オプション')
        print('     BROUTE_BAUDRATE=115200    # オプション')
        print('     WISUN_TYPE=DSS            # オプション(DSS or IPS)')
        sys.exit(1)
    
    logger.info('=== スマートメーター全EPC取得開始 ===')
    if SECURE_MODE:
        logger.info('セキュアモード: 有効')
    if args.force:
        logger.info('強制モード: 有効 (重要EPCを追加取得)')
    logger.info(f'ポート: {port}')
    logger.info(f'ボーレート: {baudrate}')
    logger.info(f'デバイスタイプ: {device_type}')
    logger.info(f'BルートID: {mask_string(broute_id, 4) if SECURE_MODE else broute_id}')
    
    # WiSUNデバイスインスタンス作成
    if device_type.upper() == 'IPS':
        wisundev = WiSunRL7023(port, baudrate, WiSunRL7023.IPS)
    else:
        wisundev = WiSunRL7023(port, baudrate, WiSunRL7023.DSS)
    
    # 全EPC取得実行
    results = get_all_epc_values(wisundev, broute_id, broute_pwd, force_important_epcs=args.force)
    
    # 結果表示
    logger.info('=== 取得結果サマリー ===')
    
    # 有効なデータがあるEPCのみをカウント
    valid_results = {epc: edt for epc, edt in results.items() if edt}
    empty_results = {epc: edt for epc, edt in results.items() if not edt}
    
    logger.info(f'取得試行EPC数: {len(results)}')
    logger.info(f'有効データあり: {len(valid_results)}')
    logger.info(f'データなし: {len(empty_results)}')
    logger.info('')
    logger.info('=== 有効データがあるEPC ===')
    
    for epc in sorted(valid_results.keys()):
        edt = valid_results[epc]
        epc_info = EPC_DEFINITIONS.get(epc)
        
        # セキュアモードの場合は機密情報をマスク
        display_value = mask_sensitive_value(epc, edt)
        
        if epc_info:
            print(f'{epc}: {epc_info["name"]:30s} = {display_value}')
        else:
            print(f'{epc}: {"(定義なし)":30s} = {display_value}')
    
    if empty_results:
        logger.info('')
        logger.info('=== データなしのEPC ===')
        for epc in sorted(empty_results.keys()):
            epc_info = EPC_DEFINITIONS.get(epc)
            epc_name = epc_info['name'] if epc_info else '(定義なし)'
            print(f'{epc}: {epc_name}')
    
    if SECURE_MODE:
        logger.info('')
        logger.info('注: セキュアモードが有効なため、一部の値がマスクされています')
    
    # E0, E7などの重要なEPCが取得できていない場合は警告
    important_epcs = {'E0': '積算電力量(正方向)', 'E7': '瞬時電力', 'D3': '係数', 'E1': '積算電力量単位'}
    missing_important = []
    for epc, name in important_epcs.items():
        if epc not in valid_results:
            missing_important.append(f'{epc}({name})')
    
    if missing_important:
        logger.info('')
        logger.warning('以下の重要なEPCが取得できませんでした:')
        for item in missing_important:
            logger.warning(f'  {item}')
        logger.warning('これらのEPCを取得するには -f オプションを使用してください:')
        logger.warning(f'  {sys.argv[0]} -f')

    # .env に貼り付け可能な BROUTE_REQUESTS を出力
    suggested_requests = _build_broute_requests(valid_results)
    if suggested_requests:
        compact = json.dumps(suggested_requests, ensure_ascii=False, separators=(',', ':'))
        pretty = json.dumps(suggested_requests, ensure_ascii=False, indent=2)
        logger.info('')
        logger.info('=== .env 用 BROUTE_REQUESTS 候補 ===')
        print('BROUTE_REQUESTS=' + compact)
        logger.info('参考（整形版）:')
        print(pretty)
    
    logger.info('=== 処理完了 ===')


if __name__ == '__main__':
    main()
